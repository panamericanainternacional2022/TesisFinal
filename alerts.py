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

from simulation import (
    BuildingSimulator,
    LOG_SIM, RATIONING_THRESHOLD,
    MAX_DOOR_CLOSE_ATTEMPTS, PROTECTION_HOLD_SECONDS,
    simulators,
    sensor_data, pump_on, elevator_on, protection_ends, active_alerts,
    door_close_attempts, history, pending_notifications,
    last_email_sent_time,
    reset_critical_values,
)

logger = logging.getLogger(__name__)

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


def _sim_or_global(sim, attr):
    if sim is not None:
        return getattr(sim, attr)
    return globals()[attr]


def enter_protection_mode(reason=None, targets=None, sim=None):
    if not targets:
        logger.warning("Protección solicitada sin targets; no se hará nada.")
        return

    pe = _sim_or_global(sim, "protection_ends")
    pn = _sim_or_global(sim, "pending_notifications")
    les = _sim_or_global(sim, "last_email_sent_time")

    now = time.time()
    targets_set = set(targets)
    for device in targets_set:
        pe[device] = now + PROTECTION_HOLD_SECONDS
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
    pn.append(notification_payload)
    from entry import alert_enabled
    if alert_enabled:
        eid = sim.edificio_id if sim else None
        persist_notification_in_django("auto_protection", targets_text_es, "Crítico", action_msg, edificio_id=eid)

    now_ts = time.time()
    if now_ts - les > 300:
        les = now_ts
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

    if sim is not None:
        sim.last_email_sent_time = les
    else:
        global last_email_sent_time
        last_email_sent_time = les

    try:
        from entry import socketio
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass


def update_protection_state(sim=None):
    pe = _sim_or_global(sim, "protection_ends")
    sd = _sim_or_global(sim, "sensor_data")
    aa = _sim_or_global(sim, "active_alerts")
    pn = _sim_or_global(sim, "pending_notifications")

    now = time.time()
    expired = [d for d, end in pe.items() if end and now >= end]
    for device in expired:
        try:
            reset_critical_values({device}, sd)
        except Exception:
            logger.exception("Error reseteando valores críticos para %s", device)
        try:
            if device == "pump":
                for v in PUMP_VARS + ["rationing"]:
                    aa.pop(v, None)
            elif device == "elevator":
                for v in ELEVATOR_VARS:
                    aa.pop(v, None)
        except Exception:
            pass
        del pe[device]
        logger.info("Protección finalizada para %s. Dispositivo restaurado.", device)
        from entry import alert_enabled
        if alert_enabled:
            eid = sim.edificio_id if sim else None
            persist_notification_in_django(
                f"protection_{device}",
                None,
                "Info",
                f"Protección finalizada para {'la bomba de agua' if device == 'pump' else 'el elevador'}. Operación normal restaurada.",
                edificio_id=eid,
            )
        notification_payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "variable": f"protection_{device}",
            "value": None,
            "risk": "Info",
            "message": f"Protección finalizada para {'la bomba de agua' if device == 'pump' else 'el elevador'}. Operación normal restaurada.",
        }
        pn.append(notification_payload)
        try:
            from entry import socketio
            socketio.emit("notification", notification_payload, broadcast=True)
        except Exception:
            pass


def send_alert(variable, value, risk_level, recommended_action, sim=None):
    aa = _sim_or_global(sim, "active_alerts")
    les = _sim_or_global(sim, "last_email_sent_time")

    from entry import alert_enabled
    if not alert_enabled:
        logger.info("Alertas desactivadas por el usuario")
        return
    if variable in aa and aa[variable] == risk_level:
        return
    aa[variable] = risk_level
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
                targets={device_target},
                sim=sim,
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
    if send_email and now - les > 300:
        les = now
        if sim is not None:
            sim.last_email_sent_time = les
        else:
            global last_email_sent_time
            last_email_sent_time = les
        threading.Thread(
            target=send_email_alert, args=(risk_level, subject, body), daemon=True
        ).start()

    pn = _sim_or_global(sim, "pending_notifications")
    notification_payload = {
        "timestamp": timestamp,
        "variable": variable,
        "value": value,
        "risk": risk_level,
        "message": recommended_action,
    }
    pn.append(notification_payload)
    eid = sim.edificio_id if sim else None
    persist_notification_in_django(variable, value, risk_level, recommended_action, edificio_id=eid)
    try:
        from entry import socketio
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass


def check_rationing(flow_rate, sim=None):
    if flow_rate < RATIONING_THRESHOLD:
        action = get_professional_action("rationing", "Crítico", flow_rate)
        send_alert("rationing", flow_rate, "Crítico", action, sim=sim)
        return True
    return False
