import random
import re
import string
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from django.core import signing
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from django.db.models import Q

from core.models import (
    Usuario,
    Persona,
    Edificio,
    UsuarioEdificio,
    Notificacion,
    EquipoMonitoreo,
    EquipoSensor,
    StatusEquipoMonitoreo,
    AccionPrev,
    HistoricoFalla,
)

from front.sensor_config import (
    VAR_NAMES,
    UNITS,
    RISK_NAMES_ES,
    DEVICE_NAMES_ES,
    VALUE_DISPLAY_ES,
)


# ─── VALIDACIÓN ──────────────────────────────────────────────────

REGEX_SOLO_LETRAS = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$")
REGEX_SOLO_NUMEROS = re.compile(r"^\d+$")
REGEX_EMAIL = re.compile(
    r"^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$"
)
REGEX_TELEFONO = re.compile(r"^[\d\s\+\-]+$")
REGEX_RIF = re.compile(r"^[VJEGP]\-?\d{7,9}\-?\d$")
REGEX_DIRECCION = re.compile(r"^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s\,\.\#\-\/\(\)]+$")
REGEX_USERNAME = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+$")


def _validar_campo(valor, regex, mensaje):
    if valor and not regex.match(valor):
        return mensaje
    return None


def _validar_longitud_min(valor, minimo, campo):
    if valor and len(valor) < minimo:
        return f"{campo} debe tener al menos {minimo} caracteres."
    return None


def _validar_longitud_max(valor, maximo, campo):
    if valor and len(valor) > maximo:
        return f"{campo} no puede tener más de {maximo} caracteres."
    return None


def _validar_telefono(valor):
    if not valor:
        return None
    if not REGEX_TELEFONO.match(valor):
        return "El teléfono contiene caracteres no válidos."
    digitos = re.sub(r"[\s\+\-]", "", valor)
    if len(digitos) < 10:
        return "El teléfono debe tener al menos 10 dígitos reales."
    if len(digitos) > 20:
        return "El teléfono no puede tener más de 20 dígitos."
    return None


def _validar_rif(valor):
    if not valor:
        return "El RIF es obligatorio."
    if not REGEX_RIF.match(valor.upper()):
        return "El RIF debe tener formato: letra (V,J,E,G) + 7-9 dígitos + dígito de control. Ej: J-12345678-0"
    return None


def _validar_email(valor):
    if not valor:
        return "El email es obligatorio."
    if not REGEX_EMAIL.match(valor):
        return "Ingresa un correo electrónico válido."
    local = valor.split("@")[0]
    if len(local) > 30:
        return "La parte antes del @ no puede tener más de 30 caracteres."
    if len(valor) < 6:
        return "El correo debe tener al menos 6 caracteres."
    return None


def _validar_unico_email(email, exclude_persona_id=None):
    qs = Persona.objects.filter(email=email)
    if exclude_persona_id:
        qs = qs.exclude(id_persona=exclude_persona_id)
    if qs.exists():
        return "El correo electrónico ya está registrado por otro usuario."
    return None


def _validar_unico_ci(ci, exclude_persona_id=None):
    try:
        ci_int = int(ci)
    except (ValueError, TypeError):
        return None
    qs = Persona.objects.filter(ci=ci_int)
    if exclude_persona_id:
        qs = qs.exclude(id_persona=exclude_persona_id)
    if qs.exists():
        return "La cédula ya está registrada por otro usuario."
    return None


def _validar_unico_telefono(telefono, exclude_persona_id=None):
    if not telefono:
        return None
    qs = Persona.objects.filter(telefono=telefono)
    if exclude_persona_id:
        qs = qs.exclude(id_persona=exclude_persona_id)
    if qs.exists():
        return "El teléfono ya está registrado por otro usuario."
    return None


def _validaciones_formulario_usuario(data, exclude_persona_id=None):
    errores = {}

    # primerNombre
    campo = _validar_campo(
        data.get("primerNombre", ""),
        REGEX_SOLO_LETRAS,
        "El primer nombre solo acepta letras.",
    )
    if campo:
        errores["primerNombre"] = campo
    campo = _validar_longitud_min(data.get("primerNombre", ""), 2, "El primer nombre")
    if campo:
        errores["primerNombre_min"] = campo
    campo = _validar_longitud_max(data.get("primerNombre", ""), 20, "El primer nombre")
    if campo:
        errores["primerNombre_long"] = campo

    # segundoNombre
    campo = _validar_campo(
        data.get("segundoNombre", ""),
        REGEX_SOLO_LETRAS,
        "El segundo nombre solo acepta letras.",
    )
    if campo:
        errores["segundoNombre"] = campo
    campo = _validar_longitud_min(data.get("segundoNombre", ""), 2, "El segundo nombre")
    if campo:
        errores["segundoNombre_min"] = campo
    campo = _validar_longitud_max(
        data.get("segundoNombre", ""), 20, "El segundo nombre"
    )
    if campo:
        errores["segundoNombre_long"] = campo

    # primerApellido
    campo = _validar_campo(
        data.get("primerApellido", ""),
        REGEX_SOLO_LETRAS,
        "El primer apellido solo acepta letras.",
    )
    if campo:
        errores["primerApellido"] = campo
    campo = _validar_longitud_min(
        data.get("primerApellido", ""), 2, "El primer apellido"
    )
    if campo:
        errores["primerApellido_min"] = campo
    campo = _validar_longitud_max(
        data.get("primerApellido", ""), 20, "El primer apellido"
    )
    if campo:
        errores["primerApellido_long"] = campo

    # segundoApellido
    campo = _validar_campo(
        data.get("segundoApellido", ""),
        REGEX_SOLO_LETRAS,
        "El segundo apellido solo acepta letras.",
    )
    if campo:
        errores["segundoApellido"] = campo
    campo = _validar_longitud_min(
        data.get("segundoApellido", ""), 2, "El segundo apellido"
    )
    if campo:
        errores["segundoApellido_min"] = campo
    campo = _validar_longitud_max(
        data.get("segundoApellido", ""), 20, "El segundo apellido"
    )
    if campo:
        errores["segundoApellido_long"] = campo

    # cedula
    campo = _validar_campo(
        data.get("cedula", ""), REGEX_SOLO_NUMEROS, "La cédula solo acepta números."
    )
    if campo:
        errores["cedula"] = campo
    campo = _validar_longitud_min(data.get("cedula", ""), 6, "La cédula")
    if campo:
        errores["cedula_min"] = campo
    campo = _validar_longitud_max(data.get("cedula", ""), 8, "La cédula")
    if campo:
        errores["cedula_long"] = campo

    # email
    campo = _validar_email(data.get("email", ""))
    if campo:
        errores["email"] = campo

    # telefono
    campo = _validar_telefono(data.get("telefono", ""))
    if campo:
        errores["telefono"] = campo

    # direccion
    campo = _validar_longitud_min(data.get("direccion", ""), 8, "La dirección")
    if campo:
        errores["direccion_min"] = campo
    campo = _validar_longitud_max(data.get("direccion", ""), 50, "La dirección")
    if campo:
        errores["direccion_long"] = campo

    campo = _validar_unico_email(data.get("email", ""), exclude_persona_id)
    if campo:
        errores["email_unico"] = campo
    campo = _validar_unico_ci(data.get("cedula", ""), exclude_persona_id)
    if campo:
        errores["cedula_unico"] = campo
    campo = _validar_unico_telefono(data.get("telefono", ""), exclude_persona_id)
    if campo:
        errores["telefono_unico"] = campo
    return errores


def _validar_unico_rif(rif, exclude_edificio_id=None):
    if not rif:
        return None
    qs = Edificio.objects.filter(rif=rif)
    if exclude_edificio_id:
        qs = qs.exclude(id_edificio=exclude_edificio_id)
    if qs.exists():
        return "El RIF ya está registrado en otro edificio."
    return None


def _validaciones_formulario_edificio(data, exclude_edificio_id=None):
    errores = {}
    campo = _validar_campo(
        data.get("nombreEdificio", ""),
        REGEX_SOLO_LETRAS,
        "El nombre del edificio solo acepta letras.",
    )
    if campo:
        errores["nombreEdificio"] = campo
    campo = _validar_longitud_min(
        data.get("nombreEdificio", ""), 3, "El nombre del edificio"
    )
    if campo:
        errores["nombreEdificio_min"] = campo
    campo = _validar_longitud_max(
        data.get("nombreEdificio", ""), 20, "El nombre del edificio"
    )
    if campo:
        errores["nombreEdificio_long"] = campo
    campo = _validar_campo(
        data.get("direccion", ""),
        REGEX_DIRECCION,
        "La dirección contiene caracteres no válidos.",
    )
    if campo:
        errores["direccion"] = campo
    campo = _validar_longitud_min(data.get("direccion", ""), 8, "La dirección")
    if campo:
        errores["direccion_min"] = campo
    campo = _validar_longitud_max(data.get("direccion", ""), 50, "La dirección")
    if campo:
        errores["direccion_long"] = campo
    campo = _validar_rif(data.get("rif", ""))
    if campo:
        errores["rif"] = campo
    campo = _validar_unico_rif(data.get("rif", ""), exclude_edificio_id)
    if campo:
        errores["rif_unico"] = campo
    return errores


def _build_beneficiario_data(usuario):
    persona = usuario.id_persona
    ue = usuario.usuarioedificio_set.first()
    edificio = ue.id_edificio if ue else None
    return {
        "id": usuario.id_usuario,
        "cedula": persona.ci if persona else "",
        "nombre": persona.name if persona else usuario.username,
        "apellido": persona.apellido if persona else "",
        "direccion": persona.direccion if persona else "",
        "email": persona.email if persona else "",
        "telefono": persona.telefono if persona else "",
        "edificio_nombre": edificio.nb_edificio if edificio else "",
        "edificio_rif": edificio.rif if edificio else "",
        "edificio_direccion": edificio.direccion if edificio else "",
        "registrado": usuario.registrado,
    }


