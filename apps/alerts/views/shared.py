import json
from typing import Any, Dict, Optional

from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, VALUE_DISPLAY_ES,
)
from apps.alerts.models import Notification


def _make_parsed(
    risk: str, variable: str, value: str, action: str
) -> Dict[str, Any]:
    var_display = VAR_NAMES.get(variable, variable.replace("_", " ").title())
    value_str = str(value).lower().strip() if value is not None else ""

    if variable in VALUE_DISPLAY_ES:
        value_display = VALUE_DISPLAY_ES[variable].get(value_str, str(value).capitalize())
    elif value_str:
        value_display = value_str.capitalize()
    else:
        value_display = ""

    return {
        "parsed": True,
        "risk": risk,
        "variable": var_display,
        "value": value_display,
        "unit": UNITS.get(variable, ""),
        "action": action,
    }


def parse_notification_for_display(notif: Notification) -> Notification:
    raw_msg = notif.message
    parsed_data: Optional[Dict[str, Any]] = None

    if isinstance(raw_msg, dict):
        parsed_data = _make_parsed(
            risk=raw_msg.get("risk", ""),
            variable=raw_msg.get("variable", ""),
            value=raw_msg.get("value") or "",
            action=raw_msg.get("action", ""),
        )
    elif isinstance(raw_msg, str) and raw_msg.strip().startswith("{"):
        try:
            data = json.loads(raw_msg.strip())
            parsed_data = _make_parsed(
                risk=data.get("risk", ""),
                variable=data.get("variable", ""),
                value=data.get("value") or "",
                action=data.get("action", ""),
            )
        except (ValueError, KeyError):
            parsed_data = None
    else:
        parsed_data = None

    notif.parsed_data = parsed_data or {"parsed": False}
    return notif
