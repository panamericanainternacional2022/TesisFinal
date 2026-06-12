from apps.users.validators import (
    _validar_campo, _validar_longitud_min, _validar_longitud_max,
    _validar_rif, REGEX_SOLO_LETRAS, REGEX_DIRECCION,
)
from apps.buildings.models import Edificio


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
