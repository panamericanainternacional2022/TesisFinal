from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password

from apps.core.auth_decorators import _login_required, _admin_required
from apps.users.models import Usuario, Persona
from apps.buildings.models import Edificio, UsuarioEdificio, EquipoMonitoreo
from apps.buildings.services import _crear_equipos_para_edificio, _sincronizar_equipos_para_edificio
from apps.buildings.validators import _validaciones_formulario_edificio
from apps.users.validators import (
    _validar_campo, _validar_email, _validar_unico_email,
    _validar_longitud_min, _validar_longitud_max, REGEX_USERNAME,
)
from apps.users.services import _build_beneficiario_data
from django.db.models import Q
from django.db import transaction


@_login_required
@_admin_required
def registro_edificio_view(request):
    bld_msgs = request.session.pop("_bld_msg", [])
    form_errors = {}
    edificio_data = {}
    con_bomba = False
    con_elevador = False
    if request.method == "POST":
        nombre = request.POST.get("nombreEdificio", "").strip()
        parroquia = request.POST.get("parroquia", "").strip()
        rif = request.POST.get("rif", "").strip()
        con_bomba = request.POST.get("con_bomba") == "true"
        con_elevador = request.POST.get("con_elevador") == "true"

        edificio_data = {
            "nb_edificio": nombre,
            "direccion": parroquia,
            "rif": rif,
            "con_bomba": con_bomba,
            "con_elevador": con_elevador,
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
                edificio = Edificio.objects.create(
                    nb_edificio=nombre,
                    rif=rif,
                    direccion=parroquia,
                )
                _crear_equipos_para_edificio(edificio, con_bomba, con_elevador)
                request.session["_bld_msg"] = [
                    {"text": "Edificio registrado correctamente.", "type": "success"}
                ]
                return redirect("lista_edificios")
    return render(
        request,
        "buildings/registro_edificio.html",
        {
            "editing": False,
            "page_messages": bld_msgs,
            "form_errors": form_errors,
            "edificio": edificio_data,
            "con_bomba": con_bomba,
            "con_elevador": con_elevador,
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
        con_bomba = request.POST.get("con_bomba") == "true"
        con_elevador = request.POST.get("con_elevador") == "true"

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
                _sincronizar_equipos_para_edificio(edificio, con_bomba, con_elevador)
                request.session["_bld_msg"] = [
                    {"text": "Edificio actualizado correctamente.", "type": "success"}
                ]
                return redirect("lista_edificios")
    equipos_tipos = set(edificio.equipomonitoreo_set.values_list("tipo", flat=True))
    return render(
        request,
        "buildings/registro_edificio.html",
        {
            "editing": True,
            "edificio": edificio,
            "page_messages": bld_msgs,
            "form_errors": form_errors,
            "con_bomba": EquipoMonitoreo.TIPO_BOMBA in equipos_tipos,
            "con_elevador": EquipoMonitoreo.TIPO_ELEVADOR in equipos_tipos,
        },
    )


@_login_required
@_admin_required
def lista_edificios_view(request):
    query = request.GET.get("q", "").strip()
    edificios = Edificio.objects.all().prefetch_related("equipomonitoreo_set")
    if query:
        edificios = edificios.filter(
            Q(nb_edificio__icontains=query)
            | Q(rif__icontains=query)
            | Q(direccion__icontains=query)
        )
    bld_msgs = request.session.pop("_bld_msg", [])
    return render(
        request,
        "buildings/lista_edificios.html",
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
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        edificio.delete()

        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    messages.success(
        request, "Edificio y todos sus datos asociados fueron eliminados correctamente."
    )
    return redirect("seleccionar_edificio", accion="eliminar")


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
        "buildings/seleccionar_edificio.html",
        {
            "items": items,
            "accion": accion,
        },
    )


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
            "buildings/configuracion.html",
            {
                "usuario": usuario_data,
                "persona": persona_data,
                "page_messages": page_messages,
                "form_errors": form_errors,
            },
        )

    return render(
        request,
        "buildings/configuracion.html",
        {
            "usuario": usuario,
            "persona": persona,
            "page_messages": page_messages,
            "form_errors": form_errors,
        },
    )