def _next_usuario_edificio_pk():
    ultimo = UsuarioEdificio.objects.order_by("-id_usuario_beneficiario").first()
    return (ultimo.id_usuario_beneficiario + 1) if ultimo else 1


def _generate_random_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _build_random_username(primer_nombre, primer_apellido):
    primer_nombre = primer_nombre.strip()
    primer_apellido = primer_apellido.strip()
    if not primer_nombre or not primer_apellido:
        return None
    base_username = (
        f"{primer_nombre[0].upper()}{primer_apellido.split()[0].capitalize()}"
    )
    username = base_username
    counter = 1
    while Usuario.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    return username


def _send_activation_email(email, user_id, request):
    token = signing.dumps({"user_id": user_id})
    protocol = "https" if request.is_secure() else "http"
    host = request.get_host()
    link = f"{protocol}://{host}/completar_registro/?token={token}"

    # Cargar variables de entorno desde .env si existen (como en app27.py)
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.strip().split("=", 1)
                        os.environ[key.strip()] = val.strip().strip("'\"")

    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        print(f"⚠️ Credenciales SMTP no configuradas. Link de registro: {link}")
        return False, link

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = smtp_user
        msg["To"] = email
        msg["Subject"] = "[INES] Activacion y Acceso al Sistema"

        body = f"""Hola,
        
Se ha registrado su usuario en el Sistema de Monitoreo INES.
Para completar su registro y poder acceder al sistema, por favor haga clic en el siguiente enlace y defina su nombre de usuario y contraseña:

{link}

Este enlace es valido por 24 horas.
Si usted no solicito este registro, por favor ignore este correo.
"""
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Activación de Cuenta - Sistema INES</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f5f5f5; padding: 24px 0;">
    <tr>
      <td align="center">
        <!-- Contenedor Principal (Estilo Suizo - Bordes Rectos) -->
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #0a0a0a; border-collapse: collapse;">
          <!-- Cabecera -->
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #ffffff;">
              <span style="font-size: 14px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #0a0a0a;">SISTEMA INES</span>
            </td>
          </tr>
          <!-- Banner de Bienvenida -->
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #f5f5f5; border-left: 6px solid #0a0a0a;">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #5e5e5e; display: block; margin-bottom: 4px;">ACCESO AL SISTEMA</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Activación de Cuenta</h1>
            </td>
          </tr>
          <!-- Contenido -->
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              <p style="margin: 0 0 16px 0;">Hola,</p>
              <p style="margin: 0 0 16px 0;">Se ha registrado su usuario en el Sistema de Monitoreo INES. Para poder acceder y utilizar todas las funciones de monitoreo y alertas de infraestructura de su edificio, es necesario que complete su registro.</p>
              <p style="margin: 0 0 24px 0;">Por favor, haga clic en el botón a continuación para definir su nombre de usuario y contraseña:</p>
              
              <!-- Botón de Acción -->
              <div style="margin: 24px 0; text-align: left;">
                <a href="{link}" target="_blank" style="background-color: #0a0a0a; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; display: inline-block; border-radius: 0px; border: 1px solid #0a0a0a;">Completar Registro</a>
              </div>
              
              <div style="margin: 24px 0; padding: 16px; background-color: #f5f5f5; border: 1px solid #e0e0e0; font-size: 12px; color: #5e5e5e;">
                <p style="margin: 0 0 8px 0; font-weight: 700;">Información de seguridad:</p>
                <p style="margin: 0 0 8px 0;">• Este enlace es válido por 24 horas.</p>
                <p style="margin: 0;">• Si usted no solicitó este registro, por favor ignore este correo.</p>
              </div>
              
              <p style="margin: 0; font-size: 12px; color: #9e9e9e;">Si el botón no funciona, copie y pegue la siguiente dirección en su navegador:<br>
              <a href="{link}" style="color: #0a0a0a; text-decoration: underline;">{link}</a></p>
            </td>
          </tr>
          <!-- Pie de página -->
          <tr>
            <td style="padding: 16px 24px; border-top: 1px solid #e0e0e0; background-color: #f5f5f5; font-size: 11px; color: #6b6b6b; text-align: center;">
              Este es un mensaje generado de forma automática por el Sistema de Monitoreo INES.<br>
              Por favor, no responda a este correo electrónico.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        return True, link
    except Exception as e:
        print(f"Error enviando email de activacion: {e}")
        return False, link


ADMIN_ROLES = ("SA", "ADMIN")


def _login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return wrapper


def _is_admin_role(rol):
    return rol in ADMIN_ROLES


def _admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not _is_admin_role(request.session.get("usuario_rol")):
            messages.error(request, "No tienes permiso para acceder a esta sección.")
            return redirect("menu_seleccion")
        return view_func(request, *args, **kwargs)

    return wrapper


# ─── AUTH ────────────────────────────────────────────────────────


def login_view(request):
    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        if username and password:
            try:
                usuario = Usuario.objects.get(username=username)
                password_ok = check_password(password, usuario.password)
                if not password_ok and usuario.password == password:
                    usuario.password = make_password(password)
                    usuario.save()
                    password_ok = True
                if not password_ok:
                    error = "Usuario o contraseña incorrectos."
                else:
                    request.session["usuario_id"] = usuario.id_usuario
                    request.session["usuario_username"] = usuario.username
                    usuario_rol = usuario.rol or "US"
                    if usuario_rol == "ADMIN":
                        usuario_rol = "SA"
                    request.session["usuario_rol"] = usuario_rol
                    # Restore alert state from DB into session
                    import time as _time
                    _alerts_dis = usuario.alerts_disabled
                    _alerts_until = usuario.alerts_disabled_until
                    if _alerts_dis and _alerts_until and _time.time() > _alerts_until:
                        # Timer expired while logged out — auto-clear
                        usuario.alerts_disabled = False
                        usuario.alerts_disabled_until = None
                        usuario.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
                        _alerts_dis = False
                        _alerts_until = None
                    request.session["alerts_disabled"] = _alerts_dis
                    if _alerts_until:
                        request.session["alerts_disabled_until_ts"] = _alerts_until
                    else:
                        request.session.pop("alerts_disabled_until_ts", None)
                    return redirect("menu_seleccion")
            except Usuario.DoesNotExist:
                error = "Usuario o contraseña incorrectos."
        else:
            error = "Ingrese usuario y contraseña."
    return render(request, "pages/login.html", {"error": error})


def logout_view(request):
    request.session.flush()
    return redirect("login")


# ─── DASHBOARD / MENU ────────────────────────────────────────────


@_login_required
def menu_seleccion_view(request):
    rol = request.session.get("usuario_rol", "US")
    return render(request, "pages/menu_seleccion.html", {"rol": rol})


# ─── USUARIOS (ADMIN ONLY) ──────────────────────────────────────


@_login_required
@_admin_required
def usuario_view(request):
    return render(request, "pages/registro_usuario.html", {"user": {}})


@_login_required
@_admin_required
def lista_usuario_view(request):
    query = request.GET.get("q", "").strip()
    edificio_id = request.GET.get("edificio", "").strip()
    
    usuarios = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("usuarioedificio_set__id_edificio")
        .exclude(rol__in=ADMIN_ROLES)
    )
    
    if edificio_id:
        usuarios = usuarios.filter(usuarioedificio__id_edificio_id=edificio_id)
        
    if query:
        usuarios = usuarios.filter(
            Q(id_persona__ci__icontains=query)
            | Q(id_persona__name__icontains=query)
            | Q(id_persona__apellido__icontains=query)
            | Q(id_persona__email__icontains=query)
            | Q(username__icontains=query)
            | Q(usuarioedificio__id_edificio__nb_edificio__icontains=query)
        ).distinct()
        
    beneficiarios = [_build_beneficiario_data(usuario) for usuario in usuarios]
    edificios = Edificio.objects.all()
    
    return render(
        request,
        "pages/lista_usuario.html",
        {
            "beneficiarios": beneficiarios,
            "edificios": edificios,
            "selected_edificio_id": int(edificio_id) if edificio_id.isdigit() else None,
            "request": request,
        },
    )


@_login_required
@_admin_required
def registro_beneficiario_view(request):
    generated_username = None
    generated_password = None
    user_data = {}
    form_error = None
    form_errors = {}

    if request.method == "POST":
        if Edificio.objects.count() == 0:
            form_error = (
                "Debe registrar al menos un edificio antes de crear un beneficiario."
            )
        else:
            primer_nombre = request.POST.get("primerNombre", "").strip()
            segundo_nombre = request.POST.get("segundoNombre", "").strip()
            primer_apellido = request.POST.get("primerApellido", "").strip()
            segundo_apellido = request.POST.get("segundoApellido", "").strip()
            email = request.POST.get("email", "").strip()
            cedula = request.POST.get("cedula", "").strip()
            telefono = request.POST.get("telefono", "").strip()
            direccion = request.POST.get("direccion", "").strip()
            id_edificio = request.POST.get("id_edificio", "").strip()

            user_data = {
                "primerNombre": primer_nombre,
                "segundoNombre": segundo_nombre,
                "primerApellido": primer_apellido,
                "segundoApellido": segundo_apellido,
                "email": email,
                "cedula": cedula,
                "telefono": telefono,
                "direccion": direccion,
                "id_edificio": int(id_edificio) if id_edificio else "",
            }

            if not (
                primer_nombre
                and primer_apellido
                and email
                and cedula
                and id_edificio
                and telefono
            ):
                form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula, teléfono y edificio."
                if not primer_nombre:
                    form_errors["primerNombre"] = "Este campo es obligatorio."
                if not primer_apellido:
                    form_errors["primerApellido"] = "Este campo es obligatorio."
                if not email:
                    form_errors["email"] = "Este campo es obligatorio."
                if not cedula:
                    form_errors["cedula"] = "Este campo es obligatorio."
                if not telefono:
                    form_errors["telefono"] = "Este campo es obligatorio."
                if not id_edificio:
                    form_errors["id_edificio"] = "Este campo es obligatorio."
            else:
                form_errors = _validaciones_formulario_usuario(user_data)
                if form_errors:
                    form_error = "Por favor, corrige los errores en el formulario."
                else:
                    nombre_completo = f"{primer_nombre} {segundo_nombre}".strip()
                    apellido_completo = f"{primer_apellido} {segundo_apellido}".strip()
                    generated_username = _build_random_username(
                        primer_nombre, primer_apellido
                    )
                    generated_password = _generate_random_password(10)

                    if not generated_username:
                        form_error = "No se pudo generar un nombre de usuario. Verifica los datos ingresados."
                    else:
                        persona = Persona.objects.create(
                            ci=cedula,
                            name=nombre_completo,
                            apellido=apellido_completo,
                            email=email,
                            telefono=telefono,
                            direccion=direccion,
                        )
                        usuario = Usuario.objects.create(
                            username=generated_username,
                            password=make_password(generated_password),
                            id_persona=persona,
                            rol="US",
                        )
                        if id_edificio:
                            UsuarioEdificio.objects.create(
                                id_usuario_beneficiario=_next_usuario_edificio_pk(),
                                id_usuario=usuario,
                                id_edificio_id=id_edificio,
                            )
                        email_sent, activation_link = _send_activation_email(
                            email, usuario.id_usuario, request
                        )

    edificios = Edificio.objects.all()
    context = {
        "user": user_data,
        "edificios": edificios,
        "form_error": form_error,
        "form_errors": form_errors,
    }
    if "email_sent" in locals():
        context["email_sent"] = email_sent
        context["activation_link"] = activation_link
        context["sent_to"] = email

    return render(
        request,
        "pages/registro_usuario.html",
        context,
    )


