import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Any, Dict, List, Optional

from apps.core.auth_decorators import ADMIN_ROLES


logger = logging.getLogger(__name__)


# ─── Constantes de texto — fuente única, no hardcodeadas en el HTML ──────────
_BRAND_NAME      = "INES"
_BRAND_SUBTITLE  = "Sistema inteligente de automatización"
_ALERT_H1        = "Anomalía detectada en la infraestructura"
_ALERT_TAG_LABEL = "Severidad"             # alineado con la columna homónima de los PDFs
_ACTION_LABEL    = "Medida correctiva recomendada"
_DETAILS_LABEL   = "Detalles del evento"
_FOOTER_TEXT     = (
    "Este mensaje ha sido generado automáticamente por el Sistema de Monitoreo INES.<br>"
    "Por favor, no responda a este correo."
)
_CONTEXT_DEFAULT = (
    "El sistema ha registrado una lectura fuera de los rangos operativos "
    "establecidos para el presente edificio. A continuación se detallan "
    "los parámetros del evento y la medida correctiva recomendada."
)

# Acento navy — idéntico al usado en los PDFs (ACCENT_COLOR)
_NAVY = "#1e3a5f"


# ─── Helpers de datos ─────────────────────────────────────────────────────────

def get_unit(variable: str) -> str:
    from apps.sensors.sensor_config import UNITS
    return UNITS.get(variable, "")


def get_building_emails(edificio_id: Optional[int] = None) -> List[str]:
    try:
        from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
    except Exception:
        return []
    try:
        if edificio_id is None:
            # Fallback: ningún edificio especificado — usar el primero disponible.
            # ADVERTENCIA: este fallback solo debería usarse en contextos sin simulador
            # activo. Las alertas del engine siempre deben pasar un edificio_id explícito.
            equipo = MonitoringEquipment.objects.first()
            if equipo and equipo.building:
                edificio_id = equipo.building.id
            else:
                first_edf = Building.objects.first()
                if first_edf:
                    edificio_id = first_edf.id
                else:
                    return []
            logger.warning(
                "get_building_emails llamado sin edificio_id — usando fallback edificio %s. "
                "Las alertas del simulador deberían pasar siempre un edificio_id explícito.",
                edificio_id,
            )

        users = UserBuilding.objects.filter(
            building_id=edificio_id,
            user__registered=True,
            user__email_alerts_disabled=False,
        ).exclude(
            user__rol__in=ADMIN_ROLES,
        ).select_related("user__id_persona")
        emails: List[str] = []
        for u in users:
            if u.user and u.user.id_persona and u.user.id_persona.email:
                email = u.user.id_persona.email.strip()
                if email and email not in emails:
                    emails.append(email)
        return emails
    except Exception as e:
        logger.error("Error retrieving emails for building %s: %s", edificio_id, e)
        return []


# ─── Clases de configuración ──────────────────────────────────────────────────

class EmailAttachment:
    def __init__(self, pdf_data: Any, filename: str = "report.pdf") -> None:
        if isinstance(pdf_data, bytes):
            from io import BytesIO
            pdf_data = BytesIO(pdf_data)
        self.pdf_data = pdf_data
        self.filename = filename


class EmailConfig:
    def __init__(
        self,
        risk_level: str,
        subject: str,
        body: str,
        attachment: Optional[EmailAttachment] = None,
        recipients: Optional[List[str]] = None,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ) -> None:
        self.risk_level = risk_level
        self.subject = subject
        self.body = body
        self.attachment = attachment
        self.recipients = recipients
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password


# ─── SMTP helpers ─────────────────────────────────────────────────────────────

def _smtp_send(
    msg: Any,
    recipients: List[str],
    server: str,
    port: int,
    user: str,
    password: str,
    timeout: int = 15,
) -> None:
    if not user or not password:
        logger.warning("SMTP credentials not configured. Email not sent to %s.", recipients)
        return
    conn = smtplib.SMTP(server, port, timeout=timeout)
    conn.starttls()
    conn.login(user, password)
    for rec in recipients:
        if "To" in msg:
            del msg["To"]
        msg["To"] = rec
        conn.send_message(msg)
    conn.quit()


