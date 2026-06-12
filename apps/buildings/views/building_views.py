from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.core.auth_decorators import _login_required, _admin_required
from apps.alerts.models import Notification
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.buildings.services import (
    create_equipment_for_building, sync_equipment_for_building,
    EquipmentConfig,
)
from apps.buildings.validators import validate_building_form
from apps.buildings.views.shared import build_message, pop_messages


# ─── SELECT (READ) ──────────────────────────────────────────────────


@_login_required
@_admin_required
def select_building_view(request: HttpRequest, action: str) -> HttpResponse:
    VALID_ACTIONS = ("edit", "delete")
    if action not in VALID_ACTIONS:
        messages.error(request, f"Acción no válida: {action}")
        return redirect("building_list")
    buildings = Building.objects.all()
    items = [
        {"id": b.id, "name": b.name, "rif": b.rif}
        for b in buildings
    ]
    return render(
        request,
        "buildings/seleccionar_edificio.html",
        {"items": items, "action": action},
    )


@_login_required
@_admin_required
def building_list_view(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    buildings = Building.objects.all().prefetch_related("equipment")
    if query:
        buildings = buildings.filter(
            Q(name__icontains=query)
            | Q(rif__icontains=query)
            | Q(address__icontains=query)
        )
    msgs = pop_messages(request)
    return render(
        request,
        "buildings/lista_edificios.html",
        {"buildings": list(buildings), "page_messages": msgs},
    )


# ─── CREATE ─────────────────────────────────────────────────────────


@_login_required
@_admin_required
def register_building_view(request: HttpRequest) -> HttpResponse:
    msgs = pop_messages(request)
    if request.method == "POST":
        return _handle_register_post(request, msgs)
    return _render_register_form(request, msgs, {}, {}, EquipmentConfig())


# ─── UPDATE ─────────────────────────────────────────────────────────


@_login_required
@_admin_required
def edit_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    msgs = pop_messages(request)
    if request.method == "POST":
        return _handle_edit_post(request, building, msgs)

    equipment_types = set(building.equipment.values_list("equipment_type", flat=True))
    config = EquipmentConfig(
        has_pump=MonitoringEquipment.TYPE_PUMP in equipment_types,
        has_elevator=MonitoringEquipment.TYPE_ELEVATOR in equipment_types,
    )
    return render(
        request,
        "buildings/registro_edificio.html",
        {
            "editing": True,
            "building": building,
            "page_messages": msgs,
            "form_errors": {},
            "has_pump": config.has_pump,
            "has_elevator": config.has_elevator,
        },
    )


# ─── DELETE ─────────────────────────────────────────────────────────


@_login_required
@_admin_required
def delete_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    if request.method == "POST" and request.POST.get("confirmed") == "1":
        return _execute_delete(request, building)
    return _render_delete_confirmation(request, building)


# ─── PRIVATE HELPERS ────────────────────────────────────────────────


def _extract_building_data(request: HttpRequest) -> dict:
    return {
        "name": request.POST.get("nombreEdificio", "").strip(),
        "address": request.POST.get("parroquia", "").strip(),
        "rif": request.POST.get("rif", "").strip(),
    }


def _extract_equipment_config(request: HttpRequest) -> EquipmentConfig:
    return EquipmentConfig(
        has_pump=request.POST.get("con_bomba") == "true",
        has_elevator=request.POST.get("con_elevador") == "true",
    )


def _build_required_errors(data: dict) -> dict[str, str]:
    errors = {}
    if not data["name"]:
        errors["nombreEdificio"] = "Este campo es obligatorio."
    if not data["rif"]:
        errors["rif"] = "Este campo es obligatorio."
    if not data["address"]:
        errors["direccion"] = "Este campo es obligatorio."
    return errors


def _handle_register_post(
    request: HttpRequest, msgs: list,
) -> HttpResponse:
    data = _extract_building_data(request)
    config = _extract_equipment_config(request)

    if not (data["name"] and data["rif"] and data["address"]):
        msgs.append(build_message(
            "Complete el nombre, la dirección y el RIF del edificio.",
            "error",
        ))
        return _render_register_form(
            request, msgs, _build_required_errors(data), data, config,
        )

    form_errors = validate_building_form({
        "nombreEdificio": data["name"],
        "direccion": data["address"],
        "rif": data["rif"],
    })
    if form_errors:
        msgs.append(build_message(
            "Por favor, corrige los errores en el formulario.", "error",
        ))
        return _render_register_form(
            request, msgs, form_errors, data, config,
        )

    building = Building.objects.create(
        name=data["name"], rif=data["rif"], address=data["address"],
    )
    create_equipment_for_building(building, config)
    request.session["_bld_msg"] = [
        build_message("Edificio registrado correctamente.", "success")]
    return redirect("building_list")


def _render_register_form(
    request: HttpRequest, msgs: list, form_errors: dict,
    data: dict, config: EquipmentConfig,
) -> HttpResponse:
    return render(
        request,
        "buildings/registro_edificio.html",
        {
            "editing": False,
            "page_messages": msgs,
            "form_errors": form_errors,
            "building": data,
            "has_pump": config.has_pump,
            "has_elevator": config.has_elevator,
        },
    )


def _handle_edit_post(
    request: HttpRequest, building: Building, msgs: list,
) -> HttpResponse:
    data = _extract_building_data(request)
    config = _extract_equipment_config(request)

    building.name = data["name"]
    building.address = data["address"]
    building.rif = data["rif"]

    if not (data["name"] and data["rif"] and data["address"]):
        msgs.append(build_message(
            "Complete el nombre, la dirección y el RIF del edificio.",
            "error",
        ))
        return _render_register_form(
            request, msgs, _build_required_errors(data), data, config,
        )

    form_errors = validate_building_form(
        {
            "nombreEdificio": data["name"],
            "direccion": data["address"],
            "rif": data["rif"],
        },
        exclude_building_id=building.id,
    )
    if form_errors:
        msgs.append(build_message(
            "Por favor, corrige los errores en el formulario.", "error",
        ))
        return _render_register_form(
            request, msgs, form_errors, data, config,
        )

    building.save()
    sync_equipment_for_building(building, config)
    request.session["_bld_msg"] = [
        build_message("Edificio actualizado correctamente.", "success")]
    return redirect("building_list")


def _execute_delete(request: HttpRequest, building: Building) -> HttpResponse:
    from apps.alerts.models import Notification
    equipment = list(building.equipment.all())
    Notification.objects.filter(
        monitoring_equipment__building=building,
    ).delete()
    for eq in equipment:
        eq.delete()
    UserBuilding.objects.filter(building=building).delete()
    building.delete()
    messages.success(
        request,
        "Edificio y todos sus datos asociados fueron eliminados correctamente.",
    )
    return redirect("select_building", action="delete")


def _render_delete_confirmation(
    request: HttpRequest, building: Building,
) -> HttpResponse:
    equipment = MonitoringEquipment.objects.filter(building=building)
    user_assignments = UserBuilding.objects.filter(building=building)
    notifications = _count_notifications_for_building(building)
    return render(
        request,
        "buildings/confirmar_eliminar_edificio.html",
        {
            "building": building,
            "equipment": list(equipment),
            "usuarios_count": user_assignments.count(),
            "notifications_count": notifications,
        },
    )


def _count_notifications_for_building(building: Building) -> int:
    from apps.alerts.models import Notification
    return Notification.objects.filter(
        monitoring_equipment__building=building,
    ).count()
