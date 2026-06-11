"""
Configuración del sistema de monitoreo.
Contiene los umbrales de riesgo y configuración general.
No confundir con front/sensor_config.py (nombres y unidades de sensores).
"""

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

thresholds = DEFAULT_THRESHOLDS.copy()


def load_from_db():
    try:
        from front.services.threshold_service import get_thresholds as _get_db
        db_thresholds = _get_db()
        if db_thresholds != DEFAULT_THRESHOLDS:
            thresholds.clear()
            thresholds.update(db_thresholds)
            logger.info("Umbrales cargados desde la base de datos de Django")
    except Exception as e:
        logger.debug("No se pudieron cargar umbrales desde DB: %s", e)


def save_to_db():
    try:
        from front.services.threshold_service import bulk_update
        bulk_update(thresholds)
        logger.info("Umbrales persistidos en la base de datos de Django")
    except Exception as e:
        logger.warning("No se pudieron persistir umbrales en DB: %s", e)


try:
    load_from_db()
except Exception:
    pass
