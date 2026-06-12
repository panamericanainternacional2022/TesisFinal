import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = {
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

thresholds: Dict[str, Dict[str, Any]] = DEFAULT_THRESHOLDS.copy()


def load_from_db() -> None:
    try:
        from apps.alerts.services.threshold_service import get_thresholds as _get_db
        db_thresholds = _get_db()
        if db_thresholds != DEFAULT_THRESHOLDS:
            thresholds.clear()
            thresholds.update(db_thresholds)
            logger.info("Thresholds loaded from Django database")
    except Exception as e:
        logger.debug("Could not load thresholds from DB: %s", e)


def save_to_db() -> None:
    try:
        from apps.alerts.services.threshold_service import bulk_update
        bulk_update(thresholds)
        logger.info("Thresholds persisted in Django database")
    except Exception as e:
        logger.warning("Could not persist thresholds in DB: %s", e)
