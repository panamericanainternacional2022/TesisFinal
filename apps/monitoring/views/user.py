from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator

from apps.core.auth_decorators import login_required
from apps.core.services.http_request import get_building_id_param
from apps.buildings.models import Building

from .shared import (
    build_monitoring_config, get_user_building_ids,
    filter_date_range, parse_notifications,
    extract_variables, extract_severities, filter_severity_python,
    filter_by_variable, build_query_string,
)
from apps.sensors.sensor_config import (
    RISK_CRITICO, RISK_ALTO, RISK_INFORMATIVO, RISK_NORMAL,
    PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS, FAULT_NAMES_ES, PAGE_SIZE,
)


@login_required
def render_user_monitoring(request) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    user_id = request.session.get("usuario_id")

    user_building_ids = get_user_building_ids(user_id)
    edificios = list(Building.objects.filter(pk__in=user_building_ids))
    
    building_id_raw = get_building_id_param(request, "edificio", "edificio_id")
    if building_id_raw and building_id_raw.isdigit():
        building_id = int(building_id_raw)
        if building_id not in user_building_ids:
            building_id = edificios[0].pk if edificios else 0
    else:
        building_id = edificios[0].pk if edificios else 0

    return render(
        request,
        "monitoring/monitoreo_dashboard.html",
        {
            "rol": rol,
            "edificios": edificios,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": False,
            "RISK_CRITICO": RISK_CRITICO, "RISK_ALTO": RISK_ALTO,
            "RISK_INFORMATIVO": RISK_INFORMATIVO, "RISK_NORMAL": RISK_NORMAL,
            "PUMP_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in PUMP_FAULT_KEYS],
            "ELEVATOR_FAULT_OPTIONS": [(k, FAULT_NAMES_ES[k]) for k in ELEVATOR_FAULT_KEYS],
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
    notifications, _ = _build_notification_query(user_id, rol, building_id)

    notifications = filter_date_range(notifications, period, date_from, date_to)

    notifications = (
        notifications
        .select_related("user", "monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    parsed_list = parse_notifications(notifications)

    all_variables = extract_variables(parsed_list)
    available_severities = extract_severities(parsed_list)

    parsed_list = filter_severity_python(parsed_list, severity)
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
            "ALL_SEVERITIES": available_severities,
            "rol": rol,
            "total_count": len(parsed_list),
            "periodo_seleccionado": period,
            "RISK_CRITICO": RISK_CRITICO, "RISK_ALTO": RISK_ALTO,
            "RISK_INFORMATIVO": RISK_INFORMATIVO, "RISK_NORMAL": RISK_NORMAL,
        },
    )

