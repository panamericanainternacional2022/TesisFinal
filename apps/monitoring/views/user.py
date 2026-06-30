from django.shortcuts import render
from django.http import HttpResponse

from apps.core.auth_decorators import login_required
from apps.core.services.http_request import get_building_id_param
from apps.buildings.models import Building

from .shared import build_monitoring_config, get_user_building_ids
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
        "dashboard/panel/monitoreo_dashboard.html",
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




