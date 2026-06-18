import logging
from typing import Dict, Any

from django.db import IntegrityError

from apps.alerts.models import ThresholdConfig
from apps.sensors.sensor_config import DEFAULT_THRESHOLDS as _DEFAULT

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = _DEFAULT


def get_thresholds(building_id: int) -> Dict[str, Dict[str, Any]]:
    """Return thresholds for a specific building.

    Falls back to DEFAULT_THRESHOLDS for any variable not yet customised
    in the DB, then overlays the building-specific overrides on top.
    """
    result: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    try:
        for row in ThresholdConfig.objects.filter(building_id=building_id):
            result[row.variable] = {
                "direction": row.direction,
                "low": row.low,
                "medium": row.medium,
                "high": row.high,
            }
    except Exception as e:
        logger.debug("Could not load thresholds from DB (building %s): %s", building_id, e)
    return result


class ThresholdPersistenceError(Exception):
    pass


def update_threshold(variable: str, config: Dict[str, Any], building_id: int) -> None:
    try:
        medium = config.get("medium")
        if medium is not None:
            try:
                medium = float(medium)
            except (ValueError, TypeError):
                medium = None
        ThresholdConfig.objects.update_or_create(
            building_id=building_id,
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


def bulk_update(thresholds_dict: Dict[str, Dict[str, Any]], building_id: int) -> None:
    errors: list[str] = []
    for var, config in thresholds_dict.items():
        try:
            update_threshold(var, config, building_id)
        except ThresholdPersistenceError as e:
            errors.append(str(e))
    if errors:
        raise ThresholdPersistenceError("; ".join(errors))
