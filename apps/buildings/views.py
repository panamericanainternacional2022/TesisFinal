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
from apps.buildings.shared import (
    build_message, pop_messages, extract_building_data,
    extract_equipment_config, build_required_errors,
)


@login_required
@admin_required
def building_list_view(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    equipamiento = request.GET.get("equipamiento", "").strip()

    buildings = Building.objects.all().prefetch_related("equipment")

    if equipamiento == "elevador":
        buildings = buildings.filter(equipment__equipment_type="elevador")

    if query:
        buildings = buildings.filter(
            Q(name__icontains=query)
            | Q(rif__icontains=query)
        )

    buildings = buildings.distinct()
    msgs = pop_messages(request)
    return render(
        request,
        "buildings/building_list.html",
        {
            "buildings": list(buildings),
            "page_messages": msgs,
            "current_equipamiento": equipamiento,
        },
    )


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

        if not (data["name"] and data["rif"] and data["address"] and data.get("floors")):
            messages.error(request, "Complete el nombre, la dirección, el RIF y la cantidad de pisos del edificio.")
            form_errors = build_required_errors(data)
        else:
            form_errors = validate_building_form({
                "nombreEdificio": data["name"],
                "direccion": data["address"],
                "rif": data["rif"],
                "cantidadPisos": data.get("floors"),
            })
            if not form_errors:
                try:
                    floors_val = int(data["floors"])
                    if config.has_elevator and floors_val <= 1:
                        form_errors["cantidadPisos"] = "Un edificio de 1 piso no puede tener elevador."
                except (ValueError, TypeError):
                    form_errors["cantidadPisos"] = "La cantidad de pisos debe ser un número entero."
            if form_errors:
                messages.error(request, "Corrija los errores indicados en el formulario.")
            else:
                with transaction.atomic():
                    building = Building.objects.create(
                        name=data["name"], rif=data["rif"], address=data["address"],
                        floors=int(data["floors"]),
                    )
                    create_equipment_for_building(building, config)
                messages.success(request, "Edificio registrado correctamente.")
                return redirect("building_list")

    return render(
        request,
        "buildings/building_register.html",
        {
            "editing": False,
            "form_errors": form_errors,
            "building": building_data,
            "has_elevator": config.has_elevator,
        },
    )


@login_required
@admin_required
def edit_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    form_errors = {}

    equipment_types = set(building.equipment.values_list("equipment_type", flat=True))
    has_elevator = MonitoringEquipment.TYPE_ELEVATOR in equipment_types

    if request.method == "POST":
        data = extract_building_data(request)
        if data.get("rif"):
            data["rif"] = normalize_rif(data["rif"])

        has_elevator = request.POST.get("con_elevador") == "true"
        config = EquipmentConfig(has_elevator=has_elevator)

        if not (data["name"] and data["rif"] and data["address"] and data.get("floors")):
            messages.error(request, "Complete el nombre, la dirección, el RIF y la cantidad de pisos del edificio.")
            form_errors = build_required_errors(data)
        else:
            form_errors = validate_building_form(
                {
                    "nombreEdificio": data["name"],
                    "direccion": data["address"],
                    "rif": data["rif"],
                    "cantidadPisos": data.get("floors"),
                },
                exclude_building_id=building.id,
            )
            if not form_errors:
                try:
                    floors_val = int(data["floors"])
                    if config.has_elevator and floors_val <= 1:
                        form_errors["cantidadPisos"] = "Un edificio de 1 piso no puede tener elevador."
                except (ValueError, TypeError):
                    form_errors["cantidadPisos"] = "La cantidad de pisos debe ser un número entero."
            if form_errors:
                messages.error(request, "Corrija los errores indicados en el formulario.")
            else:
                with transaction.atomic():
                    building.name = data["name"]
                    building.address = data["address"]
                    building.rif = data["rif"]
                    building.floors = int(data["floors"])
                    building.save()
                    sync_equipment_for_building(building, config)
                messages.success(request, "Edificio actualizado correctamente.")
                return redirect("building_list")

    return render(
        request,
        "buildings/building_register.html",
        {
            "editing": True,
            "building": building,
            "form_errors": form_errors,
            "has_elevator": has_elevator,
        },
    )


@login_required
@admin_required
def delete_building_view(request: HttpRequest, building_id: int) -> HttpResponse:
    building = get_object_or_404(Building, id=building_id)
    from apps.events.models import Notification
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
        "El edificio y todos sus datos asociados se eliminaron correctamente.",
    )
    return redirect("building_list")


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
