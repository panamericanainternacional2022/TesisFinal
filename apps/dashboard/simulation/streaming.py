import json
import logging

import eventlet
from django.http import StreamingHttpResponse

from .shared import get_simulator, json_error_response


logger = logging.getLogger(__name__)


def sse_stream(request, building_id: int) -> StreamingHttpResponse | StreamingHttpResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    def event_stream():
        from apps.sensors.payload import build_live_payload_for_sim
        try:
            while True:
                from apps.sensors.sensor_config import SIM_TICK_INTERVAL
                eventlet.sleep(SIM_TICK_INTERVAL)
                payload = build_live_payload_for_sim(sim)
                yield f"data: {json.dumps(payload)}\n\n"
                while sim.pending_notifications:
                    notif = sim.pending_notifications.popleft()
                    yield f"event: notification\ndata: {json.dumps(notif)}\n\n"
        except (GeneratorExit, IOError, OSError):
            logger.info("Cliente SSE desconectado del edificio %s", building_id)

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
