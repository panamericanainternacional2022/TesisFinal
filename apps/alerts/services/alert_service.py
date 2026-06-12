import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from apps.sensors.sensor_config import VAR_NAMES, UNITS, DEVICE_NAMES_ES

logger = logging.getLogger(__name__)


def get_unit(var):
    return UNITS.get(var, "")


def get_building_emails(edificio_id=None):
    try:
        from django.utils import timezone
        from apps.buildings.models import Edificio, EquipoMonitoreo, UsuarioEdificio
    except Exception:
        return []
    try:
        if not edificio_id:
            equipo = EquipoMonitoreo.objects.first()
            if equipo and equipo.id_edificio:
                edificio_id = equipo.id_edificio.id_edificio
            else:
                first_edf = Edificio.objects.first()
                if first_edf:
                    edificio_id = first_edf.id_edificio
                else:
                    return []

        users = UsuarioEdificio.objects.filter(
            id_edificio_id=edificio_id,
            id_usuario__registered=True,
        ).select_related("id_usuario__id_persona")
        emails = []
        for u in users:
            if u.id_usuario and u.id_usuario.id_persona and u.id_usuario.id_persona.email:
                email = u.id_usuario.id_persona.email.strip()
                if email and email not in emails:
                    emails.append(email)
        return emails
    except Exception as e:
        logger.error("Error al obtener correos del edificio %s: %s", edificio_id, e)
        return []


def generate_recommendations(data, stats=None, door_close_attempts=0, MAX_DOOR_CLOSE_ATTEMPTS=3):
    recs = []
    if data["temperature"] > 85:
        recs.append("Temperatura del motor muy alta (>85°C). Revisar refrigeración.")
    elif data["temperature"] > 70:
        recs.append("Temperatura elevada. Monitorear.")
    if data["flow_rate"] < 10:
        recs.append("Caudal bajo (<10 L/s). Revisar bomba.")
    elif data["flow_rate"] < 20:
        recs.append("Caudal bajo óptimo. Revisar filtros.")
    if data["pressure"] > 8:
        recs.append("Presión excesiva (>8 bar). Riesgo de fugas.")
    if data["vibration"] > 7:
        recs.append("Vibración anómala (>7 mm/s). Verificar alineamiento.")
    if data["tank_level"] < 20:
        recs.append("Nivel de tanque crítico (<20%). Reposición urgente.")
    elif data["tank_level"] < 30:
        recs.append("Nivel de tanque bajo.")
    if data["load"] > 800:
        recs.append("Sobrepeso en elevador (>800 kg). Reducir carga.")
    if data["voltage"] < 200 or data["voltage"] > 240:
        recs.append("Inestabilidad eléctrica. Revisar suministro.")
    if data["current"] > 45:
        recs.append("Sobrecarga eléctrica (corriente >45A).")
    if data["motor_stuck"]:
        recs.append("MOTOR PEGADO. Mantenimiento urgente.")
    if door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
        recs.append(
            f"Revisar puertas: {door_close_attempts} intentos de cierre fallidos."
        )
    if not recs:
        recs.append("Todos los parámetros normales. Operación estable.")
    return recs[:5]


