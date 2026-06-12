import time as _time

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.core import signing
from django.db import transaction, IntegrityError

from apps.core.auth_decorators import _login_required, _admin_required, ADMIN_ROLES
from apps.users.models import Usuario, Persona
from apps.buildings.models import Edificio, UsuarioEdificio
from apps.alerts.models import Notificacion
from apps.users.validators import (
    _validaciones_formulario_usuario, REGEX_USERNAME,
)
from apps.users.services import (
    _build_beneficiario_data, _build_random_username,
    _generate_random_password, _send_activation_email,
)
from django.db.models import Q


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
                    _alerts_dis = usuario.alerts_disabled
                    _alerts_until = usuario.alerts_disabled_until
                    if _alerts_dis and _alerts_until and _time.time() > _alerts_until:
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
    return render(request, "users/login.html", {"error": error})


def logout_view(request):
    request.session.flush()
    return redirect("login")


@_login_required
@_admin_required
def usuario_view(request):
    return render(request, "users/registro_usuario.html", {"user": {}})


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
        "users/lista_usuario.html",
        {
            "beneficiarios": beneficiarios,
            "edificios": edificios,
            "selected_edificio_id": int(edificio_id) if edificio_id.isdigit() else None,
        },
    )


@_login_required
@_admin_required
@transaction.atomic
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
            id_edificio = request.POST.get("id_edificio", "").strip()

            user_data = {
                "primerNombre": primer_nombre,
                "segundoNombre": segundo_nombre,
                "primerApellido": primer_apellido,
                "segundoApellido": segundo_apellido,
                "email": email,
                "cedula": cedula,
                "telefono": telefono,
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
                    generated_password = _generate_random_password(10)

                    if not primer_nombre or not primer_apellido:
                        form_error = "No se pudo generar un nombre de usuario. Verifica los datos ingresados."
                    else:
                        persona = Persona.objects.create(
                            ci=cedula,
                            name=nombre_completo,
                            apellido=apellido_completo,
                            email=email,
                            telefono=telefono,
                        )
                        _MAX_RETRIES = 10
                        _created = False
                        for _attempt in range(_MAX_RETRIES):
                            generated_username = _build_random_username(
                                primer_nombre, primer_apellido
                            )
                            if not generated_username:
                                form_error = "No se pudo generar un nombre de usuario."
                                break
                            try:
                                usuario = Usuario.objects.create(
                                    username=generated_username,
                                    password=make_password(generated_password),
                                    id_persona=persona,
                                    rol="US",
                                )
                            except IntegrityError:
                                continue
                            _created = True
                            break
                        if not _created and not form_error:
                            form_error = "No se pudo generar un nombre de usuario único tras varios intentos."
                        if _created and id_edificio:
                            UsuarioEdificio.objects.create(
                                id_usuario=usuario,
                                id_edificio_id=id_edificio,
                            )
                        email_sent, activation_link = _send_activation_email(
                            email, usuario.id_usuario, request
                        )

    email_sent = None
    edificios = Edificio.objects.all()
    context = {
        "user": user_data,
        "edificios": edificios,
        "form_error": form_error,
        "form_errors": form_errors,
    }
    if email_sent is not None:
        context["email_sent"] = email_sent
        context["activation_link"] = activation_link
        context["sent_to"] = email

    return render(
        request,
        "users/registro_usuario.html",
        context,
    )


@_login_required
@_admin_required
@transaction.atomic
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
        id_edificio = request.POST.get("id_edificio", "").strip()

        data = {
            "primerNombre": primer_nombre,
            "segundoNombre": segundo_nombre,
            "primerApellido": primer_apellido,
            "segundoApellido": segundo_apellido,
            "email": email,
            "cedula": cedula,
            "telefono": telefono,
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
                persona.save()

                if id_edificio:
                    UsuarioEdificio.objects.filter(id_usuario=usuario).delete()
                    UsuarioEdificio.objects.create(
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
            "id_edificio": id_edificio_actual,
        }

    usuario_edificio = UsuarioEdificio.objects.filter(id_usuario=usuario).first()
    edificio_actual = usuario_edificio.id_edificio if usuario_edificio else None
    edificios = Edificio.objects.all()
    return render(
        request,
        "users/registro_usuario.html",
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
        persona_id = usuario.id_persona_id
        usuario.delete()
        if persona_id:
            Persona.objects.filter(id_persona=persona_id).delete()
    messages.success(request, "Beneficiario eliminado correctamente.")
    return redirect("seleccionar_usuario", accion="eliminar")


@_login_required
@_admin_required
def seleccionar_usuario_view(request, accion):
    ACCIONES_VALIDAS = ("editar", "eliminar")
    if accion not in ACCIONES_VALIDAS:
        messages.error(request, f"Acción no válida: {accion}")
        return redirect("lista_usuario")
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
        "users/seleccionar_usuario.html",
        {
            "items": items,
            "accion": accion,
        },
    )


def completar_registro_view(request):
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
        usuario = Usuario.objects.get(id_usuario=user_id)
        if usuario.registrado:
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
    form_errors = {}
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
            form_errors["username"] = (
                "El nombre de usuario solo acepta letras y números."
            )
        else:
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
        "users/completar_registro.html",
        {
            "usuario": usuario,
            "token": token,
            "username_val": username_val,
            "email_val": email_val,
            "form_error": form_error,
            "form_errors": form_errors,
        },
    )
