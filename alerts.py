"""
Módulo de alertas y notificaciones del sistema PCLogo.
Contiene lógica de envío de correos, protección de dispositivos
y persistencia de notificaciones en Django.
"""

import os
import sys
import threading
import time
import smtplib
import json as _json
import logging
from collections import deque
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

logger = logging.getLogger(__name__)

from simulation import (
    LOG_SIM, MAX_LOG_ENTRIES, RATIONING_THRESHOLD,
    MAX_DOOR_CLOSE_ATTEMPTS, PROTECTION_HOLD_SECONDS,
    simulators,
    sensor_data, pump_on, elevator_on, protection_ends, active_alerts,
    door_close_attempts, history, alert_log, pending_notifications,
    last_email_sent_time,
    reset_critical_values,
)

from front.sensor_config import (
    VAR_NAMES, UNITS, PUMP_VARS, ELEVATOR_VARS,
    RISK_NAMES_ES, DEVICE_NAMES_ES,
)

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

subscribers = {"email": {"Bajo": [], "Medio": [], "Alto": [], "Crítico": []}}


def get_unit(var):
    return UNITS.get(var, "")


def _es_device(d):
    return DEVICE_NAMES_ES.get(d, d)


def _es_var(v):
    return VAR_NAMES.get(v, v.replace("_", " ").title())


def get_building_emails(edificio_id=None):
    from app27 import DJANGO_CONNECTED, active_edificio_id
    if not DJANGO_CONNECTED:
        return []
    try:
        from app27 import EquipoMonitoreo, Edificio, UsuarioEdificio
        if not edificio_id:
            if active_edificio_id:
                edificio_id = active_edificio_id
            else:
                equipo = EquipoMonitoreo.objects.first()
                if equipo and equipo.id_edificio:
                    edificio_id = equipo.id_edificio.id_edificio
                else:
                    first_edf = Edificio.objects.first()
                    if first_edf:
                        edificio_id = first_edf.id_edificio
                    else:
                        return []

        users = UsuarioEdificio.objects.filter(id_edificio_id=edificio_id).select_related('id_usuario__id_persona')
        emails = []
        for u in users:
            if u.id_usuario and u.id_usuario.id_persona and u.id_usuario.id_persona.email:
                email = u.id_usuario.id_persona.email.strip()
                if email and email not in emails:
                    emails.append(email)
        return emails
    except Exception as e:
        logger.error(f"Error al obtener correos del edificio {edificio_id}: {e}")
        return []


def generate_recommendations(data, stats=None):
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
        recs.append("Sobrepeso en ascensor (>800 kg). Reducir carga.")
    if data["voltage"] < 200 or data["voltage"] > 240:
        recs.append("Inestabilidad eléctrica. Revisar suministro.")
    if data["current"] > 45:
        recs.append("Sobrecarga eléctrica (corriente >45A).")
    if data["motor_stuck"]:
        recs.append("MOTOR PEGADO. Mantenimiento urgente.")
    at_floor = abs(data["position"] - round(data["position"])) < 0.05
    if (
        data["speed"] == 0
        and at_floor
        and door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS
    ):
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} DOORS: speed={data['speed']} at_floor={at_floor} door_close_attempts={door_close_attempts} position={data['position']}"
            )
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
            "Bajo": "Velocidad de ascensor normal.",
            "Medio": "Velocidad moderadamente elevada. Monitorear variador de frecuencia.",
            "Alto": "Velocidad de ascensor por encima del límite de viaje seguro. Programar revisión de variador de frecuencia.",
            "Crítico": "Exceso de velocidad crítico. Frenado de emergencia activado. Inspección técnica de seguridad obligatoria."
        },
        "load": {
            "Bajo": "Carga de cabina normal.",
            "Medio": "Carga moderada en cabina. Vigilar comportamiento del motor.",
            "Alto": "Carga de cabina cercana al límite de diseño. Monitorear comportamiento de motor.",
            "Crítico": "Sobrecarga en cabina de ascensor. Desalojar exceso de peso para reanudar operación."
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
            "Crítico": "Eje del motor del ascensor trabado/bloqueado. Detener cabina y realizar liberación de emergencia de pasajeros."
        },
        "trip_count": {
            "Bajo": "Conteo de viajes dentro del rango normal.",
            "Medio": "Conteo de viajes elevado. Programar inspección de sistema de tracción próximamente.",
            "Alto": "Conteo de viajes alto. Revisar desgaste de componentes mecánicos del ascensor.",
            "Crítico": "Conteo de viajes crítico. Inspección técnica obligatoria antes de continuar operación."
        },
        "position": {
            "Bajo": "Posición del ascensor dentro del rango normal de operación.",
            "Medio": "Posición del ascensor en zona de precaución. Monitorear desplazamiento.",
            "Alto": "Posición del ascensor fuera del rango seguro. Revisar sistema de límites.",
            "Crítico": "Posición crítica detectada. Detener ascensor y revisar sistema de guías."
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
    risk_level, subject, body, attachment_pdf=None, attachment_name="reporte.pdf", recipients=None
):
    if recipients is None:
        recipients = get_building_emails()
    if not recipients:
        logger.info(f"No hay suscriptores para nivel {risk_level} en email")
        return
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            f"⚠️ CREDENCIALES SMTP NO CONFIGURADAS. No se enviará email real a {recipients}."
        )
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

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        for rec in recipients:
            if "To" in msg:
                del msg["To"]
            msg["To"] = rec
            server.send_message(msg)
            logger.info(f"✅ Email REAL enviado a {rec} (riesgo {risk_level})")
        server.quit()
    except Exception as e:
        logger.error(f"Error enviando email: {e}")


