import random
import string
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from django.core import signing
from django.urls import reverse

from apps.users.models import Usuario, Persona


def _build_beneficiario_data(usuario):
    persona = usuario.id_persona
    ue = usuario.usuarioedificio_set.first()
    edificio = ue.id_edificio if ue else None
    nombre = usuario.username
    apellido = ""
    cedula = ""
    email = ""
    telefono = ""
    if persona:
        cedula = persona.ci
        nombre = persona.name or usuario.username
        apellido = persona.apellido or ""
        email = persona.email or ""
        telefono = persona.telefono or ""
    return {
        "id": usuario.id_usuario,
        "cedula": cedula,
        "nombre": nombre,
        "apellido": apellido,
        "email": email,
        "telefono": telefono,
        "edificio_nombre": edificio.nb_edificio if edificio else "",
        "edificio_rif": edificio.rif if edificio else "",
        "edificio_direccion": edificio.direccion if edificio else "",
        "registrado": usuario.registrado,
    }


def _generate_random_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _build_random_username(primer_nombre, primer_apellido):
    primer_nombre = primer_nombre.strip()
    primer_apellido = primer_apellido.strip()
    if not primer_nombre or not primer_apellido:
        return None
    base_username = (
        f"{primer_nombre[0].upper()}{primer_apellido.split()[0].capitalize()}"
    )
    username = base_username
    counter = 1
    while Usuario.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    return username


def _send_activation_email(email, user_id, request):
    token = signing.dumps({"user_id": user_id, "email": email})
    protocol = "https" if request.is_secure() else "http"
    host = request.get_host()
    link = f"{protocol}://{host}{reverse('completar_registro')}?token={token}"

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

    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        print(f"⚠️ Credenciales SMTP no configuradas. Link de registro: {link}")
        return False, link

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = smtp_user
        msg["To"] = email
        msg["Subject"] = "[INES] Activacion y Acceso al Sistema"

        body = f"""Hola,
        
Se ha registrado su usuario en el Sistema de Monitoreo INES.
Para completar su registro y poder acceder al sistema, por favor haga clic en el siguiente enlace y defina su nombre de usuario y contraseña:

{link}

Este enlace es valido por 24 horas.
Si usted no solicito este registro, por favor ignore este correo.
"""
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Activación de Cuenta - Sistema INES</title>
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
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #5e5e5e; display: block; margin-bottom: 4px;">ACCESO AL SISTEMA</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Activación de Cuenta</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              <p style="margin: 0 0 16px 0;">Hola,</p>
              <p style="margin: 0 0 16px 0;">Se ha registrado su usuario en el Sistema de Monitoreo INES. Para poder acceder y utilizar todas las funciones de monitoreo y alertas de infraestructura de su edificio, es necesario que complete su registro.</p>
              <p style="margin: 0 0 24px 0;">Por favor, haga clic en el botón a continuación para definir su nombre de usuario y contraseña:</p>
              
              <div style="margin: 24px 0; text-align: left;">
                <a href="{link}" target="_blank" style="background-color: #0a0a0a; color: #ffffff; text-decoration: none; padding: 12px 24px; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; display: inline-block; border-radius: 0px; border: 1px solid #0a0a0a;">Completar Registro</a>
              </div>
              
              <div style="margin: 24px 0; padding: 16px; background-color: #f5f5f5; border: 1px solid #e0e0e0; font-size: 12px; color: #5e5e5e;">
                <p style="margin: 0 0 8px 0; font-weight: 700;">Información de seguridad:</p>
                <p style="margin: 0 0 8px 0;">• Este enlace es válido por 24 horas.</p>
                <p style="margin: 0;">• Si usted no solicitó este registro, por favor ignore este correo.</p>
              </div>
              
              <p style="margin: 0; font-size: 12px; color: #9e9e9e;">Si el botón no funciona, copie y pegue la siguiente dirección en su navegador:<br>
              <a href="{link}" style="color: #0a0a0a; text-decoration: underline;">{link}</a></p>
            </td>
          </tr>
          <tr>
            <td style="padding: 16px 24px; border-top: 1px solid #e0e0e0; background-color: #f5f5f5; font-size: 11px; color: #6b6b6b; text-align: center;">
              Este es un mensaje generado de forma automática por el Sistema de Monitoreo INES.<br>
              Por favor, no responda a este correo electrónico.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        return True, link
    except Exception as e:
        print(f"Error enviando email de activacion: {e}")
        return False, link
