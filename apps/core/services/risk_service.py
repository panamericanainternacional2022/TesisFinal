from typing import Optional

from apps.sensors.sensor_config import (
    RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO,
    NO_RISK_VARS, RISK_UNKNOWN,
)


ZERO_IS_CRITICAL_VARS = {"flow_rate", "pressure"}


def classify_risk(variable: str, value, thresholds: Optional[dict] = None) -> tuple[str, str]:
    from apps.alerts.services.threshold_service import get_thresholds
    if variable == "motor_stuck":
        return (RISK_CRITICO, "red") if value else (RISK_BAJO, "green")
    if variable in NO_RISK_VARS:
        return RISK_BAJO, "green"
    if variable in ZERO_IS_CRITICAL_VARS and value == 0:
        return RISK_CRITICO, "red"
    if thresholds is None:
        thresholds = get_thresholds()
    if variable not in thresholds:
        return RISK_UNKNOWN, "gray"
    cfg = thresholds[variable]
    d = cfg["direction"]
    if d == "range":
        low, high = cfg["low"], cfg["high"]
        return (RISK_BAJO, "green") if low <= value <= high else (RISK_ALTO, "orange")
    else:
        low, med, high = cfg["low"], cfg["medium"], cfg["high"]
        if d == "higher":
            if value <= low:
                return RISK_BAJO, "green"
            elif value <= med:
                return RISK_MEDIO, "yellow"
            elif value <= high:
                return RISK_ALTO, "orange"
            else:
                return RISK_CRITICO, "red"
        else:
            if value >= low:
                return RISK_BAJO, "green"
            elif value >= med:
                return RISK_MEDIO, "yellow"
            elif value >= high:
                return RISK_ALTO, "orange"
            else:
                return RISK_CRITICO, "red"
