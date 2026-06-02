import random
import re
import string

from django.shortcuts import render, redirect, get_object_or_404
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
    if len(digitos) < 7:
        return "El teléfono debe tener al menos 7 dígitos."
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
    campo = _validar_campo(
        data.get("primerNombre", ""),
        REGEX_SOLO_LETRAS,
        "El primer nombre solo acepta letras.",
    )
    if campo:
        errores["primerNombre"] = campo
    campo = _validar_longitud_max(data.get("primerNombre", ""), 20, "El primer nombre")
    if campo:
        errores["primerNombre_long"] = campo
    campo = _validar_campo(
        data.get("segundoNombre", ""),
        REGEX_SOLO_LETRAS,
        "El segundo nombre solo acepta letras.",
    )
    if campo:
        errores["segundoNombre"] = campo
    campo = _validar_longitud_max(
        data.get("segundoNombre", ""), 20, "El segundo nombre"
    )
    if campo:
        errores["segundoNombre_long"] = campo
    campo = _validar_campo(
        data.get("primerApellido", ""),
        REGEX_SOLO_LETRAS,
        "El primer apellido solo acepta letras.",
    )
    if campo:
        errores["primerApellido"] = campo
    campo = _validar_longitud_max(
        data.get("primerApellido", ""), 20, "El primer apellido"
    )
    if campo:
        errores["primerApellido_long"] = campo
    campo = _validar_campo(
        data.get("segundoApellido", ""),
        REGEX_SOLO_LETRAS,
        "El segundo apellido solo acepta letras.",
    )
    if campo:
        errores["segundoApellido"] = campo
    campo = _validar_longitud_max(
        data.get("segundoApellido", ""), 20, "El segundo apellido"
    )
    if campo:
        errores["segundoApellido_long"] = campo
    campo = _validar_campo(
        data.get("cedula", ""), REGEX_SOLO_NUMEROS, "La cédula solo acepta números."
    )
    if campo:
        errores["cedula"] = campo
    campo = _validar_longitud_max(data.get("cedula", ""), 8, "La cédula")
    if campo:
        errores["cedula_long"] = campo
    campo = _validar_email(data.get("email", ""))
    if campo:
        errores["email"] = campo
    campo = _validar_telefono(data.get("telefono", ""))
    if campo:
        errores["telefono"] = campo
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
    return render(request, "pages/usuario.html", {"user": {}})


