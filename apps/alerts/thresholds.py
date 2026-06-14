import logging
from typing import Dict, Any

from apps.sensors.sensor_config import DEFAULT_THRESHOLDS as _DEFAULT

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = _DEFAULT

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