@_login_required
@_admin_required
def editar_beneficiario_view(request, beneficiario_id):
    usuario = get_object_or_404(Usuario, id_usuario=beneficiario_id)
    persona = usuario.id_persona
    form_error = None
    form_errors = {}

    if request.method == "POST":
        primer_nombre = request.POST.get("primerNombre", "").strip()
        segundo_nombre = request.POST.get("segundoNombre", "").strip()
        primer_apellido = request.POST.get("primerApellido", "").strip()
        segundo_apellido = request.POST.get("segundoApellido", "").strip()
        email = request.POST.get("email", "").strip()
        cedula = request.POST.get("cedula", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        direccion = request.POST.get("direccion", "").strip()
        id_edificio = request.POST.get("id_edificio", "").strip()

        data = {
            "primerNombre": primer_nombre,
            "segundoNombre": segundo_nombre,
            "primerApellido": primer_apellido,
            "segundoApellido": segundo_apellido,
            "email": email,
            "cedula": cedula,
            "telefono": telefono,
            "direccion": direccion,
            "id_edificio": int(id_edificio) if id_edificio else "",
        }

        if not (
            primer_nombre
            and primer_apellido
            and email
            and cedula
            and id_edificio
            and telefono
        ):
            form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula, teléfono y edificio para actualizar."
            if not primer_nombre:
                form_errors["primerNombre"] = "Este campo es obligatorio."
            if not primer_apellido:
                form_errors["primerApellido"] = "Este campo es obligatorio."
            if not email:
                form_errors["email"] = "Este campo es obligatorio."
            if not cedula:
                form_errors["cedula"] = "Este campo es obligatorio."
            if not telefono:
                form_errors["telefono"] = "Este campo es obligatorio."
            if not id_edificio:
                form_errors["id_edificio"] = "Este campo es obligatorio."
        else:
            form_errors = _validaciones_formulario_usuario(
                data,
                exclude_persona_id=persona.id_persona,
            )
            if form_errors:
                form_error = "Por favor, corrige los errores en el formulario."
            else:
                persona.name = f"{primer_nombre} {segundo_nombre}".strip()
                persona.apellido = f"{primer_apellido} {segundo_apellido}".strip()
                persona.email = email
                persona.ci = cedula
                persona.telefono = telefono
                persona.direccion = direccion
                persona.save()

                if id_edificio:
                    UsuarioEdificio.objects.filter(id_usuario=usuario).delete()
                    UsuarioEdificio.objects.create(
                        id_usuario_beneficiario=_next_usuario_edificio_pk(),
                        id_usuario=usuario,
                        id_edificio_id=id_edificio,
                    )
                else:
                    UsuarioEdificio.objects.filter(id_usuario=usuario).delete()

                messages.success(request, "Beneficiario actualizado correctamente.")
                return redirect("lista_usuario")
    else:
        usuario_edificio = UsuarioEdificio.objects.filter(id_usuario=usuario).first()
        edificio_actual = usuario_edificio.id_edificio if usuario_edificio else None
        id_edificio_actual = edificio_actual.id_edificio if edificio_actual else None

        data = {
            "primerNombre": persona.name.split(" ")[0]
            if persona and persona.name
            else "",
            "segundoNombre": " ".join(persona.name.split(" ")[1:])
            if persona and persona.name
            else "",
            "primerApellido": persona.apellido.split(" ")[0]
            if persona and persona.apellido
            else "",
            "segundoApellido": " ".join(persona.apellido.split(" ")[1:])
            if persona and persona.apellido
            else "",
            "email": persona.email if persona else "",
            "cedula": persona.ci if persona else "",
            "telefono": persona.telefono if persona else "",
            "direccion": persona.direccion if persona else "",
            "id_edificio": id_edificio_actual,
        }

    usuario_edificio = UsuarioEdificio.objects.filter(id_usuario=usuario).first()
    edificio_actual = usuario_edificio.id_edificio if usuario_edificio else None
    edificios = Edificio.objects.all()
    return render(
        request,
        "pages/registro_usuario.html",
        {
            "user": data,
            "editing": True,
            "beneficiario_id": beneficiario_id,
            "edificios": edificios,
            "edificio_actual": edificio_actual,
            "form_error": form_error,
            "form_errors": form_errors,
        },
    )


@_login_required
@_admin_required
def eliminar_beneficiario_view(request, beneficiario_id):
    usuario = get_object_or_404(Usuario, id_usuario=beneficiario_id)
    with transaction.atomic():
        Notificacion.objects.filter(id_usuario=usuario).delete()
        UsuarioEdificio.objects.filter(id_usuario=usuario).delete()
        usuario.delete()
        if usuario.id_persona:
            Persona.objects.filter(id_persona=usuario.id_persona.id_persona).delete()
    messages.success(request, "Beneficiario eliminado correctamente.")
    return redirect("seleccionar_usuario", accion="eliminar")


# ─── EDIFICIOS (ADMIN ONLY) ─────────────────────────────────────


@_login_required
@_admin_required
def registro_edificio_view(request):
    bld_msgs = request.session.pop("_bld_msg", [])
    form_errors = {}
    edificio_data = {}
    if request.method == "POST":
        nombre = request.POST.get("nombreEdificio", "").strip()
        parroquia = request.POST.get("parroquia", "").strip()
        rif = request.POST.get("rif", "").strip()

        edificio_data = {
            "nb_edificio": nombre,
            "direccion": parroquia,
            "rif": rif,
        }

        if not (nombre and rif and parroquia):
            bld_msgs.append(
                {
                    "text": "Complete el nombre, la dirección y el RIF del edificio.",
                    "type": "error",
                }
            )
            if not nombre:
                form_errors["nombreEdificio"] = "Este campo es obligatorio."
            if not rif:
                form_errors["rif"] = "Este campo es obligatorio."
            if not parroquia:
                form_errors["direccion"] = "Este campo es obligatorio."
        else:
            form_errors = _validaciones_formulario_edificio(
                {
                    "nombreEdificio": nombre,
                    "direccion": parroquia,
                    "rif": rif,
                }
            )
            if form_errors:
                bld_msgs.append(
                    {
                        "text": "Por favor, corrige los errores en el formulario.",
                        "type": "error",
                    }
                )
            else:
                Edificio.objects.create(
                    nb_edificio=nombre,
                    rif=rif,
                    direccion=parroquia,
                )
                request.session["_bld_msg"] = [
                    {"text": "Edificio registrado correctamente.", "type": "success"}
                ]
                return redirect("lista_edificios")
    return render(
        request,
        "pages/registro_edificio.html",
        {
            "editing": False,
            "page_messages": bld_msgs,
            "form_errors": form_errors,
            "edificio": edificio_data,
        },
    )


@_login_required
@_admin_required
def editar_edificio_view(request, edificio_id):
    edificio = get_object_or_404(Edificio, id_edificio=edificio_id)
    bld_msgs = request.session.pop("_bld_msg", [])
    form_errors = {}
    if request.method == "POST":
        nombre = request.POST.get("nombreEdificio", "").strip()
        parroquia = request.POST.get("parroquia", "").strip()
        rif = request.POST.get("rif", "").strip()

        edificio.nb_edificio = nombre
        edificio.direccion = parroquia
        edificio.rif = rif

        if not (nombre and rif and parroquia):
            bld_msgs.append(
                {
                    "text": "Complete el nombre, la dirección y el RIF del edificio para guardar los cambios.",
                    "type": "error",
                }
            )
            if not nombre:
                form_errors["nombreEdificio"] = "Este campo es obligatorio."
            if not rif:
                form_errors["rif"] = "Este campo es obligatorio."
            if not parroquia:
                form_errors["direccion"] = "Este campo es obligatorio."
        else:
            form_errors = _validaciones_formulario_edificio(
                {
                    "nombreEdificio": nombre,
                    "direccion": parroquia,
                    "rif": rif,
                },
                exclude_edificio_id=edificio_id,
            )
            if form_errors:
                bld_msgs.append(
                    {
                        "text": "Por favor, corrige los errores en el formulario.",
                        "type": "error",
                    }
                )
            else:
                edificio.save()
                request.session["_bld_msg"] = [
                    {"text": "Edificio actualizado correctamente.", "type": "success"}
                ]
                return redirect("lista_edificios")
    return render(
        request,
        "pages/registro_edificio.html",
        {
            "editing": True,
            "edificio": edificio,
            "page_messages": bld_msgs,
            "form_errors": form_errors,
        },
    )


@_login_required
@_admin_required
def lista_edificios_view(request):
    query = request.GET.get("q", "").strip()
    edificios = Edificio.objects.all()
    if query:
        edificios = edificios.filter(
            Q(nb_edificio__icontains=query)
            | Q(rif__icontains=query)
            | Q(direccion__icontains=query)
        )
    bld_msgs = request.session.pop("_bld_msg", [])
    return render(
        request,
        "pages/lista_edificios.html",
        {
            "edificios": list(edificios),
            "request": request,
            "page_messages": bld_msgs,
        },
    )


@_login_required
@_admin_required
def eliminar_edificio_view(request, edificio_id):
    edificio = get_object_or_404(Edificio, id_edificio=edificio_id)
    with transaction.atomic():
        # Desactivamos temporalmente las FK checks para evitar race conditions
        # con app27.py, que crea notificaciones continuamente para los equipos.
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        # Materializamos los IDs para evitar subquerys dentro del mismo DELETE
        equipo_ids = list(
            EquipoMonitoreo.objects.filter(id_edificio=edificio).values_list(
                "id_equipo_monitoreo", flat=True
            )
        )
        sensor_ids = list(
            EquipoSensor.objects.filter(id_equipo_monitoreo__in=equipo_ids).values_list(
                "id_equipo_sensor", flat=True
            )
        )
        status_ids = list(
            StatusEquipoMonitoreo.objects.filter(
                id_equipo_monitoreo__in=equipo_ids
            ).values_list("id_status_equipo_monitoreo", flat=True)
        )

        # Delete HistoricoFalla records that reference our sensors or equipment statuses
        HistoricoFalla.objects.filter(
            Q(id_equipo_sensor__in=sensor_ids)
            | Q(id_status_equipo_monitoreo__in=status_ids)
        ).delete()

        # Delete the sensors
        EquipoSensor.objects.filter(id_equipo_monitoreo__in=equipo_ids).delete()

        # Delete status records
        StatusEquipoMonitoreo.objects.filter(
            id_equipo_monitoreo__in=equipo_ids
        ).delete()

        # Delete preventive actions
        AccionPrev.objects.filter(id_equipo_monitoreo__in=equipo_ids).delete()

        # Delete notifications
        Notificacion.objects.filter(id_equipo_monitoreo__in=equipo_ids).delete()

        # Delete the monitoring equipment
        EquipoMonitoreo.objects.filter(id_equipo_monitoreo__in=equipo_ids).delete()

        # Delete user-building associations
        UsuarioEdificio.objects.filter(id_edificio=edificio).delete()

        # Finally, delete the building
        edificio.delete()

        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    messages.success(
        request, "Edificio y todos sus datos asociados fueron eliminados correctamente."
    )
    return redirect("seleccionar_edificio", accion="eliminar")


# ─── NOTIFICACIONES ─────────────────────────────────────────────


@_login_required
def notificaciones_view(request):
    usuario_id = request.session["usuario_id"]
    rol = request.session.get("usuario_rol", "US")
    edificio_id = request.GET.get("edificio", "").strip()

    if _is_admin_role(rol):
        edificios = Edificio.objects.all()
        notificaciones = Notificacion.objects.all()
        if edificio_id:
            notificaciones = notificaciones.filter(id_equipo_monitoreo__id_edificio_id=edificio_id)
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        edificios = Edificio.objects.filter(id_edificio__in=usuario_edificios)
        
        if edificio_id:
            if edificio_id.isdigit() and int(edificio_id) in list(usuario_edificios):
                notificaciones = Notificacion.objects.filter(id_equipo_monitoreo__id_edificio_id=edificio_id)
            else:
                notificaciones = Notificacion.objects.none()
        else:
            equipos = EquipoMonitoreo.objects.filter(
                id_edificio_id__in=list(usuario_edificios)
            ).values_list("id_equipo_monitoreo", flat=True)
            notificaciones = Notificacion.objects.filter(
                id_usuario_id=usuario_id
            ) | Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos))

    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        import datetime as dt
        cleared_dt = dt.datetime.fromtimestamp(alerts_cleared_at, tz=dt.timezone.utc)
        notificaciones = notificaciones.filter(fecha__gt=cleared_dt)

    notificaciones = (
        notificaciones.select_related("id_usuario", "id_equipo_monitoreo__id_edificio")
        # Solo alertas de Alto y Crítico en esta vista
        .exclude(mensaje__contains='"risk": "Info"')
        .exclude(mensaje__contains='"risk":"Info"')
        .exclude(mensaje__contains='"risk": "Bajo"')
        .exclude(mensaje__contains='"risk":"Bajo"')
        .exclude(mensaje__contains='"risk": "Medio"')
        .exclude(mensaje__contains='"risk":"Medio"')
        .distinct()
        .order_by("-fecha")
    )

    from django.core.paginator import Paginator
    paginator = Paginator(notificaciones, 30)  # 30 notificaciones por página
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    import re
    import json as _json

    var_names = VAR_NAMES
    units = UNITS
    risk_names_es = RISK_NAMES_ES
    device_names_es = DEVICE_NAMES_ES

    def _translate_devices(text):
        """Reemplaza nombres de dispositivos en inglés por su equivalente en español."""
        for en, es in device_names_es.items():
            text = re.sub(rf"\b{re.escape(en)}\b", es, text, flags=re.IGNORECASE)
        return text

    def _build_protection_action(risk, raw_action):
        """Construye el texto de acción para notificaciones de Protección automática."""
        risk_es = risk_names_es.get(risk, risk.lower())
        devices_match = re.search(r"[Dd]ispositivos?\s+apagados?:\s*(.+)", raw_action)
        if devices_match:
            devices_es = _translate_devices(devices_match.group(1).rstrip("."))
            return f"Protección automática activada (alerta {risk_es}). Dispositivos apagados: {devices_es}."
        return f"Protección automática activada (alerta {risk_es}). {_translate_devices(raw_action)}"

    def _build_restoration_action(raw_action):
        """Traduce el mensaje de restauración de protección."""
        return _translate_devices(raw_action)

    def _make_parsed(risk, variable, value, action):
        """Construye el dict parsed_data final."""
        var_display = var_names.get(variable, variable.replace("_", " ").title())

        value_str = str(value).lower().strip() if value is not None else ""

        # Traducir valores especiales de sensores (door_status, motor_stuck, etc.)
        if variable in VALUE_DISPLAY_ES:
            value_display = VALUE_DISPLAY_ES[variable].get(value_str, str(value).capitalize())
        elif value_str == "pump":
            value_display = "Bomba de agua"
        elif value_str == "elevator":
            value_display = "Ascensor"
        elif value_str in device_names_es:
            value_display = device_names_es[value_str].capitalize()
        elif value_str:
            value_display = value_str.capitalize()
        else:
            value_display = ""

        if variable == "Protección automática":
            action = _build_protection_action(risk, action)
        elif variable.startswith("Protección "):
            action = _build_restoration_action(action)
        return {
            "parsed": True,
            "risk": risk,
            "variable": var_display,
            "value": value_display,
            "unit": units.get(variable, ""),
            "action": action,
        }

    for notif in page_obj:
        raw = (notif.mensaje or "").strip()
        parsed_data = None

        # Camino 1: JSON estructurado (registros nuevos)
        if raw.startswith("{"):
            try:
                data = _json.loads(raw)
                parsed_data = _make_parsed(
                    risk=data.get("risk", ""),
                    variable=data.get("variable", ""),
                    value=data.get("value") or "",
                    action=data.get("action", ""),
                )
            except (ValueError, KeyError):
                parsed_data = None

        # Camino 2: Regex formato [risk] variable = value - action
        if parsed_data is None:
            m = re.match(r"^\[(.*?)\]\s+(.*?)\s+=\s+(.*?)\s+-\s+(.*)$", raw)
            if m:
                parsed_data = _make_parsed(
                    risk=m.group(1).strip(),
                    variable=m.group(2).strip(),
                    value=m.group(3).strip(),
                    action=m.group(4).strip(),
                )

        # Camino 3: Regex formato legado proteccion sin corchetes
        if parsed_data is None:
            pm = re.match(
                r"Protecci[oó]n autom[áa]tica activada\s*\(Alerta\s+(\w+)\s+de\s+(\w+)\)\.+\s*Dispositivos\s+apagados:\s*(.+)",
                raw,
                re.IGNORECASE,
            )
            if pm:
                p_risk = pm.group(1).strip().capitalize()
                p_variable = pm.group(2).strip()
                p_devices_es = _translate_devices(pm.group(3).rstrip("."))
                p_risk_es = risk_names_es.get(p_risk, p_risk.lower())
                p_var_es = var_names.get(p_variable, p_variable.replace("_", " "))
                parsed_data = {
                    "parsed": True,
                    "risk": p_risk,
                    "variable": "Protección automática",
                    "value": "True",
                    "unit": "",
                    "action": (
                        f"Protección automática activada ({p_var_es} {p_risk_es}). "
                        f"Dispositivos apagados: {p_devices_es}."
                    ),
                }

        # Resultado final
        notif.parsed_data = parsed_data or {"parsed": False}

    import time as _time
    usuario_id = request.session["usuario_id"]
    try:
        _usuario_obj = Usuario.objects.get(pk=usuario_id)
    except Exception:
        _usuario_obj = None

    if _usuario_obj:
        alertas_desactivadas = _usuario_obj.alerts_disabled
        alerts_disabled_until_ts = _usuario_obj.alerts_disabled_until
    else:
        alertas_desactivadas = request.session.get("alerts_disabled", False)
        alerts_disabled_until_ts = request.session.get("alerts_disabled_until_ts", None)

    # Auto-expire timed disables
    if alertas_desactivadas and alerts_disabled_until_ts:
        if _time.time() > alerts_disabled_until_ts:
            alertas_desactivadas = False
            alerts_disabled_until_ts = None
            if _usuario_obj:
                _usuario_obj.alerts_disabled = False
                _usuario_obj.alerts_disabled_until = None
                _usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
            request.session["alerts_disabled"] = False
            request.session.pop("alerts_disabled_until_ts", None)

    alerts_disabled_until_ms = int(alerts_disabled_until_ts * 1000) if alerts_disabled_until_ts else None

    return render(
        request,
        "pages/notificaciones.html",
        {
            "notificaciones": page_obj,
            "edificios": edificios,
            "selected_edificio_id": int(edificio_id) if edificio_id.isdigit() else None,
            "rol": rol,
            "alertas_desactivadas": alertas_desactivadas,
            "alerts_disabled_until_ms": alerts_disabled_until_ms,
        },
    )