@_login_required
@_admin_required
def lista_usuario_view(request):
    query = request.GET.get("q", "").strip()
    usuarios = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("usuarioedificio_set__id_edificio")
        .all()
    )
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
    return render(
        request,
        "pages/lista_usuario.html",
        {
            "beneficiarios": beneficiarios,
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
                primer_nombre and primer_apellido and email and cedula and id_edificio
            ):
                form_error = "Complete los campos obligatorios: nombre, apellido, email, cédula y edificio."
            else:
                errores_val = _validaciones_formulario_usuario(user_data)
                if errores_val:
                    form_error = " | ".join(errores_val.values())
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

    edificios = Edificio.objects.all()
    return render(
        request,
        "pages/usuario.html",
        {
            "user": user_data,
            "edificios": edificios,
            "generated_username": generated_username,
            "generated_password": generated_password,
            "form_error": form_error,
        },
    )


@_login_required
@_admin_required
def editar_beneficiario_view(request, beneficiario_id):
    usuario = get_object_or_404(Usuario, id_usuario=beneficiario_id)
    persona = usuario.id_persona

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

        if not (primer_nombre and primer_apellido and email and cedula and id_edificio):
            messages.error(
                request,
                "Complete los campos obligatorios (incluyendo edificio) para actualizar.",
            )
        else:
            errores_edit = _validaciones_formulario_usuario(
                {
                    "primerNombre": primer_nombre,
                    "segundoNombre": segundo_nombre,
                    "primerApellido": primer_apellido,
                    "segundoApellido": segundo_apellido,
                    "email": email,
                    "cedula": cedula,
                    "telefono": telefono,
                },
                exclude_persona_id=persona.id_persona,
            )
            if errores_edit:
                for err in errores_edit.values():
                    messages.error(request, err)
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

    usuario_edificio = UsuarioEdificio.objects.filter(id_usuario=usuario).first()
    edificio_actual = usuario_edificio.id_edificio if usuario_edificio else None
    id_edificio_actual = edificio_actual.id_edificio if edificio_actual else None

    data = {
        "primerNombre": persona.name.split(" ")[0] if persona and persona.name else "",
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

    edificios = Edificio.objects.all()
    return render(
        request,
        "pages/usuario.html",
        {
            "user": data,
            "editing": True,
            "beneficiario_id": beneficiario_id,
            "edificios": edificios,
            "edificio_actual": edificio_actual,
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
    return redirect("lista_usuario")


# ─── EDIFICIOS (ADMIN ONLY) ─────────────────────────────────────


@_login_required
@_admin_required
def registro_edificio_view(request):
    bld_msgs = request.session.pop("_bld_msg", [])
    if request.method == "POST":
        nombre = request.POST.get("nombreEdificio", "").strip()
        parroquia = request.POST.get("parroquia", "").strip()
        rif = request.POST.get("rif", "").strip()
        if not (nombre and rif):
            bld_msgs.append(
                {"text": "Complete el nombre del edificio y el RIF.", "type": "error"}
            )
            request.session["_bld_msg"] = bld_msgs
        else:
            errores_bld = _validaciones_formulario_edificio(
                {
                    "nombreEdificio": nombre,
                    "direccion": parroquia,
                    "rif": rif,
                }
            )
            if errores_bld:
                for err in errores_bld.values():
                    bld_msgs.append({"text": err, "type": "error"})
                request.session["_bld_msg"] = bld_msgs
            else:
                Edificio.objects.create(
                    nb_edificio=nombre,
                    rif=rif,
                    direccion=parroquia,
                )
                bld_msgs.append(
                    {"text": "Edificio registrado correctamente.", "type": "success"}
                )
                request.session["_bld_msg"] = bld_msgs
                return redirect("lista_edificios")
    return render(
        request,
        "pages/registro_edificio.html",
        {
            "editing": False,
            "page_messages": bld_msgs,
        },
    )


@_login_required
@_admin_required
def editar_edificio_view(request, edificio_id):
    edificio = get_object_or_404(Edificio, id_edificio=edificio_id)
    bld_msgs = request.session.pop("_bld_msg", [])
    if request.method == "POST":
        nombre = request.POST.get("nombreEdificio", "").strip()
        parroquia = request.POST.get("parroquia", "").strip()
        rif = request.POST.get("rif", "").strip()
        if not (nombre and rif):
            bld_msgs.append(
                {
                    "text": "Complete el nombre del edificio y el RIF para guardar los cambios.",
                    "type": "error",
                }
            )
            request.session["_bld_msg"] = bld_msgs
        else:
            errores_bld = _validaciones_formulario_edificio(
                {
                    "nombreEdificio": nombre,
                    "direccion": parroquia,
                    "rif": rif,
                },
                exclude_edificio_id=edificio_id,
            )
            if errores_bld:
                for err in errores_bld.values():
                    bld_msgs.append({"text": err, "type": "error"})
                request.session["_bld_msg"] = bld_msgs
            else:
                edificio.nb_edificio = nombre
                edificio.direccion = parroquia
                edificio.rif = rif
                edificio.save()
                bld_msgs.append(
                    {"text": "Edificio actualizado correctamente.", "type": "success"}
                )
                request.session["_bld_msg"] = bld_msgs
                return redirect("lista_edificios")
    return render(
        request,
        "pages/registro_edificio.html",
        {
            "editing": True,
            "edificio": edificio,
            "page_messages": bld_msgs,
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
        # Get all monitoring equipment associated with this building
        equipos = EquipoMonitoreo.objects.filter(id_edificio=edificio)
        
        # Get all sensors associated with those equipments
        sensores = EquipoSensor.objects.filter(id_equipo_monitoreo__in=equipos)
        
        # Get all status records associated with those equipments
        status_equipos = StatusEquipoMonitoreo.objects.filter(id_equipo_monitoreo__in=equipos)
        
        # Delete HistoricoFalla records that reference our sensors or equipment statuses
        HistoricoFalla.objects.filter(
            Q(id_equipo_sensor__in=sensores) | Q(id_status_equipo_monitoreo__in=status_equipos)
        ).delete()
        
        # Delete the sensors
        sensores.delete()
        
        # Delete status records
        status_equipos.delete()
        
        # Delete preventive actions
        AccionPrev.objects.filter(id_equipo_monitoreo__in=equipos).delete()
        
        # Delete notifications
        Notificacion.objects.filter(id_equipo_monitoreo__in=equipos).delete()
        
        # Delete the monitoring equipment
        equipos.delete()
        
        # Delete user-building associations
        UsuarioEdificio.objects.filter(id_edificio=edificio).delete()
        
        # Finally, delete the building
        edificio.delete()
        
    messages.success(request, "Edificio y todos sus datos asociados fueron eliminados correctamente.")
    return redirect("lista_edificios")


# ─── NOTIFICACIONES ─────────────────────────────────────────────


@_login_required
def notificaciones_view(request):
    usuario_id = request.session["usuario_id"]
    rol = request.session.get("usuario_rol", "US")
    if _is_admin_role(rol):
        notificaciones = Notificacion.objects.select_related(
            "id_usuario", "id_equipo_monitoreo__id_edificio"
        ).all().order_by("-fecha")
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        equipos = EquipoMonitoreo.objects.filter(
            id_edificio_id__in=list(usuario_edificios)
        ).values_list("id_equipo_monitoreo", flat=True)
        notificaciones = Notificacion.objects.filter(
            id_usuario_id=usuario_id
        ) | Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos))
        notificaciones = (
            notificaciones.select_related(
                "id_usuario", "id_equipo_monitoreo__id_edificio"
            )
            .distinct()
            .order_by("-fecha")
        )
    
    from django.core.paginator import Paginator
    paginator = Paginator(notificaciones, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "pages/notificaciones.html",
        {
            "notificaciones": page_obj,
            "rol": rol,
        },
    )


@_login_required
def limpiar_notificaciones_view(request):
    usuario_id = request.session["usuario_id"]
    rol = request.session.get("usuario_rol", "US")
    
    if _is_admin_role(rol):
        Notificacion.objects.all().delete()
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        equipos = EquipoMonitoreo.objects.filter(
            id_edificio_id__in=list(usuario_edificios)
        ).values_list("id_equipo_monitoreo", flat=True)
        
        Notificacion.objects.filter(id_usuario_id=usuario_id).delete()
        Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos)).delete()
        
    messages.success(request, "Se han limpiado las notificaciones correctamente.")
    return redirect("notificaciones")


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
            request.session["_cfg_msg"] = page_messages
            return redirect("configuracion")

        errores_cfg = {}
        if email:
            err_email = _validar_email(email)
            if err_email:
                errores_cfg["email"] = err_email
            else:
                err_email_unico = _validar_unico_email(
                    email, exclude_persona_id=persona.id_persona
                )
                if err_email_unico:
                    errores_cfg["email_unico"] = err_email_unico
        if username:
            err_user = _validar_campo(
                username,
                REGEX_USERNAME,
                "El nombre de usuario solo acepta letras y números, sin espacios.",
            )
            if err_user:
                errores_cfg["username"] = err_user
        if new_password:
            if len(new_password) < 6:
                errores_cfg["new_password"] = (
                    "La contraseña debe tener al menos 6 caracteres."
                )
            elif new_password != confirm_password:
                errores_cfg["confirm_password"] = "Las contraseñas nuevas no coinciden."

        if errores_cfg:
            for err in errores_cfg.values():
                page_messages.append({"text": err, "type": "error"})
            request.session["_cfg_msg"] = page_messages
            return redirect("configuracion")

        if email:
            persona.email = email
        if username:
            usuario.username = username
        if new_password:
            usuario.password = make_password(new_password)
        persona.save()
        usuario.save()
        request.session["usuario_username"] = usuario.username
        page_messages.append(
            {"text": "Configuración actualizada correctamente.", "type": "success"}
        )
        request.session["_cfg_msg"] = page_messages
        return redirect("configuracion")

    return render(
        request,
        "pages/configuracion.html",
        {
            "usuario": usuario,
            "persona": persona,
            "page_messages": page_messages,
        },
    )


# ─── SELECCION (EDITAR / ELIMINAR) ──────────────────────────────


@_login_required
@_admin_required
def seleccionar_usuario_view(request, accion):
    usuarios = (
        Usuario.objects.select_related("id_persona")
        .prefetch_related("usuarioedificio_set__id_edificio")
        .all()
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


# ─── LEGACY ─────────────────────────────────────────────────────

from django.http import HttpResponse


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

        output_data = pdf.output(dest="S")
        if isinstance(output_data, str):
            output_data = output_data.encode("latin1")

        response = HttpResponse(output_data, content_type="application/pdf")
        response["Content-Disposition"] = (
            'attachment; filename="reporte_beneficiarios.pdf"'
        )
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
