from django.http import HttpRequest

from apps.buildings.services import EquipmentConfig


def build_message(text: str, msg_type: str) -> dict[str, str]:
    return {"text": text, "type": msg_type}


def pop_messages(request: HttpRequest, key: str = "_bld_msg") -> list:
    return request.session.pop(key, [])


def extract_building_data(request: HttpRequest) -> dict:
    return {
        "name": request.POST.get("nombreEdificio", "").strip(),
        "address": request.POST.get("direccion", "").strip(),
        "rif": request.POST.get("rif", "").strip(),
        "floors": request.POST.get("cantidadPisos", "").strip(),
    }


def extract_equipment_config(request: HttpRequest) -> EquipmentConfig:
    return EquipmentConfig(
        has_pump=request.POST.get("con_bomba") == "true",
        has_elevator=request.POST.get("con_elevador") == "true",
    )


def build_required_errors(data: dict) -> dict[str, str]:
    errors = {}
    if not data["name"]:
        errors["nombreEdificio"] = "Este campo es obligatorio."
    if not data["rif"]:
        errors["rif"] = "Este campo es obligatorio."
    if not data["address"]:
        errors["direccion"] = "Este campo es obligatorio."
    if not data.get("floors"):
        errors["cantidadPisos"] = "Este campo es obligatorio."
    return errors


def count_notifications_for_building(building_id: int) -> int:
    from apps.alerts.models import Notification
    return Notification.objects.filter(
        monitoring_equipment__building_id=building_id,
    ).count()
