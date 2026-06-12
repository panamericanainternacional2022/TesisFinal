import time as _time

from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.core import signing
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect

from apps.users.models import Usuario
from apps.users.validators import REGEX_USERNAME


def login_view(request: HttpRequest) -> HttpResponse:
    error: str | None = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        if username and password:
            try:
                user = Usuario.objects.get(username=username)
                password_ok = _verify_password(password, user)
                if not password_ok:
                    error = "Usuario o contraseña incorrectos."
                else:
                    _setup_session(request, user)
                    _check_alert_cooldown(user)
                    _setup_alert_session(request, user)
                    return redirect("menu")
            except Usuario.DoesNotExist:
                error = "Usuario o contraseña incorrectos."
        else:
            error = "Ingrese usuario y contraseña."
    return render(request, "users/login.html", {"error": error})


def logout_view(request: HttpRequest) -> HttpResponse:
    request.session.flush()
    return redirect("login")


def complete_registration_view(request: HttpRequest) -> HttpResponse:
    token = request.GET.get("token") or request.POST.get("token")
    if not token:
        return render(
            request,
            "users/completar_registro.html",
            {"error": "Token de registro faltante o inválido."},
        )

    try:
        data = signing.loads(token, max_age=86400)
        user_id = data["user_id"]
        token_email = data.get("email", "")
        user = Usuario.objects.get(id_usuario=user_id)
        if user.registered:
            return render(
                request,
                "users/completar_registro.html",
                {"error": "Este registro ya fue completado anteriormente. Puede iniciar sesión."},
            )
    except (signing.BadSignature, signing.SignatureExpired, Usuario.DoesNotExist):
        return render(
            request,
            "users/completar_registro.html",
            {"error": "El enlace de registro ha expirado o es inválido."},
        )

    form_error = None
    form_errors: dict[str, str] = {}
    username_val = request.POST.get("username", "").strip()
    email_val = request.POST.get("email", "").strip()

    if request.method == "POST":
        password = request.POST.get("password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        if not email_val or not username_val or not password or not confirm_password:
            form_error = "Todos los campos son obligatorios."
            if not email_val:
                form_errors["email"] = "Este campo es obligatorio."
            if not username_val:
                form_errors["username"] = "Este campo es obligatorio."
            if not password:
                form_errors["password"] = "Este campo es obligatorio."
            if not confirm_password:
                form_errors["confirm_password"] = "Este campo es obligatorio."
        elif email_val.lower() != token_email.lower():
            form_error = "El correo ingresado no coincide con el registrado."
            form_errors["email"] = "No coincide con el correo registrado."
        elif password != confirm_password:
            form_error = "Las contraseñas no coinciden."
            form_errors["confirm_password"] = "Las contraseñas no coinciden."
        elif len(password) < 6:
            form_error = "La contraseña debe tener al menos 6 caracteres."
            form_errors["password"] = "La contraseña debe tener al menos 6 caracteres."
        elif not REGEX_USERNAME.match(username_val):
            form_error = "El nombre de usuario solo acepta letras y números."
            form_errors["username"] = "El nombre de usuario solo acepta letras y números."
        elif (
            Usuario.objects.filter(username=username_val)
            .exclude(id_usuario=user.id_usuario)
            .exists()
        ):
            form_error = "El nombre de usuario ya está registrado."
            form_errors["username"] = "El nombre de usuario ya está registrado."
        else:
            user.username = username_val
            user.password = make_password(password)
            user.registered = True
            user.save()
            messages.success(
                request,
                "Registro completado con éxito. Ahora puede iniciar sesión.",
            )
            return redirect("login")

    return render(
        request,
        "users/completar_registro.html",
        {
            "user": user,
            "token": token,
            "username_val": username_val,
            "email_val": email_val,
            "form_error": form_error,
            "form_errors": form_errors,
        },
    )


def _verify_password(raw_password: str, user: Usuario) -> bool:
    if check_password(raw_password, user.password):
        return True
    if user.password == raw_password:
        user.password = make_password(raw_password)
        user.save()
        return True
    return False


def _setup_session(request: HttpRequest, user: Usuario) -> None:
    request.session["usuario_id"] = user.id_usuario
    request.session["usuario_username"] = user.username
    user_role = user.rol or "US"
    if user_role == "ADMIN":
        user_role = "SA"
    request.session["usuario_rol"] = user_role


def _check_alert_cooldown(user: Usuario) -> None:
    if (
        user.alerts_disabled
        and user.alerts_disabled_until
        and _time.time() > user.alerts_disabled_until
    ):
        user.alerts_disabled = False
        user.alerts_disabled_until = None
        user.save(update_fields=["alerts_disabled", "alerts_disabled_until"])


def _setup_alert_session(request: HttpRequest, user: Usuario) -> None:
    alerts_disabled = user.alerts_disabled
    alerts_until = user.alerts_disabled_until
    if alerts_disabled and alerts_until and _time.time() > alerts_until:
        alerts_disabled = False
        alerts_until = None
    request.session["alerts_disabled"] = alerts_disabled
    if alerts_until:
        request.session["alerts_disabled_until_ts"] = alerts_until
    else:
        request.session.pop("alerts_disabled_until_ts", None)