@_login_required
def toggle_alerts_session_view(request):
    from django.http import JsonResponse
    import json
    import time as _time

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            enabled = data.get("enabled", True)
            duration_minutes = data.get("duration_minutes", None)  # None = indefinite

            usuario_id = request.session.get("usuario_id")
            try:
                usuario_obj = Usuario.objects.get(pk=usuario_id)
            except Exception:
                usuario_obj = None

            if enabled:
                if usuario_obj:
                    usuario_obj.alerts_disabled = False
                    usuario_obj.alerts_disabled_until = None
                    usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
                request.session["alerts_disabled"] = False
                request.session.pop("alerts_disabled_until_ts", None)
                return JsonResponse({"status": "ok", "alerts_disabled": False, "alerts_disabled_until_ms": None})
            else:
                until_ts = None
                if duration_minutes is not None:
                    until_ts = _time.time() + float(duration_minutes) * 60
                if usuario_obj:
                    usuario_obj.alerts_disabled = True
                    usuario_obj.alerts_disabled_until = until_ts
                    usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
                request.session["alerts_disabled"] = True
                if until_ts:
                    request.session["alerts_disabled_until_ts"] = until_ts
                else:
                    request.session.pop("alerts_disabled_until_ts", None)
                until_ms = int(until_ts * 1000) if until_ts else None
                return JsonResponse({"status": "ok", "alerts_disabled": True, "alerts_disabled_until_ms": until_ms})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"status": "error", "message": "Método no permitido"}, status=405)


