"""
Módulo de construcción del payload en vivo para streaming SSE/WebSocket.
Contiene titleize_name y build_live_payload.
Delega en front/services/payload_service.py.
"""

import logging

from front.services.payload_service import (  # noqa: F401
    titleize_name,
    build_live_payload as _build_live_payload,
)
from front.services.alert_service import generate_recommendations

logger = logging.getLogger(__name__)


def build_live_payload():
    from simulation import (
        sensor_data, protection_ends, history,
        door_close_attempts, pump_on, elevator_on, equipment_types,
        RATIONING_THRESHOLD, sim_paused, sim_speed,
    )
    from entry import alert_enabled, active_edificio_id, DJANGO_CONNECTED

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
        alert_enabled=alert_enabled,
        active_edificio_id=active_edificio_id,
        DJANGO_CONNECTED=DJANGO_CONNECTED,
    )
