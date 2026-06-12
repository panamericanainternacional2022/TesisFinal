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
            | Q(id_persona__name__icontains=query)
            | Q(id_persona__last_name__icontains=query)
            | Q(id_persona__email__icontains=query)
            | Q(username__icontains=query)
            | Q(building_assignments__building__name__icontains=query)
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
            "current_estado": estado,
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
                form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula y edificio."
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

                        person_name = f"{person.name} {person.last_name}".strip()
                        if email_sent:
                            msg_html = f"""
                            <h3 style="margin: 0 0 6px; color: #137333; font-size: 1.05rem; font-weight: bold; line-height: 1.2;">¡Registro exitoso!</h3>
                            <p style="margin: 0 0 4px; font-size: 0.9rem; line-height: 1.4;">Se ha enviado un correo de activación para <strong>{person_name}</strong> a: <strong style="word-break: break-all;">{post_data['email']}</strong></p>
                            <p style="margin: 0; font-size: 0.85rem; opacity: 0.9;">El usuario deberá seguir el enlace enviado para configurar su cuenta.</p>
                            """
                            messages.success(request, msg_html)
                        else:
                            msg_html = f"""
                            <h3 style="margin: 0 0 6px; color: #c5221f; font-size: 1.05rem; font-weight: bold; line-height: 1.2;">Registro exitoso (Correo no enviado)</h3>
                            <p style="margin: 0 0 6px; font-size: 0.9rem; line-height: 1.4;">Se ha registrado a <strong>{person_name}</strong>. Las credenciales SMTP no están configuradas. Copia y entrega el siguiente enlace directamente al usuario:</p>
                            <div style="margin: 0 0 6px 0; word-break: break-all; background: #fff; padding: 8px; border: 1.5px solid #c5221f; font-family: monospace; font-size: 0.82rem;"><a href="{activation_link}" target="_blank" style="color: #c5221f; text-decoration: underline; font-weight: bold;">{activation_link}</a></div>
                            <p style="margin: 0; font-size: 0.8rem; opacity: 0.8;">Válido por 24 horas.</p>
                            """
                            messages.warning(request, msg_html)

                        return redirect("beneficiary_list")

    buildings = Building.objects.all()
    context: dict[str, Any] = {
        "user": user_data,
        "edificios": buildings,
        "form_error": form_error,
        "form_errors": form_errors,
    }

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
            form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula y edificio para actualizar."
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
                person.save()

                UserBuilding.objects.filter(user=user).delete()
                if post_data.get("id_edificio"):
                    UserBuilding.objects.create(
                        user=user,
                        building_id=post_data["id_edificio"],
                    )

                full_name = f"{person.name} {person.last_name}".strip() or user.username
                messages.success(request, f"Beneficiario <strong>{full_name}</strong> actualizado correctamente.")
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
    person = user.id_persona
    full_name = f"{person.name} {person.last_name}".strip() if person else user.username
    with transaction.atomic():
        Notification.objects.filter(user=user).delete()
        UserBuilding.objects.filter(user=user).delete()
        person_id = user.id_persona_id
        user.delete()
        if person_id:
            Persona.objects.filter(id_persona=person_id).delete()
    messages.success(request, f"Beneficiario <strong>{full_name}</strong> eliminado correctamente.")
    return redirect("user_select", action="eliminar")


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
        .prefetch_related("building_assignments__building")
        .exclude(rol__in=ADMIN_ROLES)
    )
    items = []
    for u in users:
        p = u.id_persona
        ue = u.building_assignments.first()
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
