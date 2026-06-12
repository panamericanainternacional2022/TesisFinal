import json
import re
from typing import Any, Dict, List, Optional

from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, RISK_NAMES_ES, DEVICE_NAMES_ES, VALUE_DISPLAY_ES,
)
from apps.alerts.models import Notification


def _translate_devices(text: str) -> str:
    for en, es in DEVICE_NAMES_ES.items():
        text = re.sub(rf"\b{re.escape(en)}\b", es, text, flags=re.IGNORECASE)
    return text


def _build_protection_action(risk: str, raw_action: str) -> str:
    risk_es = RISK_NAMES_ES.get(risk, risk.lower())
    devices_match = re.search(r"[Dd]ispositivos?\s+apagados?:\s*(.+)", raw_action)
    if devices_match:
        devices_es = _translate_devices(devices_match.group(1).rstrip("."))
        return f"Automatic protection activated (alert {risk_es}). Devices off: {devices_es}."
    return f"Automatic protection activated (alert {risk_es}). {_translate_devices(raw_action)}"


def _make_parsed(
    risk: str, variable: str, value: str, action: str
) -> Dict[str, Any]:
    var_display = VAR_NAMES.get(variable, variable.replace("_", " ").title())
    value_str = str(value).lower().strip() if value is not None else ""

    if variable in VALUE_DISPLAY_ES:
        value_display = VALUE_DISPLAY_ES[variable].get(value_str, str(value).capitalize())
    elif value_str == "pump":
        value_display = "Water pump"
    elif value_str == "elevator":
        value_display = "Elevator"
    elif value_str in DEVICE_NAMES_ES:
        value_display = DEVICE_NAMES_ES[value_str].capitalize()
    elif value_str:
        value_display = value_str.capitalize()
    else:
        value_display = ""

    if variable == "Automatic protection":
        action = _build_protection_action(risk, action)
    elif variable.startswith("Protection "):
        action = _translate_devices(action)

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
    raw_str = ""
    parsed_data: Optional[Dict[str, Any]] = None

    if isinstance(raw_msg, dict):
        parsed_data = _make_parsed(
            risk=raw_msg.get("risk", ""),
            variable=raw_msg.get("variable", ""),
            value=raw_msg.get("value") or "",
            action=raw_msg.get("action", ""),
        )
        raw_str = json.dumps(raw_msg)
    elif isinstance(raw_msg, str):
        raw_str = raw_msg.strip()
        if raw_str.startswith("{"):
            try:
                data = json.loads(raw_str)
                parsed_data = _make_parsed(
                    risk=data.get("risk", ""),
                    variable=data.get("variable", ""),
                    value=data.get("value") or "",
                    action=data.get("action", ""),
                )
            except (ValueError, KeyError):
                parsed_data = None
    else:
        raw_str = str(raw_msg or "")
        parsed_data = None

    if parsed_data is None:
        m = re.match(r"^\[(.*?)\]\s+(.*?)\s+=\s+(.*?)\s+-\s+(.*)$", raw_str)
        if m:
            parsed_data = _make_parsed(
                risk=m.group(1).strip(),
                variable=m.group(2).strip(),
                value=m.group(3).strip(),
                action=m.group(4).strip(),
            )

    if parsed_data is None:
        pm = re.match(
            r"Automatic protection activated\s*\(Alert\s+(\w+)\s+of\s+(\w+)\).+\s*Devices off:\s*(.+)",
            raw_str,
            re.IGNORECASE,
        )
        if pm:
            p_risk = pm.group(1).strip().capitalize()
            p_variable = pm.group(2).strip()
            p_devices_es = _translate_devices(pm.group(3).rstrip("."))
            p_risk_es = RISK_NAMES_ES.get(p_risk, p_risk.lower())
            p_var_es = VAR_NAMES.get(p_variable, p_variable.replace("_", " "))
            parsed_data = {
                "parsed": True,
                "risk": p_risk,
                "variable": "Automatic protection",
                "value": "True",
                "unit": "",
                "action": (
                    f"Automatic protection activated ({p_var_es} {p_risk_es}). "
                    f"Devices off: {p_devices_es}."
                ),
            }

    notif.parsed_data = parsed_data or {"parsed": False}
    return notif
