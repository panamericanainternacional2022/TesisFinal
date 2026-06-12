from typing import Optional

from apps.buildings.models import Edificio
from apps.users.validators import (
    _validate_field,
    _validate_min_length,
    _validate_max_length,
    _validate_rif,
    REGEX_ONLY_LETTERS,
    REGEX_ADDRESS,
)


def _validate_unique_rif(rif: str, exclude_edificio_id: Optional[int] = None) -> str:
    if not rif:
        return ""
    qs = Edificio.objects.filter(rif=rif)
    if exclude_edificio_id:
        qs = qs.exclude(id_edificio=exclude_edificio_id)
    if qs.exists():
        return "El RIF ya está registrado en otro edificio."
    return ""


def validate_building_form(
    data: dict, exclude_edificio_id: Optional[int] = None
) -> dict[str, str]:
    errors: dict[str, str] = {}

    error = _validate_field(
        data.get("nombreEdificio", ""),
        REGEX_ONLY_LETTERS,
        "El nombre del edificio solo acepta letras.",
    )
    if error:
        errors["nombreEdificio"] = error

    error = _validate_min_length(
        data.get("nombreEdificio", ""), 3, "El nombre del edificio"
    )
    if error:
        errors["nombreEdificio_min"] = error

    error = _validate_max_length(
        data.get("nombreEdificio", ""), 20, "El nombre del edificio"
    )
    if error:
        errors["nombreEdificio_long"] = error

    error = _validate_field(
        data.get("direccion", ""),
        REGEX_ADDRESS,
        "La dirección contiene caracteres no válidos.",
    )
    if error:
        errors["direccion"] = error

    error = _validate_min_length(data.get("direccion", ""), 8, "La dirección")
    if error:
        errors["direccion_min"] = error

    error = _validate_max_length(data.get("direccion", ""), 50, "La dirección")
    if error:
        errors["direccion_long"] = error

    error = _validate_rif(data.get("rif", ""))
    if error:
        errors["rif"] = error

    error = _validate_unique_rif(data.get("rif", ""), exclude_edificio_id)
    if error:
        errors["rif_unico"] = error

    return errors
