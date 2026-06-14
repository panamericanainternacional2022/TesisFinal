from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator

from apps.core.auth_decorators import login_required, admin_required
from apps.buildings.models import Building
from apps.alerts.models import Notification

from .shared import (
    build_monitoring_config, filter_severity, filter_date_range,
    build_query_string, parse_notifications, extract_variables,
    filter_by_variable, ALL_SEVERITIES,
)
from apps.sensors.sensor_config import RISK_CRITICO, RISK_ALTO, RISK_MEDIO, RISK_BAJO, RISK_INFO


@login_required
def render_admin_monitoring(request) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    buildings = list(Building.objects.all())

    building_id = request.GET.get("edificio") or request.GET.get("edificio_id")
    valid_ids = [b.pk for b in buildings]
    if building_id:
        try:
            building_id = int(building_id)
            if building_id not in valid_ids:
                building_id = valid_ids[0] if valid_ids else 0
        except (ValueError, TypeError, IndexError):
            building_id = valid_ids[0] if valid_ids else 0
    else:
        from apps.sensors.simulation.globals import simulators
        if simulators:
            building_id = next(iter(simulators.keys()))
            if building_id not in valid_ids:
                building_id = valid_ids[0] if valid_ids else 0
        else:
            building_id = valid_ids[0] if valid_ids else 0

    return render(
        request,
        "monitoring/monitoreo_dashboard.html",
        {
            "rol": rol,
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
        },
    )


@login_required
@admin_required
def building_monitoring_view(request, building_id: int) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    building = get_object_or_404(Building, pk=building_id)
    return render(
        request,
        "monitoring/monitoreo.html",
        {
            "rol": rol,
            "selected_edificio": building,
            "equipos_data": [],
            "query": "",
            "edificio_id": building_id,
        },
    )


@login_required
def render_admin_history(request) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    building_id = (request.GET.get("edificio") or request.GET.get("edificio_id") or "").strip()
    severity = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    period = request.GET.get("periodo", "24h").strip()
    date_from = request.GET.get("fecha_desde", "").strip()
    date_to = request.GET.get("fecha_hasta", "").strip()

    buildings = Building.objects.all()
    notifications = Notification.objects.all()

    if building_id:
        notifications = notifications.filter(monitoring_equipment__building_id=building_id)

    notifications = filter_severity(notifications, severity)
    notifications = filter_date_range(notifications, period, date_from, date_to)

    notifications = (
        notifications
        .select_related("user", "monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    parsed_list = parse_notifications(notifications)
    all_variables = extract_variables(parsed_list)
    parsed_list = filter_by_variable(parsed_list, variable_filter)

    paginator = Paginator(parsed_list, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    query_string = build_query_string(
        edificio=building_id,
        severidad=severity,
        variable=variable_filter,
        periodo=period,
        fecha_desde=date_from if period == "custom" else None,
        fecha_hasta=date_to if period == "custom" else None,
    )

    return render(
        request,
        "monitoring/historial.html",
        {
            "notificaciones": page_obj,
            "edificios": buildings,
            "selected_edificio_id": int(building_id) if building_id and building_id.isdigit() else None,
            "severidad": severity,
            "variable_filter": variable_filter,
            "all_variables": all_variables,
            "fecha_desde": date_from,
            "fecha_hasta": date_to,
            "filter_query_string": query_string,
            "ALL_SEVERITIES": ALL_SEVERITIES,
            "rol": rol,
            "total_count": len(parsed_list),
            "periodo_seleccionado": period,
            "RISK_CRITICO": RISK_CRITICO, "RISK_ALTO": RISK_ALTO,
            "RISK_MEDIO": RISK_MEDIO, "RISK_BAJO": RISK_BAJO, "RISK_INFO": RISK_INFO,
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
                simulators[building_id] = BuildingSimulator(building_id, building_name)
            simulator = simulators[building_id]
            simulator.equipment_types.add(equipment.equipment_type)
            simulator.has_pump = "bomba" in simulator.equipment_types
            simulator.has_elevator = "elevador" in simulator.equipment_types
            simulator.pump_on = simulator.has_pump
            simulator.elevator_on = simulator.has_elevator
            created_count += 1
        if created_count:
            return JsonResponse({"status": "ok", "message": f"Simuladores creados ({created_count})."})
        return JsonResponse({"status": "error", "message": "No hay equipos de monitoreo en la BD."})

    for simulator in simulators.values():
        simulator.sim_paused = False
    return JsonResponse({"status": "ok", "message": "Simulación reanudada."})


@login_required
@admin_required
def simulator_stop_view(request) -> JsonResponse:
    from apps.sensors.simulation.globals import simulators

    if not simulators:
        return JsonResponse({"status": "ok", "message": "No hay simuladores activos."})
    for simulator in simulators.values():
        simulator.sim_paused = True
    return JsonResponse({"status": "ok", "message": "Simulación pausada."})


@login_required
@admin_required
def simulator_restart_view(request) -> JsonResponse:
    from apps.sensors.simulation.globals import simulators
    from apps.sensors.simulation.controls import reset_simulator

    if not simulators:
        return JsonResponse({"status": "error", "message": "No hay simuladores activos."})
    restarted_count = 0
    for building_id in list(simulators.keys()):
        reset_simulator(building_id)
        simulators[building_id].sim_paused = False
        restarted_count += 1
    return JsonResponse({"status": "ok", "message": f"{restarted_count} simulador(es) reiniciado(s)."})
