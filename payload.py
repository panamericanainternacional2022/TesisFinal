"""
Módulo de construcción del payload en vivo para SSE.
"""

import logging

from front.services.payload_service import (  # noqa: F401
    titleize_name,
    build_live_payload as _build_live_payload,
)
from front.services.alert_service import generate_recommendations

logger = logging.getLogger(__name__)


def build_live_payload():
    """Legacy: construye payload desde globales (usa active_sim)."""
    from simulation import (
        sensor_data, protection_ends, history,
        door_close_attempts, pump_on, elevator_on, equipment_types,
        RATIONING_THRESHOLD, sim_paused, sim_speed,
    )
    return _build_live_payload(
        sensor_data=sensor_data,
        protection_ends=protection_ends,
        history=history,
        door_close_attempts=door_close_attempts,
        pump_on=pump_on,
        elevator_on=elevator_on,
        equipment_types=equipment_types,
        RATIONING_THRESHOLD=RATIONING_THRESHOLD,
        sim_paused=sim_paused,
        sim_speed=sim_speed,
        generate_recommendations_fn=generate_recommendations,
        alert_enabled=True,
        active_edificio_id=None,
        DJANGO_CONNECTED=True,
    )


def build_live_payload_for_sim(sim):
    """Construye payload directamente desde un BuildingSimulator."""
    from simulation import RATIONING_THRESHOLD
    return _build_live_payload(
        sensor_data=sim.sensor_data,
        protection_ends=sim.protection_ends,
        history=sim.history,
        door_close_attempts=sim.door_close_attempts,
        pump_on=sim.pump_on,
        elevator_on=sim.elevator_on,
        equipment_types=sim.equipment_types,
        RATIONING_THRESHOLD=RATIONING_THRESHOLD,
        sim_paused=sim.sim_paused,
        sim_speed=sim.sim_speed,
        generate_recommendations_fn=generate_recommendations,
        alert_enabled=sim.alert_enabled,
        active_edificio_id=sim.edificio_id,
        DJANGO_CONNECTED=True,
    )
