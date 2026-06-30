from typing import Any

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q

from apps.events.models import Notification
from apps.buildings.models import Building, UserBuilding
from apps.core.auth_decorators import login_required, admin_required
from apps.users.models import Usuario, Persona
from apps.users.services import (
    build_user_data,
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
    return render(request, "users/user_register.html", {"user": {}})


@login_required
@admin_required
def user_list_view(request: HttpRequest) -> HttpResponse:
    from apps.core.auth_decorators import ADMIN_ROLES
    query = request.GET.get("q", "").strip()
    building_id = request.GET.get("edificio", "").strip()
    estado = request.GET.get("estado", "").strip()

    users = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("building_assignments__building")
        .exclude(rol__in=ADMIN_ROLES)
    )

    if building_id:
        users = users.filter(building_assignments__building_id=building_id)

    if estado == "registrado":
        users = users.filter(registered=True)
    elif estado == "por_registrar":
        users = users.filter(registered=False)

    if query:
        users = users.filter(
            Q(id_persona__ci__icontains=query)
            | Q(id_persona__first_name__icontains=query)
            | Q(id_persona__middle_name__icontains=query)
            | Q(id_persona__first_last_name__icontains=query)
            | Q(id_persona__second_last_name__icontains=query)
        ).distinct()

    users = [build_user_data(u) for u in users]
    buildings = Building.objects.all()

    filter_params = {}
    if query:
        filter_params["q"] = query
    if building_id:
        filter_params["edificio"] = building_id
    if estado:
        filter_params["estado"] = estado
    from urllib.parse import urlencode
    filter_query_string = urlencode(filter_params)

    return render(
        request,
        "users/user_list.html",
        {
            "usuarios": users,
            "edificios": buildings,
            "selected_edificio_id": int(building_id) if building_id.isdigit() else None,
            "current_estado": estado,
            "filter_query_string": filter_query_string,
        },
    )


