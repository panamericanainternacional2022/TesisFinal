import json
from typing import Any, Dict, List, Optional

from django.db.models import Q, QuerySet

from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, VALUE_DISPLAY_ES, FAULT_NAMES_ES,
    RISK_CRITICO, RISK_ALTO, RISK_INFORMATIVO,
)
from apps.alerts.models import Notification


_RISK_ICONS = {
    RISK_CRITICO:     "fa-circle-exclamation",
    RISK_ALTO:        "fa-circle-exclamation",
    RISK_INFORMATIVO: "fa-circle-info",
}

_RISK_CSS = {
    RISK_CRITICO:     "risk-crit",
    RISK_ALTO:        "risk-high",
    RISK_INFORMATIVO: "risk-info",
}


def exclude_severity_levels(queryset: QuerySet, levels: Optional[List[str]] = None) -> QuerySet:
    if not levels:
        return queryset
    query = Q()
    for level in levels:
        query |= Q(**{"message__risk": level})
        query |= Q(**{"message__contains": f'"risk": "{level}"'})
        query |= Q(**{"message__contains": f'"risk":"{level}"'})
    return queryset.exclude(query)


def filter_severity_include(queryset: QuerySet, severity: str) -> QuerySet:
    if not severity:
        return queryset
    return queryset.filter(
        Q(**{"message__risk": severity})
        | Q(**{"message__contains": f'"risk": "{severity}"'})
        | Q(**{"message__contains": f'"risk":"{severity}"'})
    )


def _build_notification_query(
    user_id: int,
    role: str,
    building_id: Optional[str] = None,
) -> tuple[QuerySet, str]:
    from apps.core.auth_decorators import is_admin_role
    from apps.buildings.models import Building, MonitoringEquipment, UserBuilding

    building_name = ""
    if is_admin_role(role):
        notifications = Notification.objects.all()
        if building_id:
            notifications = notifications.filter(monitoring_equipment__building_id=building_id)
            try:
                building_name = Building.objects.get(id=building_id).name
            except Building.DoesNotExist:
                pass
    else:
        user_building_ids = list(UserBuilding.objects.filter(
            user_id=user_id
        ).values_list("building_id", flat=True))
        if building_id:
            if building_id.isdigit() and int(building_id) in user_building_ids:
                notifications = Notification.objects.filter(
                    monitoring_equipment__building_id=building_id
                )
                try:
                    building_name = Building.objects.get(id=building_id).name
                except Building.DoesNotExist:
                    pass
            else:
                notifications = Notification.objects.none()
        else:
            equipment_ids = list(MonitoringEquipment.objects.filter(
                building_id__in=user_building_ids
            ).values_list("id", flat=True))
            notifications = Notification.objects.filter(
                user_id=user_id
            ) | Notification.objects.filter(monitoring_equipment_id__in=equipment_ids)
    return notifications, building_name


def _make_parsed(
    risk: str, variable: str, value: object, action: str
) -> Dict[str, Any]:
    var_display = VAR_NAMES.get(variable, variable.replace("_", " ").title())

    if value is None:
        raw_str = ""
    else:
        raw_str = str(value).strip()

    value_str = raw_str.lower()

    if variable in VALUE_DISPLAY_ES:
        value_display = VALUE_DISPLAY_ES[variable].get(value_str, raw_str.capitalize())
        if value_str in ("true", "false") and variable in ("motor_stuck",):
            value_display = ""
    elif variable.startswith("fault_resolved_"):
        value_display = FAULT_NAMES_ES.get(value_str, raw_str.capitalize())
    elif raw_str:
        value_display = raw_str
    else:
        value_display = ""

    return {
        "parsed": True,
        "risk": risk,
        "variable": var_display,
        "value": value_display,
        "unit": UNITS.get(variable, ""),
        "action": action,
        "risk_icon": _RISK_ICONS.get(risk, "fa-circle-check"),
        "risk_css": _RISK_CSS.get(risk, "risk-info"),
    }


def parse_notification_for_display(notif: Notification) -> Notification:
    raw_msg = notif.message
    parsed_data: Optional[Dict[str, Any]] = None

    if isinstance(raw_msg, dict):
        raw_value = raw_msg.get("value")
        parsed_data = _make_parsed(
            risk=raw_msg.get("risk", ""),
            variable=raw_msg.get("variable", ""),
            value=raw_value,
            action=raw_msg.get("action", ""),
        )
    elif isinstance(raw_msg, str) and raw_msg.strip().startswith("{"):
        try:
            data = json.loads(raw_msg.strip())
            raw_value = data.get("value")
            parsed_data = _make_parsed(
                risk=data.get("risk", ""),
                variable=data.get("variable", ""),
                value=raw_value,
                action=data.get("action", ""),
            )
        except (ValueError, KeyError):
            parsed_data = None
    else:
        parsed_data = None

    notif.parsed_data = parsed_data or {"parsed": False}
    return notif