def get_professional_action(variable, risk_level, value):
    actions = {
        "flow_rate": {
            "Bajo": "Caudal dentro de rango normal. Monitoreo de rutina activo.",
            "Medio": "Caudal moderado. Verificar que no haya fugas menores o restricciones en la línea.",
            "Alto": "Flujo de agua elevado. Monitorear válvulas de alivio y posibles fugas.",
            "Crítico": "Caudal crítico (interrupción total o exceso grave). Apagado preventivo de bomba activado. Inspeccionar tubería principal."
        },
        "pressure": {
            "Bajo": "Presión dentro de rango operativo. Sin acción requerida.",
            "Medio": "Presión en zona de precaución. Revisar regulador de presión preventivamente.",
            "Alto": "Presión superior al límite recomendado. Verificar regulador de presión y manómetros.",
            "Crítico": "Presión crítica. Riesgo inminente de ruptura de tuberías. Apagar bomba y liberar presión."
        },
        "temperature": {
            "Bajo": "Temperatura normal. Ventilación adecuada.",
            "Medio": "Temperatura moderadamente elevada. Verificar ventilación de sala de máquinas.",
            "Alto": "Temperatura elevada en el motor de la bomba. Incrementar ventilación en sala de máquinas.",
            "Crítico": "Temperatura del motor crítica. Riesgo de sobrecalentamiento y fundición. Apagado de emergencia y revisión de refrigeración."
        },
        "vibration": {
            "Bajo": "Vibración normal. Alineación mecánica correcta.",
            "Medio": "Vibración moderada. Revisar fijaciones mecánicas y estado de rodamientos.",
            "Alto": "Vibración por encima del estándar. Programar mantenimiento mecánico.",
            "Crítico": "Vibración mecánica severa. Desalineación severa o falla de rodamientos. Apagar equipo inmediatamente."
        },
        "tank_level": {
            "Bajo": "Nivel de tanque bajo. Monitorear reabastecimiento.",
            "Medio": "Nivel de tanque en zona de precaución. Programar recarga próximamente.",
            "Alto": "Nivel de tanque elevado. Monitorear llenado automático.",
            "Crítico": "Nivel de tanque crítico. Riesgo de cavitación de la bomba. Detener succión y rellenar tanque urgentemente."
        },
        "speed": {
            "Bajo": "Velocidad de elevador normal.",
            "Medio": "Velocidad moderadamente elevada. Monitorear variador de frecuencia.",
            "Alto": "Velocidad de elevador por encima del límite de viaje seguro. Programar revisión de variador de frecuencia.",
            "Crítico": "Exceso de velocidad crítico. Frenado de emergencia activado. Inspección técnica de seguridad obligatoria."
        },
        "load": {
            "Bajo": "Carga de cabina normal.",
            "Medio": "Carga moderada en cabina. Vigilar comportamiento del motor.",
            "Alto": "Carga de cabina cercana al límite de diseño. Monitorear comportamiento de motor.",
            "Crítico": "Sobrecarga en cabina de elevador. Desalojar exceso de peso para reanudar operación."
        },
        "energy": {
            "Bajo": "Consumo de energía normal.",
            "Medio": "Consumo de energía moderadamente elevado. Verificar eficiencia operativa.",
            "Alto": "Consumo de energía inusualmente elevado. Monitorear eficiencia.",
            "Crítico": "Pico de energía crítico. Posible cortocircuito o sobreesfuerzo del motor. Revisar protecciones eléctricas."
        },
        "voltage": {
            "Bajo": "Voltaje dentro del rango nominal (200-240 V).",
            "Medio": "Voltaje con ligera desviación. Verificar estabilidad de red eléctrica.",
            "Alto": "Inestabilidad en voltaje (fuera del rango 200 V – 240 V). Riesgo para componentes electrónicos.",
            "Crítico": "Fluctuación crítica de tensión eléctrica. Desconectar equipos para evitar daños."
        },
        "current": {
            "Bajo": "Corriente del motor dentro del rango operativo.",
            "Medio": "Corriente del motor moderadamente alta. Monitorear temperatura del bobinado.",
            "Alto": "Corriente del motor por encima del límite recomendado. Revisar carga y estado del bobinado.",
            "Crítico": "Amperaje crítico (sobrecarga eléctrica). Apagado automático de protección activo."
        },
        "motor_stuck": {
            "Crítico": "Eje del motor del elevador trabado/bloqueado. Detener cabina y realizar liberación de emergencia de pasajeros."
        },
        "trip_count": {
            "Bajo": "Conteo de viajes dentro del rango normal.",
            "Medio": "Conteo de viajes elevado. Programar inspección de sistema de tracción próximamente.",
            "Alto": "Conteo de viajes alto. Revisar desgaste de componentes mecánicos del elevador.",
            "Crítico": "Conteo de viajes crítico. Inspección técnica obligatoria antes de continuar operación."
        },
        "position": {
            "Bajo": "Posición del elevador dentro del rango normal de operación.",
            "Medio": "Posición del elevador en zona de precaución. Monitorear desplazamiento.",
            "Alto": "Posición del elevador fuera del rango seguro. Revisar sistema de límites.",
            "Crítico": "Posición crítica detectada. Detener elevador y revisar sistema de guías."
        },
        "door_status": {
            "Bajo": "Estado de puerta normal.",
            "Medio": "Puerta con comportamiento irregular. Monitorear ciclos de apertura y cierre.",
            "Alto": "Fallo en cierre de puerta. Revisar mecanismo de enclavamiento.",
            "Crítico": "Puerta no responde. Detener operación e inspeccionar sistema de puertas."
        },
        "rationing": {
            "Crítico": "Caudal por debajo del mínimo admisible (racionamiento activo). Restringir consumo general."
        }
    }
    var_actions = actions.get(variable, {})
    var_display = VAR_NAMES.get(variable, variable.replace("_", " "))
    return var_actions.get(risk_level, f"Verificar el sensor de {var_display.lower()}. Programar revisión preventiva.")