@_login_required
def limpiar_notificaciones_view(request):
    from django.http import JsonResponse
    import time

    if request.method == "POST":
        request.session["alerts_cleared_at"] = time.time()
        return JsonResponse(
            {"status": "ok", "message": "Alertas limpiadas correctamente"}
        )
    return JsonResponse(
        {"status": "error", "message": "Método no permitido"}, status=405
    )


# ─── MONITOREO ──────────────────────────────────────────────────


@_login_required
def monitoreo_view(request):
    rol = request.session.get("usuario_rol", "US")
    if _is_admin_role(rol):
        edificios = Edificio.objects.all()
        return render(
            request,
            "pages/monitoreo_admin.html",
            {
                "rol": rol,
                "edificios": edificios,
            },
        )

    usuario_id = request.session["usuario_id"]
    query = request.GET.get("q", "").strip()
    usuario_edificios = UsuarioEdificio.objects.filter(
        id_usuario_id=usuario_id
    ).values_list("id_edificio_id", flat=True)
    equipos = EquipoMonitoreo.objects.filter(
        id_edificio_id__in=list(usuario_edificios)
    ).select_related("id_edificio")

    if query:
        equipos = equipos.filter(
            Q(id_edificio__nb_edificio__icontains=query)
            | Q(id_edificio__rif__icontains=query)
        )

    data = []
    for eq in equipos:
        ultimo_status = (
            StatusEquipoMonitoreo.objects.filter(id_equipo_monitoreo=eq)
            .select_related("id_status")
            .order_by("-id_status_equipo_monitoreo")
            .first()
        )

        sensores = EquipoSensor.objects.filter(id_equipo_monitoreo=eq).select_related(
            "id_dispos_sensor"
        )

        data.append(
            {
                "equipo": eq,
                "edificio": eq.id_edificio,
                "status": ultimo_status.id_status.nb_status
                if ultimo_status
                else "Sin datos",
                "sensores": list(sensores),
            }
        )

    return render(
        request,
        "pages/monitoreo.html",
        {
            "equipos_data": data,
            "rol": rol,
            "query": query,
        },
    )


@_login_required
@_admin_required
def monitoreo_edificio_view(request, edificio_id):
    rol = request.session.get("usuario_rol", "US")
    edificio = get_object_or_404(Edificio, id_edificio=edificio_id)
    return render(
        request,
        "pages/monitoreo.html",
        {
            "rol": rol,
            "selected_edificio": edificio,
            "equipos_data": [],
            "query": "",
        },
    )


# ─── CONFIGURACION ──────────────────────────────────────────────


@_login_required
def configuracion_view(request):
    usuario_id = request.session["usuario_id"]
    usuario = get_object_or_404(Usuario, id_usuario=usuario_id)
    persona = usuario.id_persona
    page_messages = request.session.pop("_cfg_msg", [])
    form_errors = {}

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        username = request.POST.get("username", "").strip()
        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        password_ok = check_password(current_password, usuario.password)
        if not password_ok and usuario.password == current_password:
            usuario.password = make_password(current_password)
            password_ok = True

        if not password_ok:
            page_messages.append(
                {"text": "La contraseña actual no es correcta.", "type": "error"}
            )
            form_errors["current_password"] = "La contraseña actual no es correcta."
        else:
            if email:
                err_email = _validar_email(email)
                if err_email:
                    form_errors["email"] = err_email
                else:
                    err_email_unico = _validar_unico_email(
                        email, exclude_persona_id=persona.id_persona
                    )
                    if err_email_unico:
                        form_errors["email_unico"] = err_email_unico
            if username:
                err_user = _validar_campo(
                    username,
                    REGEX_USERNAME,
                    "El nombre de usuario solo acepta letras y números, sin espacios.",
                )
                if err_user:
                    form_errors["username"] = err_user
                else:
                    err_user_min = _validar_longitud_min(
                        username, 4, "El nombre de usuario"
                    )
                    if err_user_min:
                        form_errors["username"] = err_user_min
                    else:
                        err_user_max = _validar_longitud_max(
                            username, 20, "El nombre de usuario"
                        )
                        if err_user_max:
                            form_errors["username"] = err_user_max
            if new_password:
                if len(new_password) < 6:
                    form_errors["new_password"] = (
                        "La contraseña debe tener al menos 6 caracteres."
                    )
                elif new_password != confirm_password:
                    form_errors["confirm_password"] = (
                        "Las contraseñas nuevas no coinciden."
                    )

            if not form_errors:
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
                    {
                        "text": "Configuración actualizada correctamente.",
                        "type": "success",
                    }
                ]
                return redirect("configuracion")

        # In case of validation error, re-render values typed
        usuario_data = {"username": username}
        persona_data = {"email": email}
        page_messages.append(
            {
                "text": "Por favor, corrige los errores en el formulario.",
                "type": "error",
            }
        )
        return render(
            request,
            "pages/configuracion.html",
            {
                "usuario": usuario_data,
                "persona": persona_data,
                "page_messages": page_messages,
                "form_errors": form_errors,
            },
        )

    return render(
        request,
        "pages/configuracion.html",
        {
            "usuario": usuario,
            "persona": persona,
            "page_messages": page_messages,
            "form_errors": form_errors,
        },
    )


# ─── SELECCION (EDITAR / ELIMINAR) ──────────────────────────────


@_login_required
@_admin_required
def seleccionar_usuario_view(request, accion):
    usuarios = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("usuarioedificio_set__id_edificio")
        .exclude(rol__in=ADMIN_ROLES)
    )
    items = []
    for u in usuarios:
        p = u.id_persona
        ue = u.usuarioedificio_set.first()
        edificio = ue.id_edificio if ue else None
        items.append(
            {
                "id": u.id_usuario,
                "nombre": f"{p.name} {p.apellido}".strip() if p else u.username,
                "cedula": p.ci if p else "",
                "edificio": edificio.nb_edificio if edificio else "",
            }
        )
    return render(
        request,
        "pages/seleccionar_usuario.html",
        {
            "items": items,
            "accion": accion,
        },
    )


@_login_required
@_admin_required
def seleccionar_edificio_view(request, accion):
    edificios = Edificio.objects.all()
    items = [
        {
            "id": e.id_edificio,
            "nombre": e.nb_edificio,
            "rif": e.rif,
        }
        for e in edificios
    ]
    return render(
        request,
        "pages/seleccionar_edificio.html",
        {
            "items": items,
            "accion": accion,
        },
    )


# ─── HISTORIAL ──────────────────────────────────────────────────


