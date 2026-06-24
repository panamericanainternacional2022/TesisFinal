import re
from typing import Optional

from django.utils.translation import gettext_lazy as _

from apps.users.models import Persona

REGEX_ONLY_LETTERS: re.Pattern = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$")
REGEX_EMAIL: re.Pattern = re.compile(
    r"^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$"
)
REGEX_VENEZUELAN_CI: re.Pattern = re.compile(r"^[VEve]\-?\d{6,14}$")
REGEX_BUILDING_RIF: re.Pattern = re.compile(r"^[Jj]\-?\d{7,9}\-?\d$")
REGEX_ADDRESS: re.Pattern = re.compile(
    r"^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s\,\.\#\-\/\(\)]+$"
)
REGEX_USERNAME: re.Pattern = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+$")


FIELD_SPECS = [
    {
        "key": "primerNombre",
        "label": _("El primer nombre"),
        "regex": REGEX_ONLY_LETTERS,
        "regex_msg": _("El primer nombre solo acepta letras."),
        "min": 2,
        "max": 40,
    },
    {
        "key": "segundoNombre",
        "label": _("El segundo nombre"),
        "regex": REGEX_ONLY_LETTERS,
        "regex_msg": _("El segundo nombre solo acepta letras."),
        "min": 2,
        "max": 40,
    },
    {
        "key": "primerApellido",
        "label": _("El primer apellido"),
        "regex": REGEX_ONLY_LETTERS,
        "regex_msg": _("El primer apellido solo acepta letras."),
        "min": 2,
        "max": 40,
    },
    {
        "key": "segundoApellido",
        "label": _("El segundo apellido"),
        "regex": REGEX_ONLY_LETTERS,
        "regex_msg": _("El segundo apellido solo acepta letras."),
        "min": 2,
        "max": 40,
    },
    {
        "key": "cedula",
        "label": _("La cédula"),
        "regex": REGEX_VENEZUELAN_CI,
        "regex_msg": _("La cédula debe comenzar con V o E, seguida de 6 a 14 dígitos (ej: V-12345678)."),
        "min": 7,
        "max": 16,
    },
]


def _validate_field(value: str, regex: re.Pattern, message: str) -> str:
    if value and not regex.match(value):
        return message
    return ""


def _validate_min_length(value: str, minimum: int, label: str) -> str:
    if value and len(value) < minimum:
        return f"{label} debe tener al menos {minimum} caracteres."
    return ""


def _validate_max_length(value: str, maximum: int, label: str) -> str:
    if value and len(value) > maximum:
        return f"{label} no puede tener más de {maximum} caracteres."
    return ""


def normalize_ci(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[\.\-\s]", "", value).upper()
    if not cleaned:
        return ""
    if cleaned[0] in ("V", "E"):
        prefix = cleaned[0]
        numbers = cleaned[1:]
    else:
        prefix = "V"
        numbers = cleaned
    return f"{prefix}-{numbers}"


def normalize_rif(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[\.\-\s]", "", value).upper()
    if not cleaned:
        return ""
    if len(cleaned) >= 2:
        prefix = cleaned[0]
        numbers = cleaned[1:-1]
        dv = cleaned[-1]
        return f"{prefix}-{numbers}-{dv}"
    return cleaned


def _validate_rif(value: str) -> str:
    if not value:
        return _("El RIF es obligatorio.")
    cleaned = re.sub(r"[\.\-\s]", "", value).upper()
    if not REGEX_BUILDING_RIF.match(cleaned):
        return _(
            "El RIF del edificio debe comenzar con J, seguido de 7 a 9 dígitos y un dígito de control. Ej: J-12345678-0"
        )
    return ""


def _validate_email(value: str) -> str:
    if not value:
        return _("El email es obligatorio.")
    if not REGEX_EMAIL.match(value):
        return _("Ingresa un correo electrónico válido.")
    local = value.split("@")[0]
    if len(local) > 30:
        return _("La parte antes del @ no puede tener más de 30 caracteres.")
    if len(value) < 6:
        return _("El correo debe tener al menos 6 caracteres.")
    if len(value) > 75:
        return _("El correo no puede tener más de 75 caracteres.")
    return ""


def _validate_unique_email(email: str, exclude_persona_id: Optional[int] = None) -> str:
    qs = Persona.objects.filter(email=email)
    if exclude_persona_id:
        qs = qs.exclude(id_persona=exclude_persona_id)
    if qs.exists():
        return _("El correo electrónico ya está registrado por otro usuario.")
    return ""


def _validate_unique_ci(ci: str, exclude_persona_id: Optional[int] = None) -> str:
    if not ci:
        return ""
    normalized = normalize_ci(ci)
    qs = Persona.objects.filter(ci=normalized)
    if exclude_persona_id:
        qs = qs.exclude(id_persona=exclude_persona_id)
    if qs.exists():
        return _("La cédula ya está registrada por otro usuario.")
    return ""


def validate_user_form(data: dict, exclude_persona_id: Optional[int] = None) -> dict:
    errors: dict[str, str] = {}

    if "cedula" in data and data["cedula"]:
        data["cedula"] = normalize_ci(data["cedula"])

    for spec in FIELD_SPECS:
        key = spec["key"]
        value = data.get(key, "")

        error = _validate_field(value, spec["regex"], spec["regex_msg"])
        if error:
            errors[key] = error

        error = _validate_min_length(value, spec["min"], spec["label"])
        if error:
            errors[f"{key}_min"] = error

        error = _validate_max_length(value, spec["max"], spec["label"])
        if error:
            errors[f"{key}_long"] = error

    error = _validate_email(data.get("email", ""))
    if error:
        errors["email"] = error

    error = _validate_unique_email(data.get("email", ""), exclude_persona_id)
    if error:
        errors["email_unico"] = error

    error = _validate_unique_ci(data.get("cedula", ""), exclude_persona_id)
    if error:
        errors["cedula_unico"] = error

    return errors
