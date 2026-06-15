from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q

from apps.core.auth_decorators import login_required
from apps.buildings.models import Building, MonitoringEquipment
from apps.alerts.models import Notification

from apps.core.services.http_request import get_building_id_param

from .shared import (
    build_monitoring_config, filter_severity, filter_date_range,
    build_query_string, parse_notifications, extract_variables,
    filter_by_variable, get_user_building_ids, get_equipment_sensors,
    ALL_SEVERITIES,
)
from apps.sensors.sensor_config import RISK_CRITICO, RISK_ALTO, RISK_MEDIO, RISK_BAJO, RISK_INFO, PAGE_SIZE


@login_required
def render_user_monitoring(request) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    user_id = request.session.get("usuario_id")
    query = request.GET.get("q", "").strip()

    user_building_ids = get_user_building_ids(user_id)
    equipment_list = MonitoringEquipment.objects.filter(
        building_id__in=user_building_ids
    ).select_related("building")

    if query:
        equipment_list = equipment_list.filter(
            Q(building__name__icontains=query)
            | Q(building__rif__icontains=query)
        )

    data = []
    first_building_id = 0
    for equipment in equipment_list:
        sensors = get_equipment_sensors(equipment)
        data.append({
            "equipo": equipment,
            "edificio": equipment.building,
            "status": equipment.get_status_display(),
            "sensores": sensors,
        })
        if first_building_id == 0:
            first_building_id = equipment.building.pk

    return render(
        request,
        "monitoring/monitoreo.html",
        {
            "equipos_data": data,
            "rol": rol,
            "query": query,
            "edificio_id": first_building_id,
            "config_json": build_monitoring_config(first_building_id),
        },
    )


@login_required
def render_user_history(request) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    user_id = request.session.get("usuario_id")

    building_id = get_building_id_param(request, "edificio", "edificio_id")
    severity = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    period = request.GET.get("periodo", "24h").strip()
    date_from = request.GET.get("fecha_desde", "").strip()
    date_to = request.GET.get("fecha_hasta", "").strip()

    user_building_ids = get_user_building_ids(user_id)
    buildings = Building.objects.filter(pk__in=user_building_ids)

    from apps.alerts.views.shared import _build_notification_query
    notifications, _ = _build_notification_query(user_id, "US", building_id)

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

    paginator = Paginator(parsed_list, PAGE_SIZE)
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

