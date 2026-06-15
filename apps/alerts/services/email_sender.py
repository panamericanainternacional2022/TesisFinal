import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from typing import Any, Dict, List, Optional



logger = logging.getLogger(__name__)


def get_unit(variable: str) -> str:
    from apps.sensors.sensor_config import UNITS
    return UNITS.get(variable, "")


def get_building_emails(edificio_id: Optional[int] = None) -> List[str]:
    try:
        from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
    except Exception:
        return []
    try:
        if not edificio_id:
            equipo = MonitoringEquipment.objects.first()
            if equipo and equipo.building:
                edificio_id = equipo.building.id
            else:
                first_edf = Building.objects.first()
                if first_edf:
                    edificio_id = first_edf.id
                else:
                    return []

        users = UserBuilding.objects.filter(
            building_id=edificio_id,
            user__registered=True,
            user__alerts_disabled=False,
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


def _build_email_shell(inner_html: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{subject}}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f5f5f5; padding: 24px 0;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #0a0a0a; border-collapse: collapse;">
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #ffffff;">
              <span style="font-size: 14px; font-weight: 700; letter-spacing: 0.12em; color: #0a0a0a;">Sistema INES</span>
            </td>
          </tr>
          {inner_html}
          <tr>
            <td style="padding: 16px 24px; border-top: 1px solid #e0e0e0; background-color: #f5f5f5; font-size: 11px; color: #6b6b6b; text-align: center;">
              Este mensaje es generado automáticamente por el Sistema de Monitoreo INES.<br>
              Por favor, no responda a este correo.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email_raw(
    to_addrs: List[str],
    subject: str,
    html_body: str,
    plain_body: str = "",
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

    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["Subject"] = subject
    msg.attach(MIMEText(plain_body or html_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    from apps.sensors.sensor_config import SMTP_TIMEOUT
    _smtp_send(msg, to_addrs, smtp_server, smtp_port, smtp_user, smtp_password, SMTP_TIMEOUT)


def _get_email_colors(risk_level: str) -> Dict[str, str]:
    from apps.sensors.sensor_config import EMAIL_COLOR_PALETTE, EMAIL_FALLBACK_COLORS
    return EMAIL_COLOR_PALETTE.get(risk_level, EMAIL_FALLBACK_COLORS)


def build_standard_email_body(
    titulo: str,
    detalles: Optional[Dict[str, str]] = None,
    accion: str = "",
    contexto: str = "",
) -> str:
    lines = [titulo, ""]
    if contexto:
        lines.append(contexto)
        lines.append("")
    if detalles:
        lines.append("DETALLES DEL EVENTO:")
        lines.append("-" * 44)
        for k, v in detalles.items():
            lines.append(f"{k}:{' ' * (18 - len(k))}{v}")
        lines.append("")
    if accion:
        lines.append("MEDIDAS CORRECTIVAS RECOMENDADAS:")
        lines.append("-" * 44)
        lines.append(f"Acción:         {accion}")
        lines.append("")
    return "\n".join(lines)


def _build_html_from_sections(
    risk_level: str,
    paragraphs: List[str],
    details: Optional[Dict[str, str]] = None,
    action_text: str = "",
) -> str:
    colors = _get_email_colors(risk_level)
    inner = "".join(f"<p style='margin: 0 0 12px 0;'>{p}</p>" for p in paragraphs)

    if details:
        rows = "".join(f"""
          <tr>
            <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; font-weight: 700; width: 35%; color: #0a0a0a;">{k}</td>
            <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; color: #2e2e2e;">{v}</td>
          </tr>""" for k, v in details.items())
        inner += f"""
        <h3 style="margin: 20px 0 10px 0; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; color: #0a0a0a;">Detalles del evento</h3>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px; font-size: 13px;">{rows}
        </table>"""

    if action_text:
        inner += f"""
        <div style="margin: 24px 0; padding: 16px; background-color: {colors['bg']}; border: 1px solid {colors['border']}; border-left: 4px solid {colors['text']};">
          <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.06em; color: {colors['text']}; display: block; margin-bottom: 6px;">Medida correctiva recomendada</span>
          <p style="margin: 0; font-size: 13px; font-weight: 500; color: #0a0a0a; line-height: 1.4;">{action_text}</p>
        </div>"""

    banner = f"""
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: {colors['bg']}; border-left: 6px solid {colors['text']};">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; color: {colors['text']}; display: block; margin-bottom: 4px;">Nivel de riesgo: {risk_level}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Notificación de alerta y monitoreo</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              {inner}
            </td>
          </tr>"""
    return _build_email_shell(banner)


def _build_html_content(body: str, risk_level: str) -> str:
    colors = _get_email_colors(risk_level)
    lines = body.strip().split("\n")
    html_paragraphs: List[str] = []
    in_details = False
    in_actions = False
    details_rows: List[str] = []
    action_text = ""

    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
        if "DETALLES DEL EVENTO:" in line_strip:
            in_details = True
            in_actions = False
            continue
        elif "MEDIDAS CORRECTIVAS RECOMENDADAS:" in line_strip:
            in_details = False
            in_actions = True
            continue
        elif line_strip.startswith("---") or line_strip.startswith("==="):
            continue

        if in_details:
            if ":" in line_strip:
                parts = line_strip.split(":", 1)
                key = parts[0].strip()
                val = parts[1].strip()
                details_rows.append(f"""
                  <tr>
                    <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; font-weight: 700; width: 35%; color: #0a0a0a;">{key}</td>
                    <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; color: #2e2e2e;">{val}</td>
                  </tr>
                """)
            else:
                if details_rows:
                    html_paragraphs.append(f"<p style='margin: 0 0 12px 0;'>{line_strip}</p>")
        elif in_actions:
            if line_strip.startswith("Acción:"):
                action_text = line_strip.split(":", 1)[1].strip()
            else:
                action_text += " " + line_strip
        else:
            html_paragraphs.append(f"<p style='margin: 0 0 12px 0;'>{line_strip}</p>")

    inner = "".join(html_paragraphs)
    if details_rows:
        inner += f"""
        <h3 style="margin: 20px 0 10px 0; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; color: #0a0a0a;">Detalles del evento</h3>
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px; font-size: 13px;">
          {"".join(details_rows)}
        </table>
        """
    if action_text:
        inner += f"""
        <div style="margin: 24px 0; padding: 16px; background-color: {colors['bg']}; border: 1px solid {colors['border']}; border-left: 4px solid {colors['text']};">
          <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.06em; color: {colors['text']}; display: block; margin-bottom: 6px;">Medida correctiva recomendada</span>
          <p style="margin: 0; font-size: 13px; font-weight: 500; color: #0a0a0a; line-height: 1.4;">{action_text}</p>
        </div>
        """

    banner = f"""
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: {colors['bg']}; border-left: 6px solid {colors['text']};">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; color: {colors['text']}; display: block; margin-bottom: 4px;">Nivel de riesgo: {risk_level}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Notificación de alerta y monitoreo</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              {inner}
            </td>
          </tr>"""

    return _build_email_shell(banner)


def build_activation_email_html(link: str) -> str:
    inner_html = f"""
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #f5f5f5; border-left: 6px solid #0a0a0a;">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; color: #5e5e5e; display: block; margin-bottom: 4px;">Acceso al sistema</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Activaci&oacute;n de cuenta</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              <p style="margin: 0 0 16px 0;">Hola,</p>
              <p style="margin: 0 0 16px 0;">Se ha registrado su usuario en el Sistema de Monitoreo INES. Para poder acceder y utilizar todas las funciones de monitoreo y alertas de infraestructura de su edificio, es necesario que complete su registro.</p>
              <p style="margin: 0 0 24px 0;">Por favor, haga clic en el bot&oacute;n a continuaci&oacute;n para definir su nombre de usuario y contrase&ntilde;a:</p>
              <div style="margin: 24px 0; text-align: left;">
                <a href="{link}" target="_blank" style="background-color: #0a0a0a; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; display: inline-block; border-radius: 0px; border: 1px solid #0a0a0a;">Completar registro</a>
              </div>
              <div style="margin: 24px 0; padding: 16px; background-color: #f5f5f5; border: 1px solid #e0e0e0; font-size: 12px; color: #5e5e5e;">
                <p style="margin: 0 0 8px 0; font-weight: 700;">Informaci&oacute;n de seguridad:</p>
                <p style="margin: 0 0 8px 0;">&bull; Este enlace es v&aacute;lido por 24 horas.</p>
                <p style="margin: 0;">&bull; Si usted no solicit&oacute; este registro, por favor ignore este correo.</p>
              </div>
              <p style="margin: 0; font-size: 12px; color: #9e9e9e;">Si el bot&oacute;n no funciona, copie y pegue la siguiente direcci&oacute;n en su navegador:<br>
              <a href="{link}" style="color: #0a0a0a; text-decoration: underline;">{link}</a></p>
            </td>
          </tr>"""
    return _build_email_shell(inner_html)


def _send_email_smtp(config: EmailConfig) -> None:
    smtp_server, smtp_port, smtp_user, smtp_password = _get_smtp_creds(
        config.smtp_server, config.smtp_port, config.smtp_user, config.smtp_password
    )

    if not smtp_user or not smtp_password:
        logger.warning("SMTP credentials not configured. No real email will be sent to %s.", config.recipients)
        return

    html_content = _build_html_content(config.body, config.risk_level)

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