def persist_notification_in_django(variable, value, risk_level, recommended_action):
    from app27 import DJANGO_CONNECTED
    if not DJANGO_CONNECTED:
        return
    try:
        from app27 import active_edificio_id, EquipoMonitoreo, Usuario, Notificacion, timezone
        from front.sensor_config import PUMP_VARS, ELEVATOR_VARS

        # Determinar qué tipo de equipo generó la alerta según la variable
        _tipo = None
        if variable in PUMP_VARS or variable == "rationing":
            _tipo = EquipoMonitoreo.TIPO_BOMBA
        elif variable in ELEVATOR_VARS:
            _tipo = EquipoMonitoreo.TIPO_ELEVADOR

        if _tipo and active_edificio_id:
            equipo = EquipoMonitoreo.objects.filter(
                id_edificio_id=active_edificio_id, tipo=_tipo
            ).first()
        else:
            equipo = None

        if not equipo and active_edificio_id:
            equipo = EquipoMonitoreo.objects.filter(id_edificio_id=active_edificio_id).first()

        if not equipo:
            equipo = EquipoMonitoreo.objects.first() if EquipoMonitoreo.objects.exists() else None

        usuario = (
            Usuario.objects.filter(rol="SA").first()
            or Usuario.objects.first()
        )
        mensaje_json = _json.dumps({
            "risk": risk_level,
            "variable": variable,
            "value": str(value) if value is not None else None,
            "action": recommended_action,
        }, ensure_ascii=False)
        if usuario:
            Notificacion.objects.create(
                id_usuario=usuario,
                id_equipo_monitoreo=equipo,
                fecha=timezone.now(),
                mensaje=mensaje_json,
            )
    except Exception as e:
        logger.warning("No se pudo guardar notificación en la DB de Django: %s", e)


def enter_protection_mode(reason=None, targets=None):
    global pump_on, elevator_on, protection_ends
    if not targets:
        logger.warning("Protección solicitada sin targets; no se hará nada.")
        return
    now = time.time()
    targets_set = set(targets)
    for device in targets_set:
        protection_ends[device] = now + PROTECTION_HOLD_SECONDS
        if device == "pump":
            pump_on = True
        elif device == "elevator":
            elevator_on = True
    reason_text = f" ({reason})" if reason else ""
    targets_text_es = " y ".join(_es_device(d) for d in sorted(targets_set))
    targets_text_raw = " y ".join(sorted(targets_set))
    logger.warning(f"PROTECCIÓN ACTIVADA{reason_text}. Marcha forzada: {targets_text_raw}.")
    action_msg = f"Protección automática activada{reason_text}. Marcha forzada / Estado seguro: {targets_text_es}."
    notification_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variable": "auto_protection",
        "value": targets_text_es,
        "risk": "Crítico",
        "message": action_msg,
    }
    alert_log.insert(0, notification_payload)
    pending_notifications.append(notification_payload)
    from app27 import alert_enabled
    if alert_enabled:
        persist_notification_in_django("auto_protection", targets_text_es, "Crítico", action_msg)

    global last_email_sent_time
    now_ts = time.time()
    if now_ts - last_email_sent_time > 300:
        last_email_sent_time = now_ts
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        subject = f"[Proteccion activada] Marcha forzada: {targets_text_es}"
        body = f"""REPORTE AUTOMATICO DE PROTECCION

El sistema de proteccion automatica ha detectado una condicion critica y ha activado la marcha forzada / estado seguro para los siguientes dispositivos.

DETALLES DEL EVENTO:
--------------------------------------------
Fecha/Hora:      {timestamp}
Dispositivos:    {targets_text_es}
Motivo:          {reason or 'condicion critica detectada'}
Estado:          proteccion activada

MEDIDAS CORRECTIVAS SUGERIDAS:
--------------------------------------------
Accion: Inspeccionar los dispositivos indicados antes de reanudar operacion. Los dispositivos se restauraran automaticamente tras el periodo de proteccion.

Este es un mensaje de contingencia generado de forma automatica por el modulo de proteccion.
"""
        threading.Thread(
            target=send_email_alert, args=("Crítico", subject, body), daemon=True
        ).start()
    try:
        from app27 import socketio
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass


def update_protection_state():
    global pump_on, elevator_on, protection_ends
    now = time.time()
    expired = [d for d, end in protection_ends.items() if end and now >= end]
    for device in expired:
        if device == "pump":
            pump_on = True
        elif device == "elevator":
            elevator_on = True
        try:
            reset_critical_values({device})
        except Exception:
            logger.exception("Error reseteando valores críticos para %s", device)
        try:
            if device == "pump":
                for v in PUMP_VARS + ["rationing"]:
                    active_alerts.pop(v, None)
            elif device == "elevator":
                for v in ELEVATOR_VARS:
                    active_alerts.pop(v, None)
        except Exception:
            pass
        del protection_ends[device]
        logger.info("✅ Protección finalizada para %s. Dispositivo restaurado.", device)
        from app27 import alert_enabled
        if alert_enabled:
            persist_notification_in_django(
                f"protection_{device}",
                None,
                "Info",
                f"Protección finalizada para {'la bomba de agua' if device == 'pump' else 'el elevador'}. Operación normal restaurada."
            )
        notification_payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "variable": f"protection_{device}",
            "value": None,
            "risk": "Info",
            "message": f"Protección finalizada para {'la bomba de agua' if device == 'pump' else 'el elevador'}. Operación normal restaurada.",
        }
        alert_log.insert(0, notification_payload)
        pending_notifications.append(notification_payload)
        try:
            from app27 import socketio
            socketio.emit("notification", notification_payload, broadcast=True)
        except Exception:
            pass


def send_alert(variable, value, risk_level, recommended_action):
    global active_alerts, last_email_sent_time
    from app27 import alert_enabled
    if not alert_enabled:
        logger.info("Alertas desactivadas por el usuario")
        return
    if variable in active_alerts and active_alerts[variable] == risk_level:
        return
    active_alerts[variable] = risk_level
    device_target = None
    try:
        if variable in PUMP_VARS or variable == "rationing":
            device_target = "pump"
        elif variable in ELEVATOR_VARS:
            device_target = "elevator"
    except Exception:
        device_target = None
    if LOG_SIM:
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} ALERT: {variable}={value} level={risk_level} mapped={device_target}"
        )
    _risk_adj = RISK_NAMES_ES
    if risk_level in ("Alto", "Crítico"):
        if device_target:
            enter_protection_mode(
                f"alerta {_risk_adj.get(risk_level, risk_level.lower())} de {_es_var(variable).lower()}",
                targets={device_target}
            )
        else:
            logger.warning(
                f"Alerta crítica para {variable} sin mapeo a dispositivo; no se activará protección automática."
            )
    send_email = risk_level in ("Alto", "Crítico")
    var_display = _es_var(variable)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[Alerta de monitoreo] Nivel {risk_level.lower()}: anomalía en {var_display.lower()}"
    body = f"""REPORTE AUTOMATICO DE ANOMALIA

Se ha detectado una lectura fuera de los rangos operacionales recomendados en los sensores de monitoreo de la infraestructura.

DETALLES DEL EVENTO:
--------------------------------------------
Fecha/Hora:      {timestamp}
Parametro:       {var_display}
Lectura:         {value} {get_unit(variable)}
Nivel de riesgo: {risk_level.lower()}

MEDIDAS CORRECTIVAS SUGERIDAS:
--------------------------------------------
Accion:          {recommended_action}

Este es un mensaje de contingencia generado de forma automatica. Por favor, proceda con la inspeccion tecnica correspondiente.
"""

    now = time.time()
    if send_email and now - last_email_sent_time > 300:
        last_email_sent_time = now
        threading.Thread(
            target=send_email_alert, args=(risk_level, subject, body), daemon=True
        ).start()

    notification_payload = {
        "timestamp": timestamp,
        "variable": variable,
        "value": value,
        "risk": risk_level,
        "message": recommended_action,
    }
    alert_log.insert(0, notification_payload)
    pending_notifications.append(notification_payload)
    persist_notification_in_django(variable, value, risk_level, recommended_action)
    try:
        from app27 import socketio
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass
    while len(alert_log) > MAX_LOG_ENTRIES:
        alert_log.pop()


def check_rationing(flow_rate):
    if flow_rate < RATIONING_THRESHOLD:
        action = get_professional_action("rationing", "Crítico", flow_rate)
        send_alert("rationing", flow_rate, "Crítico", action)
        return True
    return False