def _parse_notif_for_historial(notif):
    """Reutiliza la lógica de parseo de notificaciones para el historial.
    Usa los diccionarios centralizados de sensor_config.py."""
    import re
    import json as _json

    var_names = VAR_NAMES
    units = UNITS
    risk_names_es = RISK_NAMES_ES
    device_names_es = DEVICE_NAMES_ES

    def _translate_devices(text):
        for en, es in device_names_es.items():
            text = re.sub(rf"\b{re.escape(en)}\b", es, text, flags=re.IGNORECASE)
        return text

    def _build_protection_action(risk, raw_action):
        risk_es = risk_names_es.get(risk, risk.lower())
        devices_match = re.search(r"[Dd]ispositivos?\s+apagados?:\s*(.+)", raw_action)
        if devices_match:
            devices_es = _translate_devices(devices_match.group(1).rstrip("."))
            return f"Protección automática activada (alerta {risk_es}). Dispositivos apagados: {devices_es}."
        return f"Protección automática activada (alerta {risk_es}). {_translate_devices(raw_action)}"

    def _make_parsed(risk, variable, value, action):
        var_display = var_names.get(variable, variable.replace("_", " ").title())
        value_str = str(value).lower().strip() if value is not None else ""

        # Traducir valores especiales de sensores
        if variable in VALUE_DISPLAY_ES:
            value_display = VALUE_DISPLAY_ES[variable].get(value_str, str(value).capitalize())
        elif value_str == "pump":
            value_display = "Bomba de agua"
        elif value_str == "elevator":
            value_display = "Ascensor"
        elif value_str in device_names_es:
            value_display = device_names_es[value_str].capitalize()
        elif value_str:
            value_display = value_str.capitalize()
        else:
            value_display = ""

        if variable == "Protección automática":
            action = _build_protection_action(risk, action)
        elif variable.startswith("Protección "):
            action = _translate_devices(action)
        return {
            "parsed": True,
            "risk": risk,
            "variable": var_display,
            "value": value_display,
            "unit": units.get(variable, ""),
            "action": action,
        }

    raw = (notif.mensaje or "").strip()
    parsed_data = None

    if raw.startswith("{"):
        try:
            data = _json.loads(raw)
            parsed_data = _make_parsed(
                risk=data.get("risk", ""),
                variable=data.get("variable", ""),
                value=data.get("value") or "",
                action=data.get("action", ""),
            )
        except (ValueError, KeyError):
            parsed_data = None

    if parsed_data is None:
        m = re.match(r"^\[(.*?)\]\s+(.*?)\s+=\s+(.*?)\s+-\s+(.*)$", raw)
        if m:
            parsed_data = _make_parsed(
                risk=m.group(1).strip(),
                variable=m.group(2).strip(),
                value=m.group(3).strip(),
                action=m.group(4).strip(),
            )

    if parsed_data is None:
        pm = re.match(
            r"Protecci[oó]n autom[áa]tica activada\s*\(Alerta\s+(\w+)\s+de\s+(\w+)\).+\s*Dispositivos\s+apagados:\s*(.+)",
            raw,
            re.IGNORECASE,
        )
        if pm:
            p_risk = pm.group(1).strip().capitalize()
            p_variable = pm.group(2).strip()
            p_devices_es = _translate_devices(pm.group(3).rstrip("."))
            p_risk_es = risk_names_es.get(p_risk, p_risk.lower())
            p_var_es = var_names.get(p_variable, p_variable.replace("_", " "))
            parsed_data = {
                "parsed": True,
                "risk": p_risk,
                "variable": "Protección automática",
                "value": "True",
                "unit": "",
                "action": (
                    f"Protección automática activada ({p_var_es} {p_risk_es}). "
                    f"Dispositivos apagados: {p_devices_es}."
                ),
            }

    notif.parsed_data = parsed_data or {"parsed": False}
    return notif


