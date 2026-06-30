import json
import logging
from typing import Any

from django.http import JsonResponse

from apps.core.services.http_response import json_error as _json_error, json_ok as _json_ok
from apps.sensors.simulation.exceptions import SimulatorError
from apps.sensors.simulation.models import BuildingSimulator


logger = logging.getLogger(__name__)


def get_simulator(building_id: int) -> BuildingSimulator | None:
    from apps.sensors.simulation.globals import simulators
    from apps.sensors.simulation.models import BuildingSimulator

    sim = simulators.get(building_id)
    if sim:
        return sim

    from apps.buildings.models import Building, MonitoringEquipment
    try:
        building = Building.objects.get(pk=building_id)
        equipos = MonitoringEquipment.objects.filter(building_id=building_id)
        if equipos.exists():
            sim = BuildingSimulator(building_id, building.name, floors=building.floors)
            for eq in equipos:
                sim.equipment_types.add(eq.equipment_type)
            sim.has_pump = "bomba" in sim.equipment_types
            sim.has_elevator = "elevador" in sim.equipment_types
            sim.pump_on = sim.has_pump
            sim.elevator_on = sim.has_elevator

            simulators[building_id] = sim
            logger.info("Simulador de edificio %s (%s) creado dinámicamente", building_id, building.name)
            return sim
    except Exception as e:
        logger.warning("Error al inicializar simulador dinámico para ID %s: %s", building_id, e)

    logger.warning("No hay simulador disponible para el ID %s", building_id)
    return None


def get_first_simulator() -> BuildingSimulator | None:
    from apps.sensors.simulation.globals import simulators
    return next(iter(simulators.values()), None)


def json_error_response(message: str, status: int = 400) -> JsonResponse:
    return _json_error(message, status)


def json_success_response(extra: dict[str, Any] | None = None) -> JsonResponse:
    return _json_ok(extra)


def parse_json_body(request) -> dict[str, Any]:
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        raise SimulatorError("JSON inválido", 400)
