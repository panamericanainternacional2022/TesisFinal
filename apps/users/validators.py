import re

from apps.users.models import Persona

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

    campo = _validar_email(data.get("email", ""))
    if campo:
        errores["email"] = campo

    campo = _validar_telefono(data.get("telefono", ""))
    if campo:
        errores["telefono"] = campo

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