@_login_required
def historial_view(request):
    from django.core.paginator import Paginator

    usuario_id = request.session["usuario_id"]
    rol = request.session.get("usuario_rol", "US")

    # ── Leer filtros ────────────────────────────────────────────
    edificio_id = request.GET.get("edificio", "").strip()
    # Normalize: template may render Python None as the string "None"
    if edificio_id.lower() in ("", "none", "null"):
        edificio_id = ""
    severidad = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    periodo_seleccionado = request.GET.get("periodo", "24h").strip()
    fecha_desde_raw = request.GET.get("fecha_desde", "").strip()
    fecha_hasta_raw = request.GET.get("fecha_hasta", "").strip()

    # ── Construir queryset base ─────────────────────────────────
    if _is_admin_role(rol):
        edificios = Edificio.objects.all()
        notificaciones = Notificacion.objects.all()
        if edificio_id:
            notificaciones = notificaciones.filter(
                id_equipo_monitoreo__id_edificio_id=edificio_id
            )
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        edificios = Edificio.objects.filter(id_edificio__in=usuario_edificios)

        if edificio_id:
            if edificio_id.isdigit() and int(edificio_id) in list(usuario_edificios):
                notificaciones = Notificacion.objects.filter(
                    id_equipo_monitoreo__id_edificio_id=edificio_id
                )
            else:
                notificaciones = Notificacion.objects.none()
        else:
            equipos = EquipoMonitoreo.objects.filter(
                id_edificio_id__in=list(usuario_edificios)
            ).values_list("id_equipo_monitoreo", flat=True)
            notificaciones = Notificacion.objects.filter(
                id_usuario_id=usuario_id
            ) | Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos))

    # ── Filtro por severidad ─────────────────────────────────────
    ALL_SEVERITIES = ["Info", "Bajo", "Medio", "Alto", "Crítico"]
    if severidad and severidad in ALL_SEVERITIES:
        notificaciones = notificaciones.filter(mensaje__icontains=f'"risk": "{severidad}"') | \
                         notificaciones.filter(mensaje__icontains=f'"risk":"{severidad}"')

    # ── Filtro por período / rango de fechas (timezone-aware) ─────
    from django.utils import timezone as tz
    import datetime as dt

    now = tz.now()  # timezone-aware en hora de Venezuela (America/Caracas)
    DELTA_MAP = {
        "1h":  dt.timedelta(hours=1),
        "12h": dt.timedelta(hours=12),
        "24h": dt.timedelta(hours=24),
        "3d":  dt.timedelta(days=3),
        "7d":  dt.timedelta(days=7),
    }

    if periodo_seleccionado in DELTA_MAP:
        dt_desde = now - DELTA_MAP[periodo_seleccionado]
        notificaciones = notificaciones.filter(fecha__gte=dt_desde)
    elif periodo_seleccionado == "custom":
        if fecha_desde_raw:
            try:
                naive = dt.datetime.strptime(fecha_desde_raw, "%Y-%m-%d")
                notificaciones = notificaciones.filter(fecha__gte=tz.make_aware(naive))
            except ValueError:
                pass
        if fecha_hasta_raw:
            try:
                naive = dt.datetime.strptime(fecha_hasta_raw, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                notificaciones = notificaciones.filter(fecha__lte=tz.make_aware(naive))
            except ValueError:
                pass

    notificaciones = (
        notificaciones.select_related("id_usuario", "id_equipo_monitoreo__id_edificio")
        .distinct()
        .order_by("-fecha")
    )

    # Parsear todos para poder filtrar por variable
    parsed_list = []
    for notif in notificaciones:
        notif = _parse_notif_for_historial(notif)
        parsed_list.append(notif)

    # ── Filtro por variable (post-parseo) ─────────────────────────
    all_variables = sorted(set(
        n.parsed_data.get("variable", "")
        for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable")
    ))

    if variable_filter:
        parsed_list = [
            n for n in parsed_list
            if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable_filter
        ]

    # ── Paginación ────────────────────────────────────────────────
    paginator = Paginator(parsed_list, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Construir parámetros de query para la paginación (preservar filtros)
    query_params = []
    if edificio_id:
        query_params.append(f"edificio={edificio_id}")
    if severidad:
        query_params.append(f"severidad={severidad}")
    if variable_filter:
        query_params.append(f"variable={variable_filter}")
    query_params.append(f"periodo={periodo_seleccionado}")
    if periodo_seleccionado == "custom":
        if fecha_desde_raw:
            query_params.append(f"fecha_desde={fecha_desde_raw}")
        if fecha_hasta_raw:
            query_params.append(f"fecha_hasta={fecha_hasta_raw}")
    filter_query_string = "&".join(query_params)

    return render(
        request,
        "pages/historial.html",
        {
            "notificaciones": page_obj,
            "edificios": edificios,
            "selected_edificio_id": int(edificio_id) if edificio_id and edificio_id.isdigit() else None,
            "severidad": severidad,
            "variable_filter": variable_filter,
            "all_variables": all_variables,
            "fecha_desde": fecha_desde_raw,
            "fecha_hasta": fecha_hasta_raw,
            "filter_query_string": filter_query_string,
            "ALL_SEVERITIES": ALL_SEVERITIES,
            "rol": rol,
            "total_count": len(parsed_list),
            "periodo_seleccionado": periodo_seleccionado,
        },
    )


@_login_required
def historial_pdf_view(request):
    """Genera y descarga un PDF del historial filtrado con los mismos parámetros de la vista."""
    import datetime as dt

    usuario_id = request.session["usuario_id"]
    rol = request.session.get("usuario_rol", "US")

    edificio_id = request.GET.get("edificio", "").strip()
    if edificio_id.lower() in ("", "none", "null"):
        edificio_id = ""
    severidad = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    periodo_seleccionado = request.GET.get("periodo", "24h").strip()
    fecha_desde_raw = request.GET.get("fecha_desde", "").strip()
    fecha_hasta_raw = request.GET.get("fecha_hasta", "").strip()

    var_names = VAR_NAMES
    units = UNITS
    risk_names_es = RISK_NAMES_ES
    device_names_es = DEVICE_NAMES_ES

    # ── Construir queryset base ─────────────────────────────────
    if _is_admin_role(rol):
        notificaciones = Notificacion.objects.all()
        edificio_nombre = "Todos los edificios"
        if edificio_id:
            notificaciones = notificaciones.filter(id_equipo_monitoreo__id_edificio_id=edificio_id)
            try:
                edificio_nombre = Edificio.objects.get(id_edificio=edificio_id).nb_edificio
            except Edificio.DoesNotExist:
                pass
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        edificio_nombre = "Todos los edificios"
        if edificio_id:
            if edificio_id.isdigit() and int(edificio_id) in list(usuario_edificios):
                notificaciones = Notificacion.objects.filter(
                    id_equipo_monitoreo__id_edificio_id=edificio_id
                )
                try:
                    edificio_nombre = Edificio.objects.get(id_edificio=edificio_id).nb_edificio
                except Edificio.DoesNotExist:
                    pass
            else:
                notificaciones = Notificacion.objects.none()
        else:
            equipos = EquipoMonitoreo.objects.filter(
                id_edificio_id__in=list(usuario_edificios)
            ).values_list("id_equipo_monitoreo", flat=True)
            notificaciones = Notificacion.objects.filter(
                id_usuario_id=usuario_id
            ) | Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos))

    ALL_SEVERITIES = ["Info", "Bajo", "Medio", "Alto", "Crítico"]
    if severidad and severidad in ALL_SEVERITIES:
        notificaciones = notificaciones.filter(mensaje__icontains=f'"risk": "{severidad}"') | \
                         notificaciones.filter(mensaje__icontains=f'"risk":"{severidad}"')

    # ── Filtro por período (timezone-aware, hora Venezuela) ────────
    from django.utils import timezone as tz

    now = tz.now()
    DELTA_MAP = {
        "1h":  dt.timedelta(hours=1),
        "12h": dt.timedelta(hours=12),
        "24h": dt.timedelta(hours=24),
        "3d":  dt.timedelta(days=3),
        "7d":  dt.timedelta(days=7),
    }

    if periodo_seleccionado in DELTA_MAP:
        notificaciones = notificaciones.filter(fecha__gte=now - DELTA_MAP[periodo_seleccionado])
    elif periodo_seleccionado == "custom":
        if fecha_desde_raw:
            try:
                naive = dt.datetime.strptime(fecha_desde_raw, "%Y-%m-%d")
                notificaciones = notificaciones.filter(fecha__gte=tz.make_aware(naive))
            except ValueError:
                pass
        if fecha_hasta_raw:
            try:
                naive = dt.datetime.strptime(fecha_hasta_raw, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                notificaciones = notificaciones.filter(fecha__lte=tz.make_aware(naive))
            except ValueError:
                pass

    # Período para el PDF (texto descriptivo)
    periodo_label_map = {
        "1h":  "Última hora",
        "12h": "Últimas 12 horas",
        "24h": "Últimas 24 horas",
        "3d":  "Últimos 3 días",
        "7d":  "Últimos 7 días",
        "custom": f"Personalizado: {fecha_desde_raw or '?'} al {fecha_hasta_raw or '?'}",
    }
    rango = periodo_label_map.get(periodo_seleccionado, periodo_seleccionado)

    notificaciones = (
        notificaciones.select_related("id_equipo_monitoreo__id_edificio")
        .distinct()
        .order_by("-fecha")
    )

    parsed_list = []
    for notif in notificaciones:
        notif = _parse_notif_for_historial(notif)
        parsed_list.append(notif)

    if variable_filter:
        parsed_list = [
            n for n in parsed_list
            if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable_filter
        ]

    # ── Generar PDF ───────────────────────────────────────────────
    try:
        from fpdf import FPDF
        from io import BytesIO

        now = dt.datetime.now()

        class HistorialPDF(FPDF):
            def header(self):
                if self.page_no() == 1:
                    self.set_fill_color(10, 10, 10)
                    self.rect(10, 10, 190, 2, "F")
                    self.ln(5)
                else:
                    self.set_font("Helvetica", "I", 8)
                    self.set_text_color(95, 95, 95)
                    self.cell(0, 10, "INES - Historial de Eventos", 0, 0, "L")
                    self.cell(0, 10, f"Pagina {self.page_no()}", 0, 1, "R")
                    self.set_draw_color(10, 10, 10)
                    self.set_line_width(0.6)
                    self.line(10, 18, 200, 18)
                    self.ln(2)

            def footer(self):
                self.set_y(-15)
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(95, 95, 95)
                self.cell(0, 10, f"Generado por INES - Pagina {self.page_no()}", 0, 0, "C")

        pdf = HistorialPDF()
        pdf.set_line_width(0.6)
        pdf.add_page()

        # Título
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 12, "Historial de Eventos ", ln=1, align="L")
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(0, 8, "SISTEMA DE TELEMETRIA Y CONTROL", ln=1, align="L")
        pdf.ln(5)

        # Metadata
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(26, 26, 26)
        pdf.cell(0, 6, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1)
        pdf.cell(0, 6, f"Edificio: {edificio_nombre}", ln=1)
        pdf.cell(0, 6, f"Severidad: {severidad if severidad else 'Todas'}", ln=1)
        pdf.cell(0, 6, f"Variable: {variable_filter if variable_filter else 'Todas'}", ln=1)
        pdf.cell(0, 6, f"Rango: {rango}", ln=1)
        pdf.cell(0, 6, f"Total de eventos: {len(parsed_list)}", ln=1)
        pdf.ln(8)

        # Leyenda
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 7, "LEYENDA DE SEVERIDADES", ln=1)
        pdf.ln(1)
        levels = [
            ("Info", (249, 250, 251), (55, 65, 81), "Eventos informativos del sistema"),
            ("Bajo", (240, 253, 244), (22, 101, 52), "Valores normales de funcionamiento"),
            ("Medio", (255, 251, 235), (146, 64, 14), "Cerca del limite sugerido"),
            ("Alto", (255, 247, 237), (194, 65, 12), "Fuera de rango seguro"),
            ("Critico", (254, 242, 242), (153, 27, 27), "Estado de peligro, accion inmediata"),
        ]
        pdf.set_font("Helvetica", "", 8)
        for lbl, fill, text_c, desc in levels:
            pdf.set_fill_color(*fill)
            pdf.set_text_color(*text_c)
            pdf.set_draw_color(10, 10, 10)
            pdf.cell(28, 6, f"  {lbl}", 1, 0, "L", True)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(162, 6, f" {desc}", 1, 1, "L")
        pdf.ln(8)

        # Tabla de eventos
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(10, 10, 10)
        pdf.cell(0, 7, f"EVENTOS REGISTRADOS ({len(parsed_list)})", ln=1)
        pdf.ln(2)

        # Configurar columnas dinámicamente según si se muestran todos los edificios o uno específico
        mostrar_todos_edificios = (edificio_nombre == "Todos los edificios")
        if mostrar_todos_edificios:
            col_widths = [26, 26, 20, 30, 20, 68]
            col_headers = ["Fecha / Hora", "Edificio", "Severidad", "Variable", "Valor", "Accion recomendada"]
            col_aligns = ["L", "L", "C", "L", "C", "L"]
        else:
            col_widths = [38, 26, 40, 24, 62]
            col_headers = ["Fecha / Hora", "Severidad", "Variable", "Valor", "Accion recomendada"]
            col_aligns = ["L", "C", "L", "C", "L"]

        def draw_row(pdf_obj, widths, aligns, row_data, cell_fills=None, cell_texts=None):
            lines_per_col = []
            for w, text in zip(widths, row_data):
                t_str = str(text) if text is not None else ""
                t_str = t_str.encode("latin-1", errors="replace").decode("latin-1")
                lines = pdf_obj.multi_cell(w, 4, t_str, split_only=True)
                lines_per_col.append(lines)
            
            max_lines = max(len(lines) for lines in lines_per_col) if lines_per_col else 1
            line_height = 4.5
            row_height = max_lines * line_height
            
            if pdf_obj.get_y() + row_height > 270:
                pdf_obj.add_page()
                
            start_x = pdf_obj.get_x()
            start_y = pdf_obj.get_y()
            
            # Dibujar fondos
            for i in range(max_lines):
                pdf_obj.set_xy(start_x, start_y + (i * line_height))
                for j, lines in enumerate(lines_per_col):
                    w = widths[j]
                    fill_c = cell_fills[j] if (cell_fills and cell_fills[j]) else None
                    if fill_c:
                        pdf_obj.set_fill_color(*fill_c)
                        pdf_obj.cell(w, line_height, "", border=0, fill=True)
                    else:
                        pdf_obj.cell(w, line_height, "", border=0, fill=False)

            # Dibujar textos
            for i in range(max_lines):
                pdf_obj.set_xy(start_x, start_y + (i * line_height))
                for j, lines in enumerate(lines_per_col):
                    w = widths[j]
                    align = aligns[j]
                    txt = lines[i] if i < len(lines) else ""
                    if align == "L" and txt:
                        txt = f" {txt}"
                    
                    text_c = cell_texts[j] if (cell_texts and cell_texts[j]) else (26, 26, 26)
                    pdf_obj.set_text_color(*text_c)
                    pdf_obj.cell(w, line_height, txt, border=0, align=align, fill=False)
                    
            # Dibujar bordes
            curr_x = start_x
            pdf_obj.set_draw_color(10, 10, 10)
            for w in widths:
                pdf_obj.rect(curr_x, start_y, w, row_height)
                curr_x += w
                
            pdf_obj.set_xy(start_x, start_y + row_height)

        if parsed_list:
            # Cabecera
            pdf.set_font("Helvetica", "B", 8)
            draw_row(
                pdf,
                col_widths,
                col_aligns,
                col_headers,
                cell_fills=[(10, 10, 10)] * len(col_widths),
                cell_texts=[(255, 255, 255)] * len(col_widths)
            )

            pdf.set_font("Helvetica", "", 7)
            pdf.set_draw_color(10, 10, 10)

            risk_styles = {
                "Info":    ((249, 250, 251), (55, 65, 81)),
                "Bajo":    ((240, 253, 244), (22, 101, 52)),
                "Medio":   ((255, 251, 235), (146, 64, 14)),
                "Alto":    ((255, 247, 237), (194, 65, 12)),
                "Crítico": ((254, 242, 242), (153, 27, 27)),
            }

            for notif in parsed_list[:200]:  # Máx 200 filas
                risk = notif.parsed_data.get("risk", "")
                fill_c, text_c = risk_styles.get(risk, ((255, 255, 255), (26, 26, 26)))

                fecha_str = notif.fecha.strftime("%d/%m/%Y %H:%M") if notif.fecha else ""
                variable_str = notif.parsed_data.get("variable", notif.mensaje or "")
                valor_str = notif.parsed_data.get("value", "")
                if valor_str and valor_str.lower() not in ("true", "false", "none", ""):
                    unidad = notif.parsed_data.get("unit", "")
                    valor_str = f"{valor_str} {unidad}".strip()
                accion_str = notif.parsed_data.get("action", notif.mensaje or "")

                if mostrar_todos_edificios:
                    edificio_fila = notif.id_equipo_monitoreo.id_edificio.nb_edificio if (notif.id_equipo_monitoreo and notif.id_equipo_monitoreo.id_edificio) else "N/A"
                    row_data = [fecha_str, edificio_fila, risk, variable_str, valor_str, accion_str]
                    cell_fills = [None, None, fill_c, None, None, None]
                    cell_texts = [None, None, text_c, None, None, None]
                else:
                    row_data = [fecha_str, risk, variable_str, valor_str, accion_str]
                    cell_fills = [None, fill_c, None, None, None]
                    cell_texts = [None, text_c, None, None, None]

                draw_row(pdf, col_widths, col_aligns, row_data, cell_fills, cell_texts)
        else:
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(95, 95, 95)
            pdf.cell(0, 8, "No se encontraron eventos con los filtros aplicados.", ln=1)

        pdf_raw = pdf.output()
        pdf_bytes = bytes(pdf_raw) if isinstance(pdf_raw, (bytearray, memoryview)) else pdf_raw.encode("latin-1") if isinstance(pdf_raw, str) else bytes(pdf_raw)

        filename = f"historial_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except ImportError:
        return HttpResponse(
            "Error: fpdf2 no está instalado. Ejecute: pip install fpdf2",
            content_type="text/plain",
            status=500,
        )
    except Exception as e:
        return HttpResponse(
            f"Error generando PDF: {e}",
            content_type="text/plain",
            status=500,
        )


