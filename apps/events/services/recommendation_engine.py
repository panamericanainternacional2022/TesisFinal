from typing import Dict, Any, List

from apps.sensors.sensor_config import (
    VAR_NAMES, RECOMMENDATION_THRESHOLDS,
    RECOMMENDATION_WARN_MSGS, RECOMMENDATION_CRIT_MSGS,
    RECOMMENDATION_RANGE_MSG, RECOMMENDATION_MOTOR_STUCK_MSG,
    RECOMMENDATION_DOOR_MSG_TEMPLATE, RECOMMENDATION_OK_MSG,
    RECOMMENDATION_FALLBACK_ACTION_TEMPLATE,
    ACTIONS, RISK_NORMAL, RISK_INFORMATIVO, RISK_ALTO, RISK_CRITICO,
)
from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS


def generate_recommendations(
    data: Dict[str, Any],
    stats: Any = None,
    door_close_attempts: int = 0,
) -> List[str]:
    recs: List[str] = []

    for var, cfg in RECOMMENDATION_THRESHOLDS.items():
        value = data.get(var)
        if value is None:
            continue

        if "max_crit" in cfg and value > cfg["max_crit"]:
            recs.append(RECOMMENDATION_CRIT_MSGS.get(var, ""))
        elif "max_warn" in cfg and value > cfg["max_warn"]:
            recs.append(RECOMMENDATION_WARN_MSGS.get(var, ""))
        elif "min_crit" in cfg and value < cfg["min_crit"]:
            recs.append(RECOMMENDATION_CRIT_MSGS.get(var, ""))
        elif "min_warn" in cfg and value < cfg["min_warn"]:
            recs.append(RECOMMENDATION_WARN_MSGS.get(var, ""))
        elif "range_warn" in cfg:
            lo, hi = cfg["range_warn"]
            if value < lo or value > hi:
                recs.append(RECOMMENDATION_RANGE_MSG)

    if data.get("motor_stuck", False):
        recs.append(RECOMMENDATION_MOTOR_STUCK_MSG)
    if door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
        recs.append(RECOMMENDATION_DOOR_MSG_TEMPLATE.format(door_close_attempts))
    if not recs:
        recs.append(RECOMMENDATION_OK_MSG)
    return recs[:5]


def get_professional_action(variable: str, risk_level: str, value: Any) -> str:
    var_actions = ACTIONS.get(variable, {})
    var_display = VAR_NAMES.get(variable, variable.replace("_", " "))
    return var_actions.get(risk_level, RECOMMENDATION_FALLBACK_ACTION_TEMPLATE.format(var_display.lower()))
