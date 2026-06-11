"""
Módulo de alertas y notificaciones del sistema PCLogo.
Contiene lógica de envío de correos, protección de dispositivos
y persistencia de notificaciones en Django.

Las funciones puras (generate_recommendations, get_professional_action,
send_email_alert, get_building_emails, persist_notification_in_django)
delegan en front/services/alert_service.py.
"""

import os
import sys
import threading
import time
import json as _json
import logging
from collections import deque

logger = logging.getLogger(__name__)

from simulation import (
    LOG_SIM, RATIONING_THRESHOLD,
    MAX_DOOR_CLOSE_ATTEMPTS, PROTECTION_HOLD_SECONDS,
    simulators,
    sensor_data, pump_on, elevator_on, protection_ends, active_alerts,
    door_close_attempts, history, pending_notifications,
    last_email_sent_time,
    reset_critical_values,
)

from front.sensor_config import (
    VAR_NAMES, UNITS, PUMP_VARS, ELEVATOR_VARS,
    RISK_NAMES_ES, DEVICE_NAMES_ES,
)

from front.services.alert_service import (        # noqa: F401
    get_unit,
    get_building_emails,
    generate_recommendations,
    get_professional_action,
    send_email_alert,
    persist_notification_in_django,
)

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

subscribers = {"email": {"Bajo": [], "Medio": [], "Alto": [], "Crítico": []}}


def _es_device(d):
    return DEVICE_NAMES_ES.get(d, d)


def _es_var(v):
    return VAR_NAMES.get(v, v.replace("_", " ").title())


def enter_protection_mode(reason=None, targets=None):
    global pump_on, elevator_on, protection_ends
    if not targets:
        logger.warning("Protección solicitada sin targets; no se hará nada.")
        return
    now = time.time()
    targets_set = set(targets)
    for device in targets_set:
        protection_ends[device] = now + PROTECTION_HOLD_SECONDS
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
    pending_notifications.append(notification_payload)
    from entry import alert_enabled
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
        from entry import socketio
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass


def update_protection_state():
    global pump_on, elevator_on, protection_ends
    now = time.time()
    expired = [d for d, end in protection_ends.items() if end and now >= end]
    for device in expired:
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
        logger.info("Protección finalizada para %s. Dispositivo restaurado.", device)
        from entry import alert_enabled
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
        pending_notifications.append(notification_payload)
        try:
            from entry import socketio
            socketio.emit("notification", notification_payload, broadcast=True)
        except Exception:
            pass


def send_alert(variable, value, risk_level, recommended_action):
    global active_alerts, last_email_sent_time
    from entry import alert_enabled
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
    pending_notifications.append(notification_payload)
    persist_notification_in_django(variable, value, risk_level, recommended_action)
    try:
        from entry import socketio
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass


def check_rationing(flow_rate):
    if flow_rate < RATIONING_THRESHOLD:
        action = get_professional_action("rationing", "Crítico", flow_rate)
        send_alert("rationing", flow_rate, "Crítico", action)
        return True
    return False
