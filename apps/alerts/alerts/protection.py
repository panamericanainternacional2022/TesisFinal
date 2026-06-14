from __future__ import annotations

import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.sensors.simulation.models import BuildingSimulator

from .utils import (
    COOLDOWN_SECONDS, get_attribute, set_attribute, translate_device_to_spanish,
)
from apps.sensors.sensor_config import RISK_CRITICO, RISK_INFO

logger = logging.getLogger(__name__)


def _send_protection_email(
    reason: Optional[str],
    targets_text_es: str,
    targets_text_raw: str,
    last_email_time: float,
) -> float:
    from apps.alerts.services.alert_service import send_email_alert
    now_ts = time.time()
    if now_ts - last_email_time <= COOLDOWN_SECONDS:
        return last_email_time
    timestamp = time.strftime("%d/%m/%Y %H:%M:%S")
    subject = f"[INES] Protección - {targets_text_es}"
    body = (
        f"Reporte de protección automática\n\n"
        f"El sistema de protección automática ha detectado una condición crítica "
        f"y ha activado la operación forzada en los siguientes dispositivos.\n\n"
        f"DETALLES DEL EVENTO:\n"
        f"{'':->44}\n"
        f"Fecha y hora:   {timestamp}\n"
        f"Dispositivos:   {targets_text_es}\n"
        f"Motivo:         {reason or 'condición crítica detectada'}\n"
        f"Estado:         protección activada\n\n"
        f"MEDIDAS CORRECTIVAS RECOMENDADAS:\n"
        f"{'':->44}\n"
        f"Acción:         Inspeccione los dispositivos indicados antes de reanudar la "
        f"operación. Los dispositivos se restaurarán automáticamente después del "
        f"período de protección.\n\n"
        f"Este es un mensaje de contingencia generado automáticamente por el "
        f"Sistema de Monitoreo INES. Por favor, no responda a este correo."
    )
    threading.Thread(
        target=send_email_alert, args=(RISK_CRITICO, subject, body), daemon=True
    ).start()
    return now_ts


def enter_protection_mode(
    reason: Optional[str] = None,
    targets: Optional[set[str]] = None,
    sim: Optional['BuildingSimulator'] = None,
) -> None:
    from apps.sensors.simulation.constants import PROTECTION_HOLD_SECONDS
    from apps.alerts.services.alert_service import get_professional_action
    if not targets:
        logger.warning("Protection requested without targets; nothing will be done.")
        return

    pe = get_attribute(sim, "protection_ends")
    pn = get_attribute(sim, "pending_notifications")
    les = get_attribute(sim, "last_email_sent_time")

    now = time.time()
    for device in targets:
        pe[device] = now + PROTECTION_HOLD_SECONDS

    reason_text = f" ({reason})" if reason else ""
    targets_text_es = " y ".join(translate_device_to_spanish(d) for d in sorted(targets))
    targets_text_raw = " and ".join(sorted(targets))
    logger.warning("PROTECTION ACTIVATED%s. Forced operation: %s.", reason_text, targets_text_raw)

    action = get_professional_action("auto_protection", RISK_CRITICO, targets_text_es)
    notification_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variable": "auto_protection",
        "value": targets_text_es,
        "risk": RISK_CRITICO,
        "message": action,
    }
    pn.append(notification_payload)

    alert_enabled = sim.alert_enabled if sim else True
    if alert_enabled:
        from apps.alerts.services.alert_service import persist_notification_in_django
        eid = sim.edificio_id if sim else None
        persist_notification_in_django(
            "auto_protection", targets_text_es, RISK_CRITICO, action, edificio_id=eid
        )

    new_les = _send_protection_email(reason, targets_text_es, targets_text_raw, les)
    set_attribute(sim, "last_email_sent_time", new_les)


def _get_expired_devices(protection_ends_dict: dict[str, float]) -> list[str]:
    now = time.time()
    return [d for d, end in protection_ends_dict.items() if end and now >= end]


def _reset_device(device: str, sim: Optional['BuildingSimulator']) -> None:
    from apps.sensors.simulation.controls import reset_critical_values

    try:
        reset_critical_values({device}, sim)
    except Exception:
        logger.exception("Error resetting critical values for %s", device)


def _clear_device_alerts(device: str, active_alerts_dict: dict[str, str]) -> None:
    from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS
    try:
        if device == "pump":
            for v in PUMP_VARS + ["rationing"]:
                active_alerts_dict.pop(v, None)
        elif device == "elevator":
            for v in ELEVATOR_VARS:
                active_alerts_dict.pop(v, None)
    except Exception:
        pass


def _notify_protection_ended(device: str, sim: Optional['BuildingSimulator'], pn: list) -> None:
    from apps.alerts.services.alert_service import persist_notification_in_django, get_professional_action
    from .utils import translate_device_to_spanish
    device_es = translate_device_to_spanish(device)
    action = get_professional_action(f"protection_{device}", RISK_INFO, None)
    alert_enabled = sim.alert_enabled if sim else True
    if alert_enabled:
        eid = sim.edificio_id if sim else None
        persist_notification_in_django(
            f"protection_{device}", None, RISK_INFO, action, edificio_id=eid,
        )
    notification_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variable": f"protection_{device}",
        "value": None,
        "risk": RISK_INFO,
        "message": action,
    }
    pn.append(notification_payload)


def update_protection_state(sim: Optional['BuildingSimulator'] = None) -> None:
    pe = get_attribute(sim, "protection_ends")
    aa = get_attribute(sim, "active_alerts")
    pn = get_attribute(sim, "pending_notifications")

    expired = _get_expired_devices(pe)
    for device in expired:
        _reset_device(device, sim)
        _clear_device_alerts(device, aa)
        del pe[device]
        logger.info("Protection ended for %s. Device restored.", device)
        _notify_protection_ended(device, sim, pn)
