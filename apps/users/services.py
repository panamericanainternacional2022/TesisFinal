import os
import random
import smtplib
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from django.core import signing
from django.urls import reverse

from apps.users.models import Usuario, Persona

_ACTIVATION_EMAIL_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Account Activation - INES System</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f5f5f5; padding: 24px 0;">
    <tr>
      <td align="center">
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #0a0a0a; border-collapse: collapse;">
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #ffffff;">
              <span style="font-size: 14px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #0a0a0a;">SISTEMA INES</span>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #f5f5f5; border-left: 6px solid #0a0a0a;">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #5e5e5e; display: block; margin-bottom: 4px;">SYSTEM ACCESS</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Account Activation</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              <p style="margin: 0 0 16px 0;">Hola,</p>
              <p style="margin: 0 0 16px 0;">Se ha registrado su usuario en el Sistema de Monitoreo INES. Para poder acceder y utilizar todas las funciones de monitoreo y alertas de infraestructura de su edificio, es necesario que complete su registro.</p>
              <p style="margin: 0 0 24px 0;">Por favor, haga clic en el bot&oacute;n a continuaci&oacute;n para definir su nombre de usuario y contrase&ntilde;a:</p>
              <div style="margin: 24px 0; text-align: left;">
                <a href="{link}" target="_blank" style="background-color: #0a0a0a; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; display: inline-block; border-radius: 0px; border: 1px solid #0a0a0a;">Completar Registro</a>
              </div>
              <div style="margin: 24px 0; padding: 16px; background-color: #f5f5f5; border: 1px solid #e0e0e0; font-size: 12px; color: #5e5e5e;">
                <p style="margin: 0 0 8px 0; font-weight: 700;">Informaci&oacute;n de seguridad:</p>
                <p style="margin: 0 0 8px 0;">&bull; Este enlace es v&aacute;lido por 24 horas.</p>
                <p style="margin: 0;">&bull; Si usted no solicit&oacute; este registro, por favor ignore este correo.</p>
              </div>
              <p style="margin: 0; font-size: 12px; color: #9e9e9e;">Si el bot&oacute;n no funciona, copie y pegue la siguiente direcci&oacute;n en su navegador:<br>
              <a href="{link}" style="color: #0a0a0a; text-decoration: underline;">{link}</a></p>
            </td>
          </tr>
          <tr>
            <td style="padding: 16px 24px; border-top: 1px solid #e0e0e0; background-color: #f5f5f5; font-size: 11px; color: #6b6b6b; text-align: center;">
              Este es un mensaje generado de forma autom&aacute;tica por el Sistema de Monitoreo INES.<br>
              Por favor, no responda a este correo electr&oacute;nico.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

_ACTIVATION_EMAIL_PLAIN = """Hola,

Se ha registrado su usuario en el Sistema de Monitoreo INES.
Para completar su registro y poder acceder al sistema, por favor haga clic en el siguiente enlace y defina su nombre de usuario y contraseña:

{link}

Este enlace es valido por 24 horas.
Si usted no solicito este registro, por favor ignore este correo.
"""


def build_beneficiary_data(user: Usuario) -> dict:
    person = user.id_persona
    ue = user.building_assignments.first()
    building = ue.id_edificio if ue else None
    name = user.username
    last_name = ""
    id_number = ""
    email = ""
    phone = ""
    if person:
        id_number = person.ci
        name = person.name or user.username
        last_name = person.last_name or ""
        email = person.email or ""
        phone = person.phone or ""
    return {
        "id": user.id_usuario,
        "cedula": id_number,
        "nombre": name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "edificio_nombre": building.nb_edificio if building else "",
        "edificio_rif": building.rif if building else "",
        "edificio_direccion": building.direccion if building else "",
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


def _load_env_file() -> None:
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.strip().split("=", 1)
                        os.environ[key.strip()] = val.strip().strip("'\"")


def _get_smtp_config() -> dict:
    _load_env_file()
    return {
        "server": os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", 587)),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
    }


def send_activation_email(email: str, user_id: int, base_url: str) -> str:
    token = signing.dumps({"user_id": user_id, "email": email})
    link = f"{base_url}{reverse('complete_registration')}?token={token}"

    smtp = _get_smtp_config()
    if not smtp["user"] or not smtp["password"]:
        raise RuntimeError(
            "SMTP credentials not configured. Activation link: " + link
        )

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = smtp["user"]
        msg["To"] = email
        msg["Subject"] = "[INES] Activacion y Acceso al Sistema"

        body = _ACTIVATION_EMAIL_PLAIN.format(link=link)
        html_content = _ACTIVATION_EMAIL_HTML.format(link=link)

        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        server = smtplib.SMTP(smtp["server"], smtp["port"])
        server.starttls()
        server.login(smtp["user"], smtp["password"])
        server.send_message(msg)
        server.quit()
        return link
    except Exception as e:
        raise RuntimeError(f"Failed to send activation email: {e}") from e
