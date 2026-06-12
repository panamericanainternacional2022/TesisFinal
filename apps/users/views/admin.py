from typing import Any

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db import transaction, IntegrityError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.alerts.models import Notification
from apps.buildings.models import Building, UserBuilding
from apps.core.auth_decorators import _login_required, _admin_required, ADMIN_ROLES
from apps.users.models import Usuario, Persona
from apps.users.services import (
    build_beneficiary_data,
    build_random_username,
    generate_random_password,
    send_activation_email,
)
from apps.users.validators import validate_user_form
from django.db.models import Q


@_login_required
@_admin_required
def user_registration_view(request: HttpRequest) -> HttpResponse:
    return render(request, "users/registro_usuario.html", {"user": {}})


@_login_required
@_admin_required
def beneficiary_list_view(request: HttpRequest) -> HttpResponse:
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


@_login_required
@_admin_required
@transaction.atomic
def beneficiary_create_view(request: HttpRequest) -> HttpResponse:
    generated_username = None
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
            post_data = _extract_post_data(request)
            user_data = post_data

            if not _has_required_fields(post_data):
                form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula, teléfono y edificio."
                form_errors = _build_required_field_errors(post_data)
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
                        user = _create_user_with_retry(
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
                        protocol = "https" if request.is_secure() else "http"
                        host = request.get_host()
                        base_url = f"{protocol}://{host}"
                        try:
                            activation_link = send_activation_email(
                                post_data["email"], user.id_usuario, base_url
                            )
                            email_sent = True
                        except RuntimeError as e:
                            activation_link = str(e)

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


@_login_required
@_admin_required
@transaction.atomic
def beneficiary_update_view(request: HttpRequest, beneficiary_id: int) -> HttpResponse:
    user = get_object_or_404(Usuario, id_usuario=beneficiary_id)
    person = user.id_persona
    form_error: str | None = None
    form_errors: dict[str, str] = {}

    if request.method == "POST":
        post_data = _extract_post_data(request)

        if not _has_required_fields(post_data):
            form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula, teléfono y edificio para actualizar."
            form_errors = _build_required_field_errors(post_data)
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
                return redirect("lista_usuario")

    data = _build_edit_initial_data(user, person)
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


@_login_required
@_admin_required
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
    return redirect("seleccionar_usuario", accion="eliminar")


@_login_required
@_admin_required
def user_select_view(request: HttpRequest, action: str) -> HttpResponse:
    VALID_ACTIONS = ("editar", "eliminar")
    if action not in VALID_ACTIONS:
        messages.error(request, f"Acción no válida: {action}")
        return redirect("lista_usuario")

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


# ═══════════════════════════════════════════════════════════════════════
# Private helpers
# ═══════════════════════════════════════════════════════════════════════

def _extract_post_data(request: HttpRequest) -> dict[str, Any]:
    return {
        "primerNombre": request.POST.get("primerNombre", "").strip(),
        "segundoNombre": request.POST.get("segundoNombre", "").strip(),
        "primerApellido": request.POST.get("primerApellido", "").strip(),
        "segundoApellido": request.POST.get("segundoApellido", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "cedula": request.POST.get("cedula", "").strip(),
        "telefono": request.POST.get("telefono", "").strip(),
        "id_edificio": request.POST.get("id_edificio", "").strip(),
    }


def _has_required_fields(data: dict[str, Any]) -> bool:
    return bool(
        data.get("primerNombre")
        and data.get("primerApellido")
        and data.get("email")
        and data.get("cedula")
        and data.get("id_edificio")
        and data.get("telefono")
    )


def _build_required_field_errors(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    required = (
        "primerNombre",
        "primerApellido",
        "email",
        "cedula",
        "telefono",
        "id_edificio",
    )
    for key in required:
        if not data.get(key):
            errors[key] = "Este campo es obligatorio."
    return errors


def _create_user_with_retry(
    first_name: str,
    last_name: str,
    password: str,
    person: Persona,
    max_retries: int = 10,
) -> Usuario:
    for _ in range(max_retries):
        username = build_random_username(first_name, last_name)
        try:
            return Usuario.objects.create(
                username=username,
                password=make_password(password),
                id_persona=person,
                rol="US",
            )
        except IntegrityError:
            continue
    raise ValueError(
        "No se pudo generar un nombre de usuario único tras varios intentos."
    )


def _build_edit_initial_data(user: Usuario, person: Persona) -> dict[str, Any]:
    current_ue = UserBuilding.objects.filter(user=user).first()
    current_building = current_ue.building if current_ue else None

    return {
        "primerNombre": person.name.split(" ")[0] if person and person.name else "",
        "segundoNombre": " ".join(person.name.split(" ")[1:])
        if person and person.name
        else "",
        "primerApellido": person.last_name.split(" ")[0]
        if person and person.last_name
        else "",
        "segundoApellido": " ".join(person.last_name.split(" ")[1:])
        if person and person.last_name
        else "",
        "email": person.email if person else "",
        "cedula": person.ci if person else "",
        "telefono": person.phone if person else "",
        "id_edificio": current_building.id if current_building else None,
    }
