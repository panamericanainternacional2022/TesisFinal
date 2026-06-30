import json
import logging
from typing import Any, Dict, List, Optional

from apps.events.models import Notification

logger = logging.getLogger(__name__)


def _find_equipment(variable: str, edificio_id: Optional[int]) -> Any:
    from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS
    from apps.buildings.models import MonitoringEquipment
    from apps.users.models import Usuario

    tipo = None
    if variable in PUMP_VARS or variable == "rationing":
        tipo = MonitoringEquipment.TYPE_PUMP
    elif variable in ELEVATOR_VARS:
        tipo = MonitoringEquipment.TYPE_ELEVATOR

    eid = edificio_id
    if eid is None:
        from apps.sensors.simulation.globals import simulators
        eid = next(iter(simulators.keys()), None)

    equipo = None
    if tipo and eid:
        equipo = MonitoringEquipment.objects.filter(
            building_id=eid, equipment_type=tipo
        ).first()

    if not equipo and eid:
        equipo = MonitoringEquipment.objects.filter(building_id=eid).first()

    if not equipo:
        equipo = MonitoringEquipment.objects.first() if MonitoringEquipment.objects.exists() else None

    from apps.core.auth_decorators import ADMIN_ROLES
    usuario = Usuario.objects.filter(rol__in=ADMIN_ROLES).first() or Usuario.objects.first()
    return equipo, usuario


def persist_notification_in_django(
    variable: str,
    value: Any,
    risk_level: str,
    recommended_action: str,
    edificio_id: Optional[int] = None,
) -> None:
    try:
        from django.utils import timezone

        equipo, usuario = _find_equipment(variable, edificio_id)
        if not usuario:
            return

        mensaje_data: Dict[str, Any] = {
            "risk": risk_level,
            "variable": variable,
            "value": str(value) if value is not None else None,
            "action": recommended_action,
        }
        Notification.objects.create(
            user=usuario,
            monitoring_equipment=equipo,
            date=timezone.now(),
            message=mensaje_data,
        )
    except Exception as e:
        logger.warning("Could not save notification in Django DB: %s", e)


def get_alert_log(edificio_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, str]]:
    try:
        qs = Notification.objects.select_related("monitoring_equipment__building")
        if edificio_id:
            qs = qs.filter(monitoring_equipment__building_id=edificio_id)
        entries: List[Dict[str, str]] = []
        for n in qs.order_by("-date")[:limit]:
            try:
                raw = n.message
                if isinstance(raw, str):
                    data = json.loads(raw)
                else:
                    data = raw
                entries.append({
                    "timestamp": n.date.strftime("%Y-%m-%d %H:%M:%S"),
                    "variable": data.get("variable", ""),
                    "value": data.get("value", ""),
                    "risk": data.get("risk", ""),
                    "message": data.get("action", ""),
                })
            except (json.JSONDecodeError, AttributeError):
                entries.append({
                    "timestamp": n.date.strftime("%Y-%m-%d %H:%M:%S") if n.date else "",
                    "variable": "",
                    "value": "",
                    "risk": "",
                    "message": str(n.message or ""),
                })
        return entries
    except Exception as e:
        logger.warning("Could not retrieve alert_log from DB: %s", e)
        return []
