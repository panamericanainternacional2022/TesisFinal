from __future__ import annotations

import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.sensors.simulation.models import BuildingSimulator

from .utils import (
    COOLDOWN_SECONDS, get_attribute, set_attribute,
    translate_variable_to_spanish, translate_device_to_spanish,
)
from .protection import enter_protection_mode
from apps.sensors.sensor_config import RISK_CRITICO, RISK_ALTO

logger = logging.getLogger(__name__)


def _determine_device_target(variable: str) -> Optional[str]:
    from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS
    try:
        if variable in PUMP_VARS or variable == "rationing":
            return "pump"
        elif variable in ELEVATOR_VARS:
            return "elevator"
    except Exception:
        pass
    return None


def _build_alert_email_subject(variable: str, risk_level: str) -> str:
    var_display = translate_variable_to_spanish(variable)
    return f"Alerta de monitoreo: {var_display} — Nivel {risk_level}"


def _build_alert_email_body(
    variable: str, value: float, risk_level: str, recommended_action: str,
    edificio_nombre: str = "",
    device_target: Optional[str] = None,
) -> str:
    from apps.alerts.services.alert_service import build_standard_email_body, get_unit
    var_display = translate_variable_to_spanish(variable)
    timestamp = time.strftime("%d/%m/%Y %H:%M:%S")
    unit = get_unit(variable)
    detalles = {
        "Fecha y hora":    timestamp,
        "Edificio":        edificio_nombre or "Sistema INES",
        "Parámetro":       var_display,
        "Lectura":         f"{value} {unit}".strip(),
        "Nivel de riesgo": risk_level,
    }
    if device_target:
        device_es = translate_device_to_spanish(device_target)
        article = "el" if device_target == "elevator" else "la"
        detalles["Respuesta automática"] = (
            f"Protección activada — INES ha puesto en modo seguro {article} {device_es} "
            f"de forma preventiva."
        )
    return build_standard_email_body(
        titulo="Anomalía detectada en los sensores de infraestructura",
        contexto=(
            "El sistema ha registrado una lectura fuera de los rangos operativos "
            "establecidos para el presente edificio. A continuación se detallan "
            "los parámetros del evento y la medida correctiva recomendada."
        ),
        detalles=detalles,
        accion=recommended_action,
    )


def _send_alert_email(
    variable: str,
    value: float,
    risk_level: str,
    recommended_action: str,
    last_email_time: float,
    sim: Optional['BuildingSimulator'],
    device_target: Optional[str] = None,
) -> float:
    from apps.alerts.services.alert_service import send_email_alert, get_building_emails
    new_les = last_email_time
    send_email = risk_level in (RISK_ALTO, RISK_CRITICO)
    now = time.time()
    
    times_dict = get_attribute(sim, "last_email_sent_time_per_var")
    if not isinstance(times_dict, dict):
        times_dict = {}
        set_attribute(sim, "last_email_sent_time_per_var", times_dict)
        
    last_sent = times_dict.get(variable, 0.0)
    
    if send_email and now - last_sent > COOLDOWN_SECONDS:
        times_dict[variable] = now
        new_les = now
        edificio_nombre = getattr(sim, "nombre", "") or ""
        edificio_id = getattr(sim, "edificio_id", None)
        subject = _build_alert_email_subject(variable, risk_level)
        body = _build_alert_email_body(
            variable, value, risk_level, recommended_action, edificio_nombre, device_target
        )
        recipients = get_building_emails(edificio_id)
        if not recipients:
            logger.info(
                "Sin destinatarios para alerta del edificio %s (variable=%s, nivel=%s)",
                edificio_id, variable, risk_level,
            )
            return new_les
        threading.Thread(
            target=send_email_alert,
            args=(risk_level, subject, body),
            kwargs={"recipients": recipients},
            daemon=True,
        ).start()
    return new_les


def send_alert(
    variable: str,
    value: float,
    risk_level: str,
    recommended_action: str,
    sim: Optional['BuildingSimulator'] = None,
) -> None:
    aa = get_attribute(sim, "active_alerts")
    les = get_attribute(sim, "last_email_sent_time")

    if variable in aa and aa[variable] == risk_level:
        return
    aa[variable] = risk_level

    device_target = _determine_device_target(variable)

    from apps.sensors.simulation.constants import LOG_SIM
    if LOG_SIM:
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} ALERT: {variable}={value} level={risk_level} mapped={device_target}"
        )

    if risk_level in (RISK_ALTO, RISK_CRITICO):
        if device_target:
            from apps.sensors.sensor_config import RISK_NAMES_ES
            enter_protection_mode(
                f"alert {RISK_NAMES_ES.get(risk_level, risk_level.lower())} of {translate_variable_to_spanish(variable).lower()}",
                targets={device_target},
                sim=sim,
            )
        else:
            logger.warning(
                "Critical alert for %s without device mapping; automatic protection will not be activated.",
                variable,
            )

    new_les = _send_alert_email(variable, value, risk_level, recommended_action, les, sim, device_target)
    set_attribute(sim, "last_email_sent_time", new_les)

    pn = get_attribute(sim, "pending_notifications")
    notification_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variable": variable,
        "value": value,
        "risk": risk_level,
        "message": recommended_action,
    }
    pn.append(notification_payload)

    from apps.alerts.services.alert_service import persist_notification_in_django
    eid = sim.edificio_id if sim else None
    persist_notification_in_django(variable, value, risk_level, recommended_action, edificio_id=eid)


def check_rationing(flow_rate: float, sim: Optional['BuildingSimulator'] = None) -> None:
    from apps.sensors.simulation.constants import RATIONING_THRESHOLD
    from apps.alerts.services.alert_service import get_professional_action
    if flow_rate < RATIONING_THRESHOLD:
        action = get_professional_action("rationing", RISK_CRITICO, flow_rate)
        send_alert("rationing", flow_rate, RISK_CRITICO, action, sim=sim)
