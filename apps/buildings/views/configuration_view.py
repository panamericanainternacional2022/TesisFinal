from django.contrib.auth.hashers import make_password, check_password
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.core.auth_decorators import _login_required
from apps.users.models import Usuario
from apps.users.validators import (
    _validate_field, _validate_email, _validate_unique_email,
    _validate_min_length, _validate_max_length, REGEX_USERNAME,
)
from apps.buildings.views.shared import build_message


@_login_required
def configuration_view(request: HttpRequest) -> HttpResponse:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return redirect("login")
    usuario = get_object_or_404(Usuario, id_usuario=usuario_id)
    persona = usuario.id_persona
    page_messages = request.session.pop("_cfg_msg", [])

    if request.method == "POST":
        return _handle_config_post(request, usuario, persona, page_messages)

    return render(
        request,
        "buildings/configuracion.html",
        {
            "usuario": usuario,
            "persona": persona,
            "page_messages": page_messages,
            "form_errors": {},
        },
    )


def _handle_config_post(
    request: HttpRequest, usuario: Usuario, persona,
    page_messages: list,
) -> HttpResponse:
    email = request.POST.get("email", "").strip()
    username = request.POST.get("username", "").strip()
    current_password = request.POST.get("current_password", "")
    new_password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")
    form_errors = {}

    if not _verify_password(usuario, current_password):
        page_messages.append(
            build_message("La contraseña actual no es correcta.", "error"))
        form_errors["current_password"] = "La contraseña actual no es correcta."
        return _render_config_error(request, page_messages, form_errors,
                                    email, username)

    _validate_config_email(email, persona, form_errors)
    _validate_config_username(username, form_errors)
    _validate_config_new_password(new_password, confirm_password, form_errors)

    if not form_errors:
        return _apply_config_changes(request, usuario, persona,
                                     email, username, new_password)

    page_messages.append(
        build_message("Por favor, corrige los errores en el formulario.", "error"))
    return _render_config_error(request, page_messages, form_errors,
                                email, username)


def _verify_password(usuario: Usuario, current_password: str) -> bool:
    if not current_password:
        return False
    if check_password(current_password, usuario.password):
        return True
    return _migrate_plaintext_password(usuario, current_password)


def _migrate_plaintext_password(usuario: Usuario, plaintext: str) -> bool:
    if usuario.password == plaintext:
        usuario.password = make_password(plaintext)
        usuario.save(update_fields=["password"])
        return True
    return False


def _validate_config_email(
    email: str, persona, form_errors: dict[str, str],
) -> None:
    if not email:
        return
    err = _validate_email(email)
    if err:
        form_errors["email"] = err
        return
    err = _validate_unique_email(email, exclude_persona_id=persona.id_persona)
    if err:
        form_errors["email_unico"] = err


def _validate_config_username(
    username: str, form_errors: dict[str, str],
) -> None:
    if not username:
        return
    err = _validate_field(
        username, REGEX_USERNAME,
        "El nombre de usuario solo acepta letras y números, sin espacios.",
    )
    if err:
        form_errors["username"] = err
        return
    err = _validate_min_length(username, 4, "El nombre de usuario")
    if err:
        form_errors["username"] = err
        return
    err = _validate_max_length(username, 20, "El nombre de usuario")
    if err:
        form_errors["username"] = err


def _validate_config_new_password(
    new_password: str, confirm_password: str,
    form_errors: dict[str, str],
) -> None:
    if not new_password:
        return
    if len(new_password) < 6:
        form_errors["new_password"] = \
            "La contraseña debe tener al menos 6 caracteres."
    elif new_password != confirm_password:
        form_errors["confirm_password"] = \
            "Las contraseñas nuevas no coinciden."


def _apply_config_changes(
    request: HttpRequest, usuario: Usuario, persona,
    email: str, username: str, new_password: str,
) -> HttpResponse:
    if email:
        persona.email = email
    if username:
        usuario.username = username
    if new_password:
        usuario.password = make_password(new_password)
    persona.save()
    usuario.save()
    request.session["usuario_username"] = usuario.username
    request.session["_cfg_msg"] = [
        build_message("Configuración actualizada correctamente.", "success"),
    ]
    return redirect("configuration")


def _render_config_error(
    request: HttpRequest, page_messages: list,
    form_errors: dict, email: str, username: str,
) -> HttpResponse:
    return render(
        request,
        "buildings/configuracion.html",
        {
            "usuario": {"username": username},
            "persona": {"email": email},
            "page_messages": page_messages,
            "form_errors": form_errors,
        },
    )
