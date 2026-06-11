from front.sensor_config import NO_RISK_VARS
from front.services.threshold_service import get_thresholds


def classify_risk(variable, value, thresholds=None):
    if variable == "motor_stuck":
        return ("Crítico", "red") if value else ("Bajo", "green")
    if variable in NO_RISK_VARS:
        return "Bajo", "green"
    if variable in ("flow_rate", "pressure") and value == 0:
        return "Crítico", "red"
    if thresholds is None:
        thresholds = get_thresholds()
    if variable not in thresholds:
        return "Desconocido", "gray"
    cfg = thresholds[variable]
    d = cfg["direction"]
    if d == "range":
        low, high = cfg["low"], cfg["high"]
        return ("Bajo", "green") if low <= value <= high else ("Alto", "orange")
    else:
        low, med, high = cfg["low"], cfg["medium"], cfg["high"]
        if d == "higher":
            if value <= low:
                return "Bajo", "green"
            elif value <= med:
                return "Medio", "yellow"
            elif value <= high:
                return "Alto", "orange"
            else:
                return "Crítico", "red"
        else:
            if value >= low:
                return "Bajo", "green"
            elif value >= med:
                return "Medio", "yellow"
            elif value >= high:
                return "Alto", "orange"
            else:
                return "Crítico", "red"
