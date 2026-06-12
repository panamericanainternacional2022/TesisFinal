import logging
from typing import Dict, Any

from django.db import IntegrityError

from apps.alerts.models import ThresholdConfig

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


def get_thresholds() -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    try:
        for row in ThresholdConfig.objects.all():
            result[row.variable] = {
                "direction": row.direction,
                "low": row.low,
                "medium": row.medium,
                "high": row.high,
            }
    except Exception as e:
        logger.debug("Could not load thresholds from DB: %s", e)
    return result


class ThresholdPersistenceError(Exception):
    pass


def update_threshold(variable: str, config: Dict[str, Any]) -> None:
    try:
        medium = config.get("medium")
        if medium is not None:
            try:
                medium = float(medium)
            except (ValueError, TypeError):
                medium = None
        ThresholdConfig.objects.update_or_create(
            variable=variable,
            defaults={
                "direction": config.get("direction", "higher"),
                "low": config.get("low", 0),
                "medium": medium,
                "high": config.get("high", 0),
            },
        )
    except IntegrityError:
        raise ThresholdPersistenceError(f"Could not persist threshold {variable}: integrity error")
    except Exception as e:
        raise ThresholdPersistenceError(f"Could not persist threshold {variable}: {e}")


def bulk_update(thresholds_dict: Dict[str, Dict[str, Any]]) -> None:
    errors: list[str] = []
    for var, config in thresholds_dict.items():
        try:
            update_threshold(var, config)
        except ThresholdPersistenceError as e:
            errors.append(str(e))
    if errors:
        raise ThresholdPersistenceError("; ".join(errors))