@login_required
@admin_required
def user_create_view(request: HttpRequest) -> HttpResponse:
    generated_password = None
    user_data: dict[str, Any] = {}
    form_errors: dict[str, str] = {}
    email_sent = False
    activation_link = ""

    if request.method == "POST":
        if Building.objects.count() == 0:
            messages.error(request, "Debe registrar al menos un edificio antes de crear un usuario.")
        else:
            post_data = extract_post_data(request)
            user_data = post_data

            if not has_required_fields(post_data):
                messages.error(request, "Complete los campos obligatorios: nombre, apellido, correo electrónico, cédula y edificio.")
                form_errors = build_required_field_errors(post_data)
            else:
                form_errors = validate_user_form(post_data)
                if form_errors:
                    messages.error(request, "Corrija los errores indicados en el formulario.")
                else:
                    person = Persona.objects.create(
                        ci=post_data["cedula"],
                        first_name=post_data["primerNombre"],
                        middle_name=post_data["segundoNombre"],
                        first_last_name=post_data["primerApellido"],
                        second_last_name=post_data["segundoApellido"],
                        email=post_data["email"],
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
                        messages.error(request, "No se pudo generar el nombre de usuario. Verifique los datos ingresados.")

                    if "user" in locals() and post_data.get("id_edificio"):
                        UserBuilding.objects.create(
                            user=user,
                            building_id=post_data["id_edificio"],
                        )

                    if "user" in locals():
                        try:
                            activation_link = send_activation_email(
                                post_data["email"], user.id_usuario,
                                f"{'https' if request.is_secure() else 'http'}://{request.get_host()}",
                            )
                            email_sent = True
                        except Exception:
                            email_sent = False
                            from django.core import signing
                            from django.urls import reverse
                            token = signing.dumps({"user_id": user.id_usuario, "email": post_data["email"]})
                            activation_link = f"{'https' if request.is_secure() else 'http'}://{request.get_host()}{reverse('complete_registration')}?token={token}"

                        p_parts = [person.first_name, person.middle_name, person.first_last_name, person.second_last_name]
                        person_name = " ".join(p for p in p_parts if p)
                        if email_sent:
                            messages.success(request, f"{person_name} registrado. Se envió el correo de activación a {post_data['email']}.")
                        else:
                            messages.warning(request, f"{person_name} registrado. No se pudo enviar el correo; entregue el enlace de activación manualmente: {activation_link}")

                        return redirect("user_list")

    buildings = Building.objects.all()
    context: dict[str, Any] = {
        "user": user_data,
        "edificios": buildings,
        "form_errors": form_errors,
    }

    return render(request, "users/user_register.html", context)


@login_required
@admin_required
@transaction.atomic
def user_update_view(request: HttpRequest, user_id: int) -> HttpResponse:
    user = get_object_or_404(Usuario, id_usuario=user_id)
    person = user.id_persona
    form_errors: dict[str, str] = {}

    if request.method == "POST":
        post_data = extract_post_data(request)
        data = post_data

        if data.get("id_edificio") and data["id_edificio"].isdigit():
            data["id_edificio"] = int(data["id_edificio"])

        if not has_required_fields(post_data):
            messages.error(request, "Complete los campos obligatorios para actualizar: nombre, apellido, correo electrónico, cédula y edificio.")
            form_errors = build_required_field_errors(post_data)
        else:
            form_errors = validate_user_form(post_data, exclude_persona_id=person.id_persona)
            if form_errors:
                messages.error(request, "Corrija los errores indicados en el formulario.")
            else:
                person.first_name = post_data["primerNombre"]
                person.middle_name = post_data["segundoNombre"]
                person.first_last_name = post_data["primerApellido"]
                person.second_last_name = post_data["segundoApellido"]
                person.email = post_data["email"]
                person.ci = post_data["cedula"]
                person.save()

                UserBuilding.objects.filter(user=user).delete()
                if post_data.get("id_edificio"):
                    UserBuilding.objects.create(
                        user=user,
                        building_id=post_data["id_edificio"],
                    )

                p_parts = [person.first_name, person.middle_name, person.first_last_name, person.second_last_name]
                full_name = " ".join(p for p in p_parts if p) or user.username
                messages.success(request, f"{full_name} actualizado correctamente.")
                return redirect("user_list")
    else:
        data = build_edit_initial_data(user, person)

    current_ue = UserBuilding.objects.filter(user=user).first()
    current_building = current_ue.building if current_ue else None
    buildings = Building.objects.all()

    return render(
        request,
        "users/user_register.html",
        {
            "user": data,
            "editing": True,
            "usuario_id": user_id,
            "persona_id": person.id_persona if person else None,
            "edificios": buildings,
            "edificio_actual": current_building,
            "form_errors": form_errors,
        },
    )


@login_required
@admin_required
def user_delete_view(request: HttpRequest, user_id: int) -> HttpResponse:
    user = get_object_or_404(Usuario, id_usuario=user_id)
    person = user.id_persona
    p_parts = [person.first_name, person.middle_name, person.first_last_name, person.second_last_name]
    full_name = " ".join(p for p in p_parts if p) if person else user.username
    with transaction.atomic():
        Notification.objects.filter(user=user).delete()
        UserBuilding.objects.filter(user=user).delete()
        person_id = user.id_persona_id
        user.delete()
        if person_id:
            Persona.objects.filter(id_persona=person_id).delete()
    messages.success(request, f"{full_name} eliminado correctamente.")
    return redirect("user_list")


def check_cedula_uniqueness_view(request: HttpRequest) -> JsonResponse:
    ci = request.GET.get("cedula", "").strip()
    exclude_id = request.GET.get("exclude_id", "").strip()
    exclude_persona_id = int(exclude_id) if exclude_id.isdigit() else None

    if not ci:
        return JsonResponse({"exists": False})

    from apps.users.validators import _validate_unique_ci
    error = _validate_unique_ci(ci, exclude_persona_id)
    return JsonResponse({"exists": bool(error), "error": error})
