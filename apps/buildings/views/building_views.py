from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.core.auth_decorators import login_required, admin_required
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.buildings.services import (
    create_equipment_for_building, sync_equipment_for_building,
    EquipmentConfig,
)
from apps.buildings.validators import validate_building_form
from apps.users.validators import normalize_rif
from apps.buildings.views.shared import (
    build_message, pop_messages, extract_building_data,
    extract_equipment_config, build_required_errors,
    count_notifications_for_building,
)


# ─── SELECT (READ) ──────────────────────────────────────────────────


@login_required
@admin_required
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


@login_required
@admin_required
def building_list_view(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    equipamiento = request.GET.get("equipamiento", "").strip()

    buildings = Building.objects.all().prefetch_related("equipment")

    if equipamiento == "bomba":
        buildings = buildings.filter(equipment__equipment_type="bomba")
    elif equipamiento == "elevador":
        buildings = buildings.filter(equipment__equipment_type="elevador")

    if query:
        buildings = buildings.filter(
            Q(name__icontains=query)
            | Q(rif__icontains=query)
            | Q(address__icontains=query)
        )

    buildings = buildings.distinct()
    msgs = pop_messages(request)
    return render(
        request,
        "buildings/lista_edificios.html",
        {
            "buildings": list(buildings),
            "page_messages": msgs,
            "current_equipamiento": equipamiento,
        },
    )


# ─── CREATE ─────────────────────────────────────────────────────────


@login_required
@admin_required
def register_building_view(request: HttpRequest) -> HttpResponse:
    building_data = {}
    form_errors = {}
    config = EquipmentConfig()

    if request.method == "POST":
        data = extract_building_data(request)
        if data.get("rif"):
            data["rif"] = normalize_rif(data["rif"])
        building_data = data
        config = extract_equipment_config(request)

        if not (data["name"] and data["rif"] and data["address"]):
            messages.error(request, "Complete el nombre, la dirección y el RIF del edificio.")
            form_errors = build_required_errors(data)
        else:
            form_errors = validate_building_form({
                "nombreEdificio": data["name"],
                "direccion": data["address"],
                "rif": data["rif"],
            })
            if form_errors:
                messages.error(request, "Por favor, corrige los errores en el formulario.")
            else:
                with transaction.atomic():
                    building = Building.objects.create(
                        name=data["name"], rif=data["rif"], address=data["address"],
                    )
                    create_equipment_for_building(building, config)
                messages.success(request, "Edificio registrado correctamente.")
                return redirect("building_list")

    return render(
        request,
        "buildings/registro_edificio.html",
        {
            "editing": False,
            "form_errors": form_errors,
            "building": building_data,
            "has_pump": config.has_pump,
            "has_elevator": config.has_elevator,
        },
    )


# ─── UPDATE ─────────────────────────────────────────────────────────


@login_required
@admin_required
def edit_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    form_errors = {}

    equipment_types = set(building.equipment.values_list("equipment_type", flat=True))
    has_pump = MonitoringEquipment.TYPE_PUMP in equipment_types
    has_elevator = MonitoringEquipment.TYPE_ELEVATOR in equipment_types

    if request.method == "POST":
        data = extract_building_data(request)
        if data.get("rif"):
            data["rif"] = normalize_rif(data["rif"])

        building.name = data["name"]
        building.address = data["address"]
        building.rif = data["rif"]

        has_pump = request.POST.get("con_bomba") == "true"
        has_elevator = request.POST.get("con_elevador") == "true"
        config = EquipmentConfig(has_pump=has_pump, has_elevator=has_elevator)

        if not (data["name"] and data["rif"] and data["address"]):
            messages.error(request, "Complete el nombre, la dirección y el RIF del edificio.")
            form_errors = build_required_errors(data)
        else:
            form_errors = validate_building_form(
                {
                    "nombreEdificio": data["name"],
                    "direccion": data["address"],
                    "rif": data["rif"],
                },
                exclude_building_id=building.id,
            )
            if form_errors:
                messages.error(request, "Por favor, corrige los errores en el formulario.")
            else:
                with transaction.atomic():
                    building.save()
                    sync_equipment_for_building(building, config)
                messages.success(request, "Edificio actualizado correctamente.")
                return redirect("building_list")

    return render(
        request,
        "buildings/registro_edificio.html",
        {
            "editing": True,
            "building": building,
            "form_errors": form_errors,
            "has_pump": has_pump,
            "has_elevator": has_elevator,
        },
    )


# ─── DELETE ─────────────────────────────────────────────────────────


@login_required
@admin_required
def delete_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    if request.method == "POST" and request.POST.get("confirmed") == "1":
        return _execute_delete(request, building)
    return _render_delete_confirmation(request, building)


# ─── PRIVATE HELPERS ────────────────────────────────────────────────


def _execute_delete(request: HttpRequest, building: Building) -> HttpResponse:
    from apps.alerts.models import Notification
    with transaction.atomic():
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
    notifications = count_notifications_for_building(building.id)
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


def check_rif_uniqueness_view(request: HttpRequest) -> JsonResponse:
    rif = request.GET.get("rif", "").strip()
    exclude_id = request.GET.get("exclude_id", "").strip()
    exclude_building_id = int(exclude_id) if exclude_id.isdigit() else None

    if not rif:
        return JsonResponse({"exists": False})

    from apps.buildings.validators import validate_unique_rif
    from apps.users.validators import normalize_rif
    from django.core.exceptions import ValidationError

    normalized = normalize_rif(rif)
    try:
        validate_unique_rif(normalized, exclude_building_id)
        exists = False
        error = ""
    except ValidationError as e:
        exists = True
        error = str(e)

    return JsonResponse({"exists": exists, "error": error})
