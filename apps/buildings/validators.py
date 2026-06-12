import re
from typing import Optional

from django.core.exceptions import ValidationError

from apps.buildings.models import Building


def validate_unique_rif(rif: str, exclude_building_id: Optional[int] = None) -> None:
    if not rif:
        return
    qs = Building.objects.filter(rif=rif)
    if exclude_building_id:
        qs = qs.exclude(id=exclude_building_id)
    if qs.exists():
        raise ValidationError("El RIF ya está registrado en otro edificio.")


def validate_building_form(
    data: dict, exclude_building_id: Optional[int] = None
) -> dict[str, str]:
    from apps.users.validators import REGEX_ONLY_LETTERS, REGEX_ADDRESS
    errors: dict[str, str] = {}

    _check_field(data, "nombreEdificio", REGEX_ONLY_LETTERS,
                 "El nombre del edificio solo acepta letras.", errors, "nombreEdificio")
    _check_min_length(data, "nombreEdificio", 3, "El nombre del edificio",
                      errors, "nombreEdificio_min")
    _check_max_length(data, "nombreEdificio", 20, "El nombre del edificio",
                      errors, "nombreEdificio_long")
    _check_field(data, "direccion", REGEX_ADDRESS,
                 "La dirección contiene caracteres no válidos.", errors, "direccion")
    _check_min_length(data, "direccion", 8, "La dirección",
                      errors, "direccion_min")
    _check_max_length(data, "direccion", 50, "La dirección",
                      errors, "direccion_long")
    _check_rif(data, errors)
    _check_unique_rif(data, exclude_building_id, errors)

    return errors


def _check_field(
    data: dict, key: str, regex: re.Pattern, msg: str,
    errors: dict[str, str], error_key: str,
) -> None:
    from apps.users.validators import _validate_field
    error = _validate_field(data.get(key, ""), regex, msg)
    if error:
        errors[error_key] = error


def _check_min_length(
    data: dict, key: str, minimum: int, label: str,
    errors: dict[str, str], error_key: str,
) -> None:
    from apps.users.validators import _validate_min_length
    error = _validate_min_length(data.get(key, ""), minimum, label)
    if error:
        errors[error_key] = error


def _check_max_length(
    data: dict, key: str, maximum: int, label: str,
    errors: dict[str, str], error_key: str,
) -> None:
    from apps.users.validators import _validate_max_length
    error = _validate_max_length(data.get(key, ""), maximum, label)
    if error:
        errors[error_key] = error


def _check_rif(data: dict, errors: dict[str, str]) -> None:
    from apps.users.validators import _validate_rif
    error = _validate_rif(data.get("rif", ""))
    if error:
        errors["rif"] = error


def _check_unique_rif(
    data: dict, exclude_building_id: Optional[int],
    errors: dict[str, str],
) -> None:
    try:
        validate_unique_rif(data.get("rif", ""), exclude_building_id)
    except ValidationError as e:
        errors["rif_unico"] = str(e)
