def classify_risk(
    variable: str, value: float, thresholds: dict | None = None
) -> tuple[str, str]:
    from apps.sensors.sensor_config import NO_RISK_VARS
    from apps.alerts.services.threshold_service import get_thresholds

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
    return _classify_by_threshold(thresholds[variable], value)


def _classify_by_threshold(cfg: dict, value: float) -> tuple[str, str]:
    direction = cfg["direction"]
    if direction == "range":
        return _evaluate_range(cfg, value)
    if direction == "higher":
        return _evaluate_higher(cfg, value)
    return _evaluate_lower(cfg, value)


def _evaluate_range(cfg: dict, value: float) -> tuple[str, str]:
    low, high = cfg["low"], cfg["high"]
    return ("Bajo", "green") if low <= value <= high else ("Alto", "orange")


def _evaluate_higher(cfg: dict, value: float) -> tuple[str, str]:
    low, med, high = cfg["low"], cfg["medium"], cfg["high"]
    if value <= low:
        return "Bajo", "green"
    if value <= med:
        return "Medio", "yellow"
    if value <= high:
        return "Alto", "orange"
    return "Crítico", "red"


def _evaluate_lower(cfg: dict, value: float) -> tuple[str, str]:
    low, med, high = cfg["low"], cfg["medium"], cfg["high"]
    if value >= low:
        return "Bajo", "green"
    if value >= med:
        return "Medio", "yellow"
    if value >= high:
        return "Alto", "orange"
    return "Crítico", "red"
