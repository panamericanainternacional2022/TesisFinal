import json
import logging
from typing import Any

from django.http import JsonResponse

from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.exceptions import SimulatorError
from apps.sensors.simulation.models import BuildingSimulator


logger = logging.getLogger(__name__)


def get_simulator(building_id: int) -> BuildingSimulator:
    sim = simulators.get(building_id)
    if not sim:
        raise SimulatorError(f"Simulador no encontrado para edificio {building_id}", 404)
    return sim


def get_first_simulator() -> BuildingSimulator | None:
    return next(iter(simulators.values()), None)


def json_error_response(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"status": "error", "message": message}, status=status)


def json_success_response(extra: dict[str, Any] | None = None) -> JsonResponse:
    resp: dict[str, Any] = {"status": "ok"}
    if extra:
        resp.update(extra)
    return JsonResponse(resp)


def parse_json_body(request) -> dict[str, Any]:
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        raise SimulatorError("JSON inválido", 400)
