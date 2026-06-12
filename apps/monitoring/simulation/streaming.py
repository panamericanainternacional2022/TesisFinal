import json
import logging

import eventlet
from django.http import StreamingHttpResponse

from apps.sensors.payload import build_live_payload_for_sim

from .shared import get_simulator, json_error_response


logger = logging.getLogger(__name__)


def sse_stream(request, building_id: int) -> StreamingHttpResponse | StreamingHttpResponse:
    try:
        sim = get_simulator(building_id)
    except Exception as e:
        return json_error_response(str(e), 404)

    def event_stream():
        try:
            while True:
                eventlet.sleep(5)
                payload = build_live_payload_for_sim(sim)
                yield f"data: {json.dumps(payload)}\n\n"
                while sim.pending_notifications:
                    notif = sim.pending_notifications.popleft()
                    yield f"event: notification\ndata: {json.dumps(notif)}\n\n"
        except (GeneratorExit, IOError, OSError):
            logger.info("Cliente SSE desconectado del edificio %s", building_id)

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
