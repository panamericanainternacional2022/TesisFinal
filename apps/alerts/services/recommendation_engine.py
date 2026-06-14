from typing import Dict, Any, List

from apps.sensors.sensor_config import (
    VAR_NAMES, RECOMMENDATION_THRESHOLDS,
    RECOMMENDATION_WARN_MSGS, RECOMMENDATION_CRIT_MSGS,
    RECOMMENDATION_RANGE_MSG, ACTIONS, RISK_BAJO, RISK_MEDIO,
    RISK_ALTO, RISK_CRITICO,
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
        recs.append("MOTOR STUCK. Urgent maintenance required.")
    if door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
        recs.append(f"Check doors: {door_close_attempts} failed closing attempts.")
    if not recs:
        recs.append("All parameters normal. Stable operation.")
    return recs[:5]


def get_professional_action(variable: str, risk_level: str, value: Any) -> str:
    var_actions = ACTIONS.get(variable, {})
    var_display = VAR_NAMES.get(variable, variable.replace("_", " "))
    return var_actions.get(risk_level, f"Check the {var_display.lower()} sensor. Schedule preventive inspection.")