# ─── LEGACY ─────────────────────────────────────────────────────


def descargar_pdf_view(request):
    try:
        from fpdf import FPDF

        usuarios = (
            Usuario.objects.select_related("id_persona")
            .prefetch_related("usuarioedificio_set__id_edificio")
            .all()
        )
        beneficiarios = [_build_beneficiario_data(u) for u in usuarios]

        class PDF(FPDF):
            def header(self):
                self.set_font("Arial", "B", 14)
                self.cell(0, 10, "INES - Reporte General de Beneficiarios", 0, 1, "C")
                self.set_draw_color(37, 99, 235)
                self.set_line_width(0.5)
                self.line(10, 22, 200, 22)
                self.ln(10)

            def footer(self):
                self.set_y(-15)
                self.set_font("Arial", "I", 8)
                self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(240, 244, 248)

        # Headers
        pdf.cell(25, 8, "Cedula", 1, 0, "C", True)
        pdf.cell(45, 8, "Nombre", 1, 0, "C", True)
        pdf.cell(45, 8, "Apellido", 1, 0, "C", True)
        pdf.cell(45, 8, "Email", 1, 0, "C", True)
        pdf.cell(30, 8, "Edificio", 1, 1, "C", True)

        pdf.set_font("Arial", "", 9)
        for b in beneficiarios:
            pdf.cell(25, 8, str(b["cedula"]), 1, 0, "C")
            pdf.cell(45, 8, b["nombre"][:24], 1)
            pdf.cell(45, 8, b["apellido"][:24], 1)
            pdf.cell(45, 8, b["email"][:24], 1)
            pdf.cell(30, 8, b["edificio_nombre"][:18], 1, 1)

        pdf_raw = pdf.output()
        pdf_bytes = bytes(pdf_raw) if isinstance(pdf_raw, (bytearray, memoryview)) else pdf_raw.encode("latin-1") if isinstance(pdf_raw, str) else bytes(pdf_raw)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="reporte_beneficiarios.pdf"'
        return response

    except Exception:
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="reporte_beneficiarios.csv"'
        )
        response.write("\ufeff".encode("utf8"))  # BOM para Excel
        writer = csv.writer(response)
        writer.writerow(
            ["Cedula", "Nombre", "Apellido", "Email", "Telefono", "Edificio"]
        )
        usuarios = (
            Usuario.objects.select_related("id_persona")
            .prefetch_related("usuarioedificio_set__id_edificio")
            .all()
        )
        for u in usuarios:
            b = _build_beneficiario_data(u)
            writer.writerow(
                [
                    b["cedula"],
                    b["nombre"],
                    b["apellido"],
                    b["email"],
                    b["telefono"],
                    b["edificio_nombre"],
                ]
            )
        return response


def completar_registro_view(request):
    token = request.GET.get("token") or request.POST.get("token")
    if not token:
        return render(
            request,
            "pages/completar_registro.html",
            {"error": "Token de registro faltante o inválido."},
        )

    try:
        data = signing.loads(token, max_age=86400)  # 24 horas de validez
        user_id = data["user_id"]
        usuario = Usuario.objects.get(id_usuario=user_id)
    except (signing.BadSignature, signing.SignatureExpired, Usuario.DoesNotExist):
        return render(
            request,
            "pages/completar_registro.html",
            {"error": "El enlace de registro ha expirado o es inválido."},
        )

    form_error = None
    form_errors = {}

    # Pre-cargar datos del formulario si es necesario
    username_val = request.POST.get("username", "").strip()

    if request.method == "POST":
        password = request.POST.get("password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        if not username_val or not password or not confirm_password:
            form_error = "Todos los campos son obligatorios."
            if not username_val:
                form_errors["username"] = "Este campo es obligatorio."
            if not password:
                form_errors["password"] = "Este campo es obligatorio."
            if not confirm_password:
                form_errors["confirm_password"] = "Este campo es obligatorio."
        elif password != confirm_password:
            form_error = "Las contraseñas no coinciden."
            form_errors["confirm_password"] = "Las contraseñas no coinciden."
        elif len(password) < 6:
            form_error = "La contraseña debe tener al menos 6 caracteres."
            form_errors["password"] = "La contraseña debe tener al menos 6 caracteres."
        elif not REGEX_USERNAME.match(username_val):
            form_error = "El nombre de usuario solo acepta letras y números."
            form_errors["username"] = (
                "El nombre de usuario solo acepta letras y números."
            )
        else:
            # Validar que el username no esté en uso por OTRO usuario
            if (
                Usuario.objects.filter(username=username_val)
                .exclude(id_usuario=usuario.id_usuario)
                .exists()
            ):
                form_error = "El nombre de usuario ya está registrado."
                form_errors["username"] = "El nombre de usuario ya está registrado."
            else:
                usuario.username = username_val
                usuario.password = make_password(password)
                usuario.registrado = True
                usuario.save()
                messages.success(
                    request,
                    "Registro completado con éxito. Ahora puede iniciar sesión.",
                )
                return redirect("login")

    return render(
        request,
        "pages/completar_registro.html",
        {
            "usuario": usuario,
            "token": token,
            "username_val": username_val,
            "form_error": form_error,
            "form_errors": form_errors,
        },
    )


# ─── CONTROL DEL SIMULADOR ──────────────────────────────────────


@_login_required
def simulador_status_view(request):
    import socket
    from django.http import JsonResponse
    has_edificios = Edificio.objects.exists()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 5000))
            return JsonResponse({"running": True, "has_edificios": has_edificios})
    except Exception:
        return JsonResponse({"running": False, "has_edificios": has_edificios})


@_login_required
@_admin_required
def simulador_start_view(request):
    import subprocess
    import sys
    from django.http import JsonResponse
    
    # Check if already running
    import socket
    is_running = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 5000))
            is_running = True
    except Exception:
        pass

    if is_running:
        return JsonResponse({"status": "ok", "message": "El simulador ya está encendido."})

    # Get absolute path to app27.py
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parent_dir = os.path.dirname(api_dir)
    app27_path = os.path.join(parent_dir, "app27.py")

    if not os.path.exists(app27_path):
        return JsonResponse({"status": "error", "message": f"No se encontró el archivo del simulador en {app27_path}."})

    try:
        python_exe = sys.executable
        if python_exe.lower().endswith("python.exe"):
            python_exe = python_exe[:-10] + "pythonw.exe"
        # DETACHED_PROCESS = 0x00000008
        env = os.environ.copy()
        # CREATE_NO_WINDOW = 0x08000000, DETACHED_PROCESS = 0x00000008
        # Combined = 0x08000008
        subprocess.Popen(
            [python_exe, app27_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=0x08000008,
            env=env
        )
        return JsonResponse({"status": "ok", "message": "Simulador encendido correctamente."})
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"Error al encender el simulador: {str(e)}"})


@_login_required
@_admin_required
def simulador_stop_view(request):
    import subprocess
    from django.http import JsonResponse
    import socket
    
    is_running = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 5000))
            is_running = True
    except Exception:
        pass

    if not is_running:
        return JsonResponse({"status": "ok", "message": "El simulador ya está apagado."})

    try:
        # Find process ID listening on port 5000 (CREATE_NO_WINDOW = 0x08000000)
        output = subprocess.check_output("netstat -ano", shell=True, creationflags=0x08000000).decode("utf-8", errors="ignore")
        pid = None
        for line in output.splitlines():
            if ":5000" in line and "LISTENING" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    break
        
        if pid:
            subprocess.check_call(f"taskkill /F /PID {pid}", shell=True, creationflags=0x08000000)
            return JsonResponse({"status": "ok", "message": "Simulador apagado correctamente."})
        else:
            return JsonResponse({"status": "error", "message": "No se pudo determinar el PID del simulador en el puerto 5000."})
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"Error al apagar el simulador: {str(e)}"})


@_login_required
@_admin_required
def simulador_restart_view(request):
    import time
    from django.http import JsonResponse
    
    # 1. Stop
    import subprocess
    try:
        output = subprocess.check_output("netstat -ano", shell=True, creationflags=0x08000000).decode("utf-8", errors="ignore")
        pid = None
        for line in output.splitlines():
            if ":5000" in line and "LISTENING" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    break
        if pid:
            subprocess.check_call(f"taskkill /F /PID {pid}", shell=True, creationflags=0x08000000)
            time.sleep(1.5)
    except Exception:
        pass
        
    # 2. Start
    import sys
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parent_dir = os.path.dirname(api_dir)
    app27_path = os.path.join(parent_dir, "app27.py")

    if not os.path.exists(app27_path):
        return JsonResponse({"status": "error", "message": f"No se encontró el archivo del simulador en {app27_path}."})

    try:
        python_exe = sys.executable
        if python_exe.lower().endswith("python.exe"):
            python_exe = python_exe[:-10] + "pythonw.exe"
        env = os.environ.copy()
        env["NO_BROWSER"] = "1"
        subprocess.Popen(
            [python_exe, app27_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=0x08000008,
            env=env
        )
        return JsonResponse({"status": "ok", "message": "Simulador reiniciado correctamente."})
    except Exception as e:
        return JsonResponse({"status": "error", "message": f"Error al iniciar tras apagar: {str(e)}"})

