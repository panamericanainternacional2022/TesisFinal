from typing import Any

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from django.http import HttpRequest

from apps.users.models import Usuario, Persona
from apps.users.services import build_random_username


def extract_post_data(request: HttpRequest) -> dict[str, Any]:
    return {
        "primerNombre": request.POST.get("primerNombre", "").strip(),
        "segundoNombre": request.POST.get("segundoNombre", "").strip(),
        "primerApellido": request.POST.get("primerApellido", "").strip(),
        "segundoApellido": request.POST.get("segundoApellido", "").strip(),
        "email": request.POST.get("email", "").strip(),
        "cedula": request.POST.get("cedula", "").strip(),
        "id_edificio": request.POST.get("id_edificio", "").strip(),
    }


def has_required_fields(data: dict[str, Any]) -> bool:
    return bool(
        data.get("primerNombre")
        and data.get("primerApellido")
        and data.get("email")
        and data.get("cedula")
        and data.get("id_edificio")
    )


def build_required_field_errors(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    required = (
        "primerNombre",
        "primerApellido",
        "email",
        "cedula",
        "id_edificio",
    )
    for key in required:
        if not data.get(key):
            errors[key] = "Este campo es obligatorio."
    return errors


def create_user_with_retry(
    first_name: str,
    last_name: str,
    password: str,
    person: Persona,
    max_retries: int = 10,
) -> Usuario:
    for _ in range(max_retries):
        username = build_random_username(first_name, last_name)
        try:
            return Usuario.objects.create(
                username=username,
                password=make_password(password),
                id_persona=person,
                rol="US",
            )
        except IntegrityError:
            continue
    raise ValueError(
        "No se pudo generar un nombre de usuario único tras varios intentos."
    )


def build_edit_initial_data(user: Usuario, person: Persona) -> dict[str, Any]:
    from apps.buildings.models import UserBuilding

    current_ue = UserBuilding.objects.filter(user=user).first()
    current_building = current_ue.building if current_ue else None

    return {
        "primerNombre": person.name.split(" ")[0] if person and person.name else "",
        "segundoNombre": " ".join(person.name.split(" ")[1:])
        if person and person.name
        else "",
        "primerApellido": person.last_name.split(" ")[0]
        if person and person.last_name
        else "",
        "segundoApellido": " ".join(person.last_name.split(" ")[1:])
        if person and person.last_name
        else "",
        "email": person.email if person else "",
        "cedula": person.ci if person else "",
        "id_edificio": current_building.id if current_building else None,
    }