def send_email_alert(
    risk_level, subject, body, attachment_pdf=None, attachment_name="reporte.pdf", recipients=None,
    SMTP_SERVER=None, SMTP_PORT=None, SMTP_USER=None, SMTP_PASSWORD=None,
):
    import os
    SMTP_SERVER = SMTP_SERVER or os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = SMTP_PORT or int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = SMTP_USER or os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = SMTP_PASSWORD or os.environ.get("SMTP_PASSWORD", "")

    if recipients is None:
        recipients = get_building_emails()
    if not recipients:
        logger.info("No hay suscriptores para nivel %s en email", risk_level)
        return
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("Credenciales SMTP no configuradas. No se enviará email real a %s.", recipients)
        return
    try:
        if risk_level == "Bajo":
            bg_color = "#f0fdf4"
            border_color = "#bbf7d0"
            text_color = "#16a34a"
        elif risk_level == "Medio":
            bg_color = "#fffbeb"
            border_color = "#fde68a"
            text_color = "#b45309"
        elif risk_level in ("Alto", "Crítico"):
            bg_color = "#fef2f2"
            border_color = "#fecaca"
            text_color = "#dc2626"
        else:
            bg_color = "#f5f5f5"
            border_color = "#e0e0e0"
            text_color = "#6b6b6b"

        lines = body.strip().split('\n')
        html_paragraphs = []
        in_details = False
        in_actions = False
        details_rows = []
        action_text = ""

        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            if "DETALLES DEL EVENTO:" in line_strip:
                in_details = True
                in_actions = False
                continue
            elif "MEDIDAS CORRECTIVAS SUGERIDAS:" in line_strip:
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
                if line_strip.startswith("Accion:") or line_strip.startswith("Acción:"):
                    action_text = line_strip.split(":", 1)[1].strip()
                else:
                    action_text += " " + line_strip
            else:
                if "SISTEMA INES" in line_strip and "REPORTE" in line_strip:
                    html_paragraphs.append(f"<h2 style='margin: 0 0 16px 0; font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 2px solid #0a0a0a; padding-bottom: 8px;'>{line_strip}</h2>")
                else:
                    html_paragraphs.append(f"<p style='margin: 0 0 12px 0;'>{line_strip}</p>")

        formatted_content = "".join(html_paragraphs)
        if details_rows:
            formatted_content += f"""
            <h3 style="margin: 20px 0 10px 0; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #0a0a0a;">Detalles del Evento</h3>
            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px; font-size: 13px;">
              {"".join(details_rows)}
            </table>
            """
        if action_text:
            formatted_content += f"""
            <div style="margin: 24px 0; padding: 16px; background-color: {bg_color}; border: 1px solid {border_color}; border-left: 4px solid {text_color};">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: {text_color}; display: block; margin-bottom: 6px;">Medida Correctiva Recomendada</span>
              <p style="margin: 0; font-size: 13px; font-weight: 500; color: #0a0a0a; line-height: 1.4;">{action_text}</p>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f5f5f5; padding: 24px 0;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #0a0a0a; border-collapse: collapse;">
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #ffffff;">
              <span style="font-size: 14px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #0a0a0a;">Sistema de Telemetría </span>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: {bg_color}; border-left: 6px solid {text_color};">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: {text_color}; display: block; margin-bottom: 4px;">NIVEL DE RIESGO: {risk_level.upper()}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Notificación de Alerta y Monitoreo </h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              {formatted_content}
            </td>
          </tr>
          <tr>
            <td style="padding: 16px 24px; border-top: 1px solid #e0e0e0; background-color: #f5f5f5; font-size: 11px; color: #6b6b6b; text-align: center;">
              Este es un mensaje generado de forma automática por el Panel de Control .<br>
              Por favor, no responda a este correo electrónico.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        msg = MIMEMultipart('mixed')
        msg["From"] = SMTP_USER
        msg["Subject"] = subject

        alt_part = MIMEMultipart('alternative')
        alt_part.attach(MIMEText(body, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_content, "html", "utf-8"))
        msg.attach(alt_part)

        if attachment_pdf:
            attachment_pdf.seek(0)
            part = MIMEApplication(attachment_pdf.read(), _subtype="pdf")
            part.add_header(
                "Content-Disposition", "attachment", filename=attachment_name
            )
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        for rec in recipients:
            if "To" in msg:
                del msg["To"]
            msg["To"] = rec
            server.send_message(msg)
            logger.info("Email REAL enviado a %s (riesgo %s)", rec, risk_level)
        server.quit()
    except Exception as e:
        logger.error("Error enviando email: %s", e)


def persist_notification_in_django(variable, value, risk_level, recommended_action, edificio_id=None):
    try:
        from django.utils import timezone
        from apps.buildings.models import EquipoMonitoreo
        from apps.users.models import Usuario
        from apps.alerts.models import Notificacion
        from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS
    except Exception:
        return
    try:
        _tipo = None
        if variable in PUMP_VARS or variable == "rationing":
            _tipo = EquipoMonitoreo.TIPO_BOMBA
        elif variable in ELEVATOR_VARS:
            _tipo = EquipoMonitoreo.TIPO_ELEVADOR

        eid = edificio_id
        if eid is None:
            from apps.sensors.simulation import simulators
            eid = next(iter(simulators.keys()), None)
        if _tipo and eid:
            equipo = EquipoMonitoreo.objects.filter(
                id_edificio_id=eid, tipo=_tipo
            ).first()
        else:
            equipo = None

        if not equipo and eid:
            equipo = EquipoMonitoreo.objects.filter(id_edificio_id=eid).first()

        if not equipo:
            equipo = EquipoMonitoreo.objects.first() if EquipoMonitoreo.objects.exists() else None

        usuario = (
            Usuario.objects.filter(rol="SA").first()
            or Usuario.objects.first()
        )
        mensaje_data = {
            "risk": risk_level,
            "variable": variable,
            "value": str(value) if value is not None else None,
            "action": recommended_action,
        }
        if usuario:
            Notificacion.objects.create(
                id_usuario=usuario,
                id_equipo_monitoreo=equipo,
                fecha=timezone.now(),
                mensaje=mensaje_data,
            )
    except Exception as e:
        logger.warning("No se pudo guardar notificación en la DB de Django: %s", e)


def get_alert_log(edificio_id=None, limit=50):
    import json
    try:
        from apps.alerts.models import Notificacion
        qs = Notificacion.objects.select_related("id_equipo_monitoreo__id_edificio")
        if edificio_id:
            qs = qs.filter(id_equipo_monitoreo__id_edificio_id=edificio_id)
        entries = []
        for n in qs.order_by("-fecha")[:limit]:
            try:
                data = json.loads(n.mensaje)
                entries.append({
                    "timestamp": n.fecha.strftime("%Y-%m-%d %H:%M:%S"),
                    "variable": data.get("variable", ""),
                    "value": data.get("value", ""),
                    "risk": data.get("risk", ""),
                    "message": data.get("action", ""),
                })
            except (json.JSONDecodeError, AttributeError):
                entries.append({
                    "timestamp": n.fecha.strftime("%Y-%m-%d %H:%M:%S") if n.fecha else "",
                    "variable": "",
                    "value": "",
                    "risk": "",
                    "message": n.mensaje or "",
                })
        return entries
    except Exception as e:
        logger.warning("No se pudo obtener alert_log desde DB: %s", e)
        return []
