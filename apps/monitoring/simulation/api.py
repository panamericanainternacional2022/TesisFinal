import json
import logging
from typing import Any

from django.http import JsonResponse

from apps.buildings.models import MonitoringEquipment, UserBuilding
from apps.alerts.models import Notification

from .shared import get_simulator, get_first_simulator, json_error_response


logger = logging.getLogger(__name__)


def api_status(request) -> JsonResponse:
    building_id = request.GET.get("edificio_id")
    if building_id:
        try:
            building_id = int(building_id)
        except (ValueError, TypeError):
            return json_error_response("edificio_id inválido")
    else:
        first_sim = get_first_simulator()
        if not first_sim:
            return json_error_response("No hay simuladores activos", 404)
        building_id = first_sim.edificio_id

    try:
        sim = get_simulator(building_id)
    except Exception as e:
        return json_error_response(str(e), 404)

    from apps.sensors.payload import build_live_payload_for_sim
    return JsonResponse(build_live_payload_for_sim(sim))


def api_buildings(request) -> JsonResponse:
    data: list[dict[str, Any]] = []
    from apps.sensors.simulation.globals import simulators

    for equipment in MonitoringEquipment.objects.select_related("building").all():
        if not equipment.building:
            continue
        building = equipment.building
        sim = simulators.get(building.pk)
        data.append({
            "id": building.pk,
            "nombre": building.name,
            "direccion": building.address or "",
            "rif": building.rif or "",
            "tipo": equipment.equipment_type,
            "simulador_activo": sim is not None,
            "sim_paused": sim.sim_paused if sim else False,
        })
    return JsonResponse(data, safe=False)


def api_building_users(request, building_id: int) -> JsonResponse:
    user_buildings = UserBuilding.objects.filter(
        building_id=building_id
    ).select_related("user__id_persona")

    data: list[dict[str, Any]] = []
    for ub in user_buildings:
        person = ub.user.id_persona if ub.user else None
        data.append({
            "id": ub.user.pk if ub.user else None,
            "nombre": f"{person.name} {person.last_name}" if person else "Desconocido",
            "email": person.email if person else "",
        })
    return JsonResponse(data, safe=False)


def api_notifications(request) -> JsonResponse:
    qs = Notification.objects.select_related(
        "monitoring_equipment__building"
    ).order_by("-fecha")[:50]

    data: list[dict[str, Any]] = []
    for notification in qs:
        msg = notification.message or {}
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except (json.JSONDecodeError, TypeError):
                msg = {"raw": msg}
        elif not isinstance(msg, dict):
            msg = {"raw": str(msg)}
        data.append({
            "id": notification.id,
            "timestamp": notification.date.isoformat() if notification.date else "",
            "variable": msg.get("variable", ""),
            "value": msg.get("value"),
            "risk": msg.get("risk", ""),
            "message": msg.get("action", msg.get("raw", json.dumps(msg, ensure_ascii=False))),
            "edificio": notification.monitoring_equipment.building.name
            if notification.monitoring_equipment and notification.monitoring_equipment.building
            else None,
        })
    return JsonResponse(data, safe=False)
