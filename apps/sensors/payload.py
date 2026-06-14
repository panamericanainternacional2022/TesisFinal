import logging

from apps.sensors.services.payload_service import PayloadContext, build_live_payload as _build_live_payload
from apps.sensors.simulation.models import BuildingSimulator

logger = logging.getLogger(__name__)


def build_live_payload() -> dict:
    from apps.sensors.simulation.globals import (
        sensor_data, protection_ends, history,
        door_close_attempts, pump_on, elevator_on, equipment_types,
        sim_paused, sim_speed,
    )
    from apps.sensors.sensor_config import RATIONING_THRESHOLD
    from apps.alerts.services.alert_service import generate_recommendations
    ctx = PayloadContext(
        sensor_data=sensor_data,
        protection_ends=protection_ends,
        history=history,
        door_close_attempts=door_close_attempts,
        pump_on=pump_on,
        elevator_on=elevator_on,
        equipment_types=equipment_types,
        rationing_threshold=RATIONING_THRESHOLD,
        sim_paused=sim_paused,
        sim_speed=sim_speed,
        generate_recommendations_fn=generate_recommendations,
        alert_enabled=True,
        active_edificio_id=None,
        django_connected=True,
    )
    return _build_live_payload(ctx)


def build_live_payload_for_sim(sim: BuildingSimulator) -> dict:
    from apps.sensors.sensor_config import RATIONING_THRESHOLD
    from apps.alerts.services.alert_service import generate_recommendations
    ctx = PayloadContext(
        sensor_data=sim.sensor_data,
        protection_ends=sim.protection_ends,
        history=sim.history,
        door_close_attempts=sim.door_close_attempts,
        pump_on=sim.pump_on,
        elevator_on=sim.elevator_on,
        equipment_types=sim.equipment_types,
        rationing_threshold=RATIONING_THRESHOLD,
        sim_paused=sim.sim_paused,
        sim_speed=sim.sim_speed,
        generate_recommendations_fn=generate_recommendations,
        alert_enabled=sim.alert_enabled,
        active_edificio_id=sim.edificio_id,
        django_connected=True,
    )
    return _build_live_payload(ctx)
