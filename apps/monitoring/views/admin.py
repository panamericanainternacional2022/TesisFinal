from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.core.services.http_request import get_building_id_param
from apps.buildings.models import Building

from .shared import build_monitoring_config
from apps.sensors.sensor_config import (
    RISK_CRITICO, RISK_ALTO, RISK_INFORMATIVO, RISK_NORMAL,
    PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS, FAULT_NAMES_ES, PAGE_SIZE,
)


@login_required
def render_admin_monitoring(request) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    buildings = list(Building.objects.all())

    building_id = get_building_id_param(request, "edificio", "edificio_id")
    valid_ids = [b.pk for b in buildings]
    if building_id:
        try:
            building_id = int(building_id)
            if building_id not in valid_ids:
                building_id = valid_ids[0] if valid_ids else 0
        except (ValueError, TypeError, IndexError):
            building_id = valid_ids[0] if valid_ids else 0
    else:
        building_id = valid_ids[0] if valid_ids else 0

    return render(
        request,
        "dashboard/panel/monitoreo_dashboard.html",
        {
            "rol": rol,
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": True,
            "RISK_CRITICO": RISK_CRITICO, "RISK_ALTO": RISK_ALTO,
            "RISK_INFORMATIVO": RISK_INFORMATIVO, "RISK_NORMAL": RISK_NORMAL,
            "PUMP_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in PUMP_FAULT_KEYS],
            "ELEVATOR_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in ELEVATOR_FAULT_KEYS],
        },
    )


@login_required
def render_admin_thresholds(request) -> HttpResponse:

    rol = request.session.get("usuario_rol", "US")
    buildings = list(Building.objects.all())

    building_id = get_building_id_param(request, "edificio", "edificio_id")
    valid_ids = [b.pk for b in buildings]
    if building_id:
        try:
            building_id = int(building_id)
            if building_id not in valid_ids:
                building_id = valid_ids[0] if valid_ids else 0
        except (ValueError, TypeError, IndexError):
            building_id = valid_ids[0] if valid_ids else 0
    else:
        building_id = valid_ids[0] if valid_ids else 0

    return render(
        request,
        "dashboard/umbrales/umbrales.html",
        {
            "rol": rol,
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": True,
        },
    )


@login_required
def render_admin_limits(request) -> HttpResponse:

    rol = request.session.get("usuario_rol", "US")
    buildings = list(Building.objects.all())

    building_id = get_building_id_param(request, "edificio", "edificio_id")
    valid_ids = [b.pk for b in buildings]
    if building_id:
        try:
            building_id = int(building_id)
            if building_id not in valid_ids:
                building_id = valid_ids[0] if valid_ids else 0
        except (ValueError, TypeError, IndexError):
            building_id = valid_ids[0] if valid_ids else 0
    else:
        building_id = valid_ids[0] if valid_ids else 0

    return render(
        request,
        "dashboard/limites/limites.html",
        {
            "rol": rol,
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": True,
        },
    )


@login_required
@admin_required
def building_monitoring_view(request, building_id: int) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    building = get_object_or_404(Building, pk=building_id)
    return render(
        request,
        "dashboard/panel/monitoreo_dashboard.html",
        {
            "rol": rol,
            "edificios": [building],
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": True,
            "RISK_CRITICO": RISK_CRITICO, "RISK_ALTO": RISK_ALTO,
            "RISK_INFORMATIVO": RISK_INFORMATIVO, "RISK_NORMAL": RISK_NORMAL,
            "PUMP_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in PUMP_FAULT_KEYS],
            "ELEVATOR_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in ELEVATOR_FAULT_KEYS],
        },
    )




@login_required
def simulator_status_view(request) -> JsonResponse:
    from apps.sensors.simulation.globals import simulators

    has_buildings = Building.objects.exists()
    has_simulator = len(simulators) > 0
    return JsonResponse({"running": has_simulator, "has_edificios": has_buildings})


@login_required
@admin_required
def simulator_start_view(request) -> JsonResponse:
    from apps.sensors.simulation.globals import simulators
    from apps.sensors.simulation.models import BuildingSimulator
    from apps.buildings.models import MonitoringEquipment

    if not simulators:
        created_count = 0
        for equipment in MonitoringEquipment.objects.select_related("building").all():
            if not equipment.building:
                continue
            building_id = equipment.building.pk
            building_name = equipment.building.name or f"Edificio #{building_id}"
            if building_id not in simulators:
                simulators[building_id] = BuildingSimulator(building_id, building_name, floors=equipment.building.floors)
            simulator = simulators[building_id]
            simulator.equipment_types.add(equipment.equipment_type)
            simulator.has_pump = "bomba" in simulator.equipment_types
            simulator.has_elevator = "elevador" in simulator.equipment_types
            simulator.pump_on = simulator.has_pump
            simulator.elevator_on = simulator.has_elevator
            created_count += 1
        if created_count:
            return json_ok({"message": f"Simuladores creados ({created_count})."})
        return json_error("No hay equipos de monitoreo en la BD.")

    for simulator in simulators.values():
        simulator.sim_paused = False
    return json_ok({"message": "Simulación reanudada."})


@login_required
@admin_required
def simulator_stop_view(request) -> JsonResponse:
    from apps.sensors.simulation.globals import simulators

    if not simulators:
        return json_ok({"message": "No hay simuladores activos."})
    for simulator in simulators.values():
        simulator.sim_paused = True
    return json_ok({"message": "Simulación pausada."})


@login_required
@admin_required
def simulator_restart_view(request) -> JsonResponse:
    from apps.sensors.simulation.globals import simulators
    from apps.sensors.simulation.controls import reset_simulator

    if not simulators:
        return json_error("No hay simuladores activos.")
    restarted_count = 0
    for building_id in list(simulators.keys()):
        reset_simulator(building_id)
        simulators[building_id].sim_paused = False
        restarted_count += 1
    return json_ok({"message": f"{restarted_count} simulador(es) reiniciado(s)."})
