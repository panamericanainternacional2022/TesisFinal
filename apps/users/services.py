import random
import string
from typing import Any

from django.core import signing
from django.urls import reverse

from apps.alerts.services.email_sender import send_email_raw, build_activation_email_html
from apps.users.models import Usuario

_ACTIVATION_EMAIL_PLAIN = """Hola,

Se ha registrado su usuario en el Sistema de Monitoreo INES.
Para completar su registro y poder acceder al sistema, por favor haga clic en el siguiente enlace y defina su nombre de usuario y contraseña:

{link}

Este enlace es válido por 24 horas.
Si usted no solicitó este registro, por favor ignore este correo.
"""


def build_user_data(user: Usuario) -> dict[str, Any]:
    person = user.id_persona
    ue = user.building_assignments.first()
    building = ue.building if ue else None
    name = user.username
    last_name = ""
    id_number = ""
    email = ""
    if person:
        id_number = person.ci
        parts = [person.first_name, person.middle_name]
        name = " ".join(p for p in parts if p) or user.username
        parts_l = [person.first_last_name, person.second_last_name]
        last_name = " ".join(p for p in parts_l if p)
        email = person.email or ""
    return {
        "id": user.id_usuario,
        "cedula": id_number,
        "nombre": name,
        "last_name": last_name,
        "email": email,
        "username": user.username,
        "edificio_nombre": building.name if building else "",
        "edificio_rif": building.rif if building else "",
        "edificio_direccion": building.address if building else "",
        "registered": user.registered,
    }


def generate_random_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def build_random_username(first_name: str, last_name: str) -> str:
    first_name = first_name.strip()
    last_name = last_name.strip()
    if not first_name or not last_name:
        raise ValueError("Both first_name and last_name are required.")
    base_username = (
        f"{first_name[0].upper()}{last_name.split()[0].capitalize()}"
    )
    username = base_username
    counter = 1
    while Usuario.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    return username


def send_activation_email(email: str, user_id: int, base_url: str) -> str:
    import os
    token = signing.dumps({"user_id": user_id, "email": email})
    link = f"{base_url}{reverse('complete_registration')}?token={token}"

    if not os.environ.get("SMTP_USER") or not os.environ.get("SMTP_PASSWORD"):
        raise RuntimeError(
            "SMTP credentials not configured. Activation link: " + link
        )

    plain_body = _ACTIVATION_EMAIL_PLAIN.format(link=link)
    html_body = build_activation_email_html(link)

    try:
        send_email_raw(
            to_addrs=[email],
            subject="[INES] Activación y acceso al sistema",
            html_body=html_body,
            plain_body=plain_body,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to send activation email: {e}") from e
    return link
