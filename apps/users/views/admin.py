from typing import Any

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q

from apps.alerts.models import Notification
from apps.buildings.models import Building, UserBuilding
from apps.core.auth_decorators import login_required, admin_required
from apps.users.models import Usuario, Persona
from apps.users.services import (
    build_beneficiary_data,
    generate_random_password,
    send_activation_email,
)
from apps.users.validators import validate_user_form
from .shared import (
    extract_post_data,
    has_required_fields,
    build_required_field_errors,
    create_user_with_retry,
    build_edit_initial_data,
)


@login_required
@admin_required
def user_register_view(request: HttpRequest) -> HttpResponse:
    return render(request, "users/registro_usuario.html", {"user": {}})


@login_required
@admin_required
def beneficiary_list_view(request: HttpRequest) -> HttpResponse:
    from apps.core.auth_decorators import ADMIN_ROLES
    query = request.GET.get("q", "").strip()
    building_id = request.GET.get("edificio", "").strip()

    users = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("userbuilding_set__building")
        .exclude(rol__in=ADMIN_ROLES)
    )

    if building_id:
        users = users.filter(userbuilding__building_id=building_id)

    if query:
        users = users.filter(
            Q(id_persona__ci__icontains=query)
            | Q(id_persona__name__icontains=query)
            | Q(id_persona__last_name__icontains=query)
            | Q(id_persona__email__icontains=query)
            | Q(username__icontains=query)
            | Q(userbuilding__building__name__icontains=query)
        ).distinct()

    beneficiaries = [build_beneficiary_data(u) for u in users]
    buildings = Building.objects.all()

    return render(
        request,
        "users/lista_usuario.html",
        {
            "beneficiarios": beneficiaries,
            "edificios": buildings,
            "selected_edificio_id": int(building_id) if building_id.isdigit() else None,
        },
    )


@login_required
@admin_required
def beneficiary_create_view(request: HttpRequest) -> HttpResponse:
    generated_password = None
    user_data: dict[str, Any] = {}
    form_error: str | None = None
    form_errors: dict[str, str] = {}
    email_sent = False
    activation_link = ""

    if request.method == "POST":
        if Building.objects.count() == 0:
            form_error = "Debe registrar al menos un edificio antes de crear un beneficiario."
        else:
            post_data = extract_post_data(request)
            user_data = post_data

            if not has_required_fields(post_data):
                form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula, teléfono y edificio."
                form_errors = build_required_field_errors(post_data)
            else:
                form_errors = validate_user_form(post_data)
                if form_errors:
                    form_error = "Por favor, corrige los errores en el formulario."
                else:
                    person = Persona.objects.create(
                        ci=post_data["cedula"],
                        name=f"{post_data['primerNombre']} {post_data['segundoNombre']}".strip(),
                        last_name=f"{post_data['primerApellido']} {post_data['segundoApellido']}".strip(),
                        email=post_data["email"],
                        phone=post_data["telefono"],
                    )
                    generated_password = generate_random_password(10)

                    try:
                        user = create_user_with_retry(
                            post_data["primerNombre"],
                            post_data["primerApellido"],
                            generated_password,
                            person,
                        )
                    except ValueError:
                        form_error = "No se pudo generar un nombre de usuario. Verifica los datos ingresados."

                    if "user" in locals() and post_data.get("id_edificio"):
                        UserBuilding.objects.create(
                            user=user,
                            building_id=post_data["id_edificio"],
                        )

                    if "user" in locals():
                        activation_link = send_activation_email(
                            post_data["email"], user.id_usuario,
                            f"{'https' if request.is_secure() else 'http'}://{request.get_host()}",
                        )
                        email_sent = True

    buildings = Building.objects.all()
    context: dict[str, Any] = {
        "user": user_data,
        "edificios": buildings,
        "form_error": form_error,
        "form_errors": form_errors,
    }
    if email_sent:
        context["email_sent"] = email_sent
        context["activation_link"] = activation_link
        context["sent_to"] = post_data.get("email", "")

    return render(request, "users/registro_usuario.html", context)


@login_required
@admin_required
@transaction.atomic
def beneficiary_update_view(request: HttpRequest, beneficiary_id: int) -> HttpResponse:
    user = get_object_or_404(Usuario, id_usuario=beneficiary_id)
    person = user.id_persona
    form_error: str | None = None
    form_errors: dict[str, str] = {}

    if request.method == "POST":
        post_data = extract_post_data(request)

        if not has_required_fields(post_data):
            form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula, teléfono y edificio para actualizar."
            form_errors = build_required_field_errors(post_data)
        else:
            form_errors = validate_user_form(post_data, exclude_persona_id=person.id_persona)
            if form_errors:
                form_error = "Por favor, corrige los errores en el formulario."
            else:
                person.name = f"{post_data['primerNombre']} {post_data['segundoNombre']}".strip()
                person.last_name = f"{post_data['primerApellido']} {post_data['segundoApellido']}".strip()
                person.email = post_data["email"]
                person.ci = post_data["cedula"]
                person.phone = post_data["telefono"]
                person.save()

                UserBuilding.objects.filter(user=user).delete()
                if post_data.get("id_edificio"):
                    UserBuilding.objects.create(
                        user=user,
                        building_id=post_data["id_edificio"],
                    )

                messages.success(request, "Beneficiario actualizado correctamente.")
                return redirect("beneficiary_list")

    data = build_edit_initial_data(user, person)
    current_ue = UserBuilding.objects.filter(user=user).first()
    current_building = current_ue.building if current_ue else None
    buildings = Building.objects.all()

    return render(
        request,
        "users/registro_usuario.html",
        {
            "user": data,
            "editing": True,
            "beneficiario_id": beneficiary_id,
            "edificios": buildings,
            "edificio_actual": current_building,
            "form_error": form_error,
            "form_errors": form_errors,
        },
    )


@login_required
@admin_required
def beneficiary_delete_view(request: HttpRequest, beneficiary_id: int) -> HttpResponse:
    user = get_object_or_404(Usuario, id_usuario=beneficiary_id)
    with transaction.atomic():
        Notification.objects.filter(user=user).delete()
        UserBuilding.objects.filter(user=user).delete()
        person_id = user.id_persona_id
        user.delete()
        if person_id:
            Persona.objects.filter(id_persona=person_id).delete()
    messages.success(request, "Beneficiario eliminado correctamente.")
    return redirect("user_select", accion="eliminar")


@login_required
@admin_required
def user_select_view(request: HttpRequest, action: str) -> HttpResponse:
    from apps.core.auth_decorators import ADMIN_ROLES
    VALID_ACTIONS = ("editar", "eliminar")
    if action not in VALID_ACTIONS:
        messages.error(request, f"Acción no válida: {action}")
        return redirect("beneficiary_list")

    users = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("userbuilding_set__building")
        .exclude(rol__in=ADMIN_ROLES)
    )
    items = []
    for u in users:
        p = u.id_persona
        ue = u.userbuilding_set.first()
        building = ue.building if ue else None
        items.append(
            {
                "id": u.id_usuario,
                "nombre": f"{p.name} {p.last_name}".strip() if p else u.username,
                "cedula": p.ci if p else "",
                "edificio": building.name if building else "",
            }
        )

    return render(
        request,
        "users/seleccionar_usuario.html",
        {
            "items": items,
            "accion": action,
        },
    )