def _get_smtp_creds(
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> tuple[str, int, str, str]:
    return (
        smtp_server or os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port or int(os.environ.get("SMTP_PORT", 587)),
        smtp_user or os.environ.get("SMTP_USER", ""),
        smtp_password or os.environ.get("SMTP_PASSWORD", ""),
    )


def _get_email_colors(risk_level: str) -> Dict[str, str]:
    from apps.sensors.sensor_config import EMAIL_COLOR_PALETTE, EMAIL_FALLBACK_COLORS
    return EMAIL_COLOR_PALETTE.get(risk_level, EMAIL_FALLBACK_COLORS)


# ─── Shell exterior — idéntico para todos los correos ─────────────────────────

def _build_email_shell(inner_html: str) -> str:
    """
    Cáscara HTML compartida por los 2 tipos de correo.
    Header con barra de acento navy (coherente con los PDFs) +
    wordmark INES + subtítulo + footer automático.
    """
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: #0a0a0a;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f0f2f5; padding: 32px 0;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #d1d5db; border-collapse: collapse; box-shadow: 0 4px 16px rgba(0,0,0,0.08);">

          <!-- Barra de acento navy (coherente con los PDFs) -->
          <tr>
            <td style="background-color: {_NAVY}; height: 4px; padding: 0; font-size: 0; line-height: 0;">&nbsp;</td>
          </tr>

          <!-- Header con wordmark INES (sin border-bottom para que el banner fluya pegado) -->
          <tr>
            <td style="padding: 18px 28px 18px 28px; background-color: #ffffff;">
              <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="border-left: 4px solid {_NAVY}; padding-left: 12px;">
                    <span style="font-size: 18px; font-weight: 800; letter-spacing: -0.02em; color: {_NAVY}; display: block; line-height: 1.2;">{_BRAND_NAME}</span>
                    <span style="font-size: 11px; font-weight: 500; color: #6b7280; display: block; margin-top: 2px;">{_BRAND_SUBTITLE}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          {inner_html}

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 28px; border-top: 1px solid #e5e7eb; background-color: #f9fafb; font-size: 11px; color: #9ca3af; text-align: center; line-height: 1.6;">
              {_FOOTER_TEXT}
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ─── Tabla de detalles — componente compartido ────────────────────────────────

def _build_details_table(details: Dict[str, str]) -> str:
    """
    Tabla de pares clave/valor, patrón compartido entre correo de alerta
    y cualquier futuro correo que necesite mostrar información estructurada.
    """
    rows = "".join(f"""
          <tr>
            <td style="padding: 10px 0; border-bottom: 1px solid #f3f4f6; font-size: 12px; font-weight: 700; width: 38%; color: #374151; vertical-align: top;">{k}</td>
            <td style="padding: 10px 0; border-bottom: 1px solid #f3f4f6; font-size: 13px; color: #111827; vertical-align: top;">{v}</td>
          </tr>""" for k, v in details.items())
    return f"""
        <p style="margin: 20px 0 8px 0; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: #6b7280; text-transform: uppercase;">{_DETAILS_LABEL}</p>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; border-top: 1px solid #f3f4f6; margin-bottom: 24px;">
          {rows}
        </table>"""


# ─── Caja de acción — componente compartido ───────────────────────────────────

def _build_action_box(action_text: str, colors: Dict[str, str]) -> str:
    """
    Caja de medida correctiva con borde izquierdo del color del riesgo.
    Patrón compartido disponible para todos los correos.
    """
    return f"""
        <div style="margin: 20px 0 0 0; padding: 16px 20px; background-color: {colors['bg']}; border: 1px solid {colors['border']}; border-left: 4px solid {colors['text']}; border-radius: 2px;">
          <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {colors['text']}; display: block; margin-bottom: 6px; text-transform: uppercase;">{_ACTION_LABEL}</span>
          <p style="margin: 0; font-size: 13px; font-weight: 500; color: #111827; line-height: 1.5;">{action_text}</p>
        </div>"""


# ─── Constructor único para correos de alerta ─────────────────────────────────

def _build_alert_html(
    risk_level: str,
    context: str = _CONTEXT_DEFAULT,
    details: Optional[Dict[str, str]] = None,
    action_text: str = "",
) -> str:
    """
    Constructor único para correos de alerta de sensor.
    Reemplaza _build_html_from_sections y _build_html_content.

    Estructura del correo:
      1. Banner (color del riesgo + tag de nivel + H1)
      2. Párrafo de contexto
      3. Tabla de detalles (si se provee)
      4. Caja de acción correctiva (si se provee)
    """
    colors = _get_email_colors(risk_level)

    # 1 — Banner de cabecera del correo (pegado al header sin gap)
    banner = f"""
          <tr>
            <td style="padding: 20px 28px; border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb; background-color: {colors['bg']}; border-left: 4px solid {colors['text']};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {colors['text']}; display: block; margin-bottom: 6px; text-transform: uppercase;">{_ALERT_TAG_LABEL}: {risk_level}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: #111827;">{_ALERT_H1}</h1>
            </td>
          </tr>"""

    # 2 — Cuerpo del correo
    inner = f'<p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #374151;">{context}</p>'

    # 3 — Tabla de detalles
    if details:
        inner += _build_details_table(details)

    # 4 — Caja de acción correctiva
    if action_text:
        inner += _build_action_box(action_text, colors)

    body_row = f"""
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: #374151;">
              {inner}
            </td>
          </tr>"""

    return _build_email_shell(banner + body_row)


# ─── Constructor para correo de activación de cuenta ─────────────────────────

def build_activation_email_html(link: str) -> str:
    """
    Correo de activación de cuenta de usuario.
    Sigue el mismo shell y patrones visuales que el correo de alerta.
    """
    inner_html = f"""
          <!-- Banner de cabecera (pegado al header sin gap) -->
          <tr>
            <td style="padding: 20px 28px; border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb; background-color: #f8fafc; border-left: 4px solid {_NAVY};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_NAVY}; display: block; margin-bottom: 6px; text-transform: uppercase;">Acceso al sistema</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: #111827;">Activaci&oacute;n de su cuenta</h1>
            </td>
          </tr>

          <!-- Cuerpo -->
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: #374151;">
              <p style="margin: 0 0 16px 0;">Estimado/a usuario/a:</p>
              <p style="margin: 0 0 16px 0;">Su cuenta ha sido registrada en el <strong>Sistema de Monitoreo INES</strong>. Para completar el proceso de registro y acceder a todas las funciones de la plataforma, es necesario que establezca su nombre de usuario y contrase&ntilde;a.</p>
              <p style="margin: 0 0 24px 0;">Para ello, haga clic en el bot&oacute;n que figura a continuaci&oacute;n:</p>

              <!-- Bot&oacute;n CTA -->
              <div style="margin: 0 0 28px 0; text-align: left;">
                <a href="{link}" target="_blank"
                   style="background-color: {_NAVY}; color: #ffffff; text-decoration: none; padding: 12px 28px; font-size: 13px; font-weight: 700; letter-spacing: 0.05em; display: inline-block; border-radius: 2px;">
                  Completar registro
                </a>
              </div>

              <!-- Caja de informaci&oacute;n de seguridad -->
              <div style="padding: 16px 20px; background-color: #f8fafc; border: 1px solid #e5e7eb; border-left: 4px solid {_NAVY}; border-radius: 2px; margin-bottom: 24px;">
                <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_NAVY}; display: block; margin-bottom: 8px; text-transform: uppercase;">Informaci&oacute;n de seguridad</span>
                <p style="margin: 0 0 6px 0; font-size: 13px; color: #374151;">&bull; Este enlace es v&aacute;lido durante las pr&oacute;ximas <strong>24 horas</strong>.</p>
                <p style="margin: 0; font-size: 13px; color: #374151;">&bull; Si usted no ha solicitado este registro, puede ignorar el presente correo sin que ello implique ninguna consecuencia.</p>
              </div>

              <!-- Enlace de respaldo -->
              <p style="margin: 0; font-size: 12px; color: #9ca3af;">Si el bot&oacute;n no funciona correctamente, copie y pegue la siguiente direcci&oacute;n en su navegador:<br>
              <a href="{link}" style="color: {_NAVY}; text-decoration: underline; word-break: break-all;">{link}</a></p>
            </td>
          </tr>"""

    return _build_email_shell(inner_html)


# ─── Constructor para correo de reporte de estado ────────────────────────────────

def build_report_email_html(edificio: str = "", contexto: str = "") -> str:
    """
    Correo de reporte de estado del sistema (enviado desde el dashboard).
    Tiene su propio banner diferenciado del correo de alerta:
      - Etiqueta: REPORTE DE MONITOREO
      - H1: Estado actual del sistema de infraestructura
    """
    ctx = contexto or (
        f"Se adjunta el informe en formato PDF con el estado actual de los "
        f"sensores de infraestructura{' de ' + edificio if edificio else ''}. "
        f"El documento incluye las lecturas más recientes, las estadísticas de "
        f"operación y un resumen del nivel de riesgo de cada parámetro monitoreado."
    )
    inner_html = f"""
          <!-- Banner de cabecera (reporte de estado — tono neutro informativo) -->
          <tr>
            <td style="padding: 20px 28px; border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb; background-color: #f0f4f8; border-left: 4px solid {_NAVY};">
              <span style="font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: {_NAVY}; display: block; margin-bottom: 6px; text-transform: uppercase;">Reporte de monitoreo</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.25; letter-spacing: -0.02em; color: #111827;">Estado actual del sistema de infraestructura</h1>
            </td>
          </tr>

          <!-- Cuerpo -->
          <tr>
            <td style="padding: 28px; font-size: 14px; line-height: 1.6; color: #374151;">
              <p style="margin: 0 0 20px 0;">{ctx}</p>
              <p style="margin: 0; font-size: 13px; color: #6b7280;">El informe PDF se encuentra adjunto al presente correo.</p>
            </td>
          </tr>"""
    return _build_email_shell(inner_html)


# ─── Función auxiliar para plain-text (solo texto, sin estructura HTML) ───────

def build_standard_email_body(
    titulo: str,
    detalles: Optional[Dict[str, str]] = None,
    accion: str = "",
    contexto: str = "",
) -> str:
    """
    Genera el cuerpo en texto plano del correo de alerta.
    No contiene estructura para conversión a HTML: eso lo hace _build_alert_html.
    """
    lines = [titulo, ""]
    if contexto:
        lines.append(contexto)
        lines.append("")
    if detalles:
        lines.append("DETALLES DEL EVENTO:")
        lines.append("-" * 44)
        for k, v in detalles.items():
            lines.append(f"{k}:{' ' * max(1, 18 - len(k))}{v}")
        lines.append("")
    if accion:
        lines.append("MEDIDA CORRECTIVA RECOMENDADA:")
        lines.append("-" * 44)
        lines.append(f"Acción: {accion}")
        lines.append("")
    return "\n".join(lines)


# ─── Envío de correo raw (p.ej. activación) ───────────────────────────────────

def send_email_raw(
    to_addrs: List[str],
    subject: str,
    html_body: str,
    plain_body: str = "",
    attachment_pdf: Optional[bytes] = None,
    attachment_name: str = "reporte.pdf",
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> None:
    smtp_server, smtp_port, smtp_user, smtp_password = _get_smtp_creds(
        smtp_server, smtp_port, smtp_user, smtp_password
    )
    if not smtp_user or not smtp_password:
        logger.warning("SMTP not configured. Email '%s' not sent.", subject)
        return

    if attachment_pdf is not None:
        msg = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain_body or html_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)
        part = MIMEApplication(attachment_pdf, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=attachment_name)
        msg.attach(part)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(plain_body or html_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    msg["From"] = smtp_user
    msg["Subject"] = subject

    from apps.sensors.sensor_config import SMTP_TIMEOUT
    _smtp_send(msg, to_addrs, smtp_server, smtp_port, smtp_user, smtp_password, SMTP_TIMEOUT)


# ─── Envío SMTP con adjunto (correo de alerta principal) ──────────────────────

def _send_email_smtp(config: EmailConfig) -> None:
    smtp_server, smtp_port, smtp_user, smtp_password = _get_smtp_creds(
        config.smtp_server, config.smtp_port, config.smtp_user, config.smtp_password
    )

    if not smtp_user or not smtp_password:
        logger.warning(
            "SMTP credentials not configured. No real email will be sent to %s.",
            config.recipients,
        )
        return

    # ── Construir HTML desde el cuerpo plain-text parseado ───────────────────
    # El body plain-text tiene secciones delimitadas por cabeceras en mayúsculas.
    # Parseamos para extraer detalles y acción, y los pasamos a _build_alert_html.
    details: Dict[str, str] = {}
    action_text = ""
    context_lines: List[str] = []
    in_details = False
    in_actions = False

    for line in config.body.strip().split("\n"):
        line_strip = line.strip()
        if not line_strip:
            continue
        if "DETALLES DEL EVENTO:" in line_strip:
            in_details, in_actions = True, False
            continue
        if "MEDIDA CORRECTIVA RECOMENDADA:" in line_strip:
            in_details, in_actions = False, True
            continue
        if line_strip.startswith("---") or line_strip.startswith("==="):
            continue

        if in_details:
            if ":" in line_strip:
                k, _, v = line_strip.partition(":")
                details[k.strip()] = v.strip()
        elif in_actions:
            if line_strip.startswith("Acción:"):
                action_text = line_strip.split(":", 1)[1].strip()
            else:
                action_text = (action_text + " " + line_strip).strip()
        else:
            # Omitimos la primera línea (título) ya que el H1 del HTML la representa
            context_lines.append(line_strip)

    # La primera línea context es el título, la segunda (si existe) es el contexto
    context = " ".join(context_lines[1:]) if len(context_lines) > 1 else _CONTEXT_DEFAULT

    html_content = _build_alert_html(
        risk_level=config.risk_level,
        context=context or _CONTEXT_DEFAULT,
        details=details or None,
        action_text=action_text,
    )

    msg = MIMEMultipart("mixed")
    msg["From"] = smtp_user
    msg["Subject"] = config.subject

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(config.body, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(alt_part)

    if config.attachment:
        config.attachment.pdf_data.seek(0)
        part = MIMEApplication(config.attachment.pdf_data.read(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=config.attachment.filename)
        msg.attach(part)

    from apps.sensors.sensor_config import SMTP_TIMEOUT
    _smtp_send(msg, config.recipients or [], smtp_server, smtp_port, smtp_user, smtp_password, SMTP_TIMEOUT)
    logger.info("Real email sent to %s (risk %s)", config.recipients, config.risk_level)


# ─── Punto de entrada público para alertas ────────────────────────────────────

def send_email_alert(
    risk_level: str,
    subject: str,
    body: str,
    attachment_pdf: Any = None,
    attachment_name: str = "report.pdf",
    recipients: Optional[List[str]] = None,
    smtp_server: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> None:
    if recipients is None:
        recipients = get_building_emails()
    if not recipients:
        logger.info("No subscribers for level %s in email", risk_level)
        return

    attachment = EmailAttachment(attachment_pdf, attachment_name) if attachment_pdf else None
    config = EmailConfig(
        risk_level=risk_level,
        subject=subject,
        body=body,
        attachment=attachment,
        recipients=recipients,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
    )

    try:
        _send_email_smtp(config)
    except Exception as e:
        logger.error("Error sending email: %s", e)
