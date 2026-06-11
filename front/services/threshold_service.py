import logging

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = {
    "flow_rate": {"direction": "higher", "low": 20, "medium": 35, "high": 45},
    "pressure": {"direction": "higher", "low": 5, "medium": 7, "high": 9},
    "temperature": {"direction": "higher", "low": 70, "medium": 85, "high": 100},
    "vibration": {"direction": "higher", "low": 4, "medium": 7, "high": 10},
    "tank_level": {"direction": "lower", "low": 30, "medium": 15, "high": 5},
    "speed": {"direction": "higher", "low": 1.5, "medium": 2.5, "high": 3.5},
    "load": {"direction": "higher", "low": 400, "medium": 700, "high": 900},
    "trip_count": {"direction": "higher", "low": 10000, "medium": 20000, "high": 30000},
    "energy": {"direction": "higher", "low": 8, "medium": 12, "high": 15},
    "voltage": {"direction": "range", "low": 200, "high": 240},
    "current": {"direction": "higher", "low": 30, "medium": 40, "high": 50},
}


def get_thresholds():
    result = DEFAULT_THRESHOLDS.copy()
    try:
        from front.models import UmbralConfig
        for row in UmbralConfig.objects.all():
            result[row.variable] = {
                "direction": row.direction,
                "low": row.low,
                "medium": row.medium if row.medium is not None else 0,
                "high": row.high,
            }
    except Exception as e:
        logger.debug("Could not load thresholds from DB: %s", e)
    return result


def update_threshold(variable, config):
    try:
        from front.models import UmbralConfig
        obj, created = UmbralConfig.objects.update_or_create(
            variable=variable,
            defaults={
                "direction": config.get("direction", "higher"),
                "low": config.get("low", 0),
                "medium": config.get("medium"),
                "high": config.get("high", 0),
            },
        )
        return True
    except Exception as e:
        logger.warning("Could not persist threshold %s: %s", variable, e)
        return False


def bulk_update(thresholds_dict):
    ok = True
    for var, config in thresholds_dict.items():
        if not update_threshold(var, config):
            ok = False
    return ok
