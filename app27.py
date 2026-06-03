#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema PCLogo - Monitoreo Avanzado con Gráficos de Barras y Alertas Reales
Ejecutar: python app.py
"""

import os
import sys
import threading
import time
import random
import smtplib
import logging
import webbrowser
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from io import BytesIO
from collections import deque

import requests
from flask import Flask, render_template_string, request, jsonify, send_file, Response
from flask_socketio import SocketIO, emit
import eventlet

# Parchado de eventlet para compatibilidad con Socket.IO y peticiones concurrentes
eventlet.monkey_patch()

# PDF
try:
    from fpdf import FPDF

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print(
        "fpdf2 no instalado. Reportes PDF no disponibles. Instale: pip install fpdf2"
    )

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Integración con Django para persistir alertas en la base de datos
# ----------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
DJANGO_CONNECTED = False
try:
    import django

    django.setup()
    from django.utils import timezone
    from core.models import Notificacion, EquipoMonitoreo, Edificio, Usuario, UsuarioEdificio, Persona

    DJANGO_CONNECTED = True
    logger.info("Django integrado correctamente en app27.py")
except Exception as e:
    logger.warning("No se pudo inicializar Django desde app27.py: %s", e)

# ----------------------------------------------------------------------
# Payload y estructura de datos para streaming en vivo
# ----------------------------------------------------------------------


def titleize_name(text):
    return " ".join(word.capitalize() for word in text.replace("_", " ").split())


def build_live_payload():
    stats = {}
    for var in [
        "temperature",
        "flow_rate",
        "pressure",
        "vibration",
        "tank_level",
        "load",
        "voltage",
        "current",
    ]:
        vals = [
            r["value"]
            for r in history
            if r["variable"] == var and isinstance(r["value"], (int, float))
        ]
        if vals:
            stats[var] = {
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }

    sensors = []
    for var, value in sensor_data.items():
        if var == "motor_stuck":
            risk, color = ("Crítico", "red") if value else ("Bajo", "green")
        else:
            risk, color = classify_risk(var, value)
        sensors.append(
            {
                "id": var,
                "nombre": titleize_name(var),
                "riesgo": risk,
                "color": color,
            }
        )

    recommendations = generate_recommendations(sensor_data, stats)

    return {
        "current": sensor_data,
        "sensors": sensors,
        "history": history[-100:],
        "thresholds": thresholds,
        "alert_enabled": alert_enabled,
        "alert_log": alert_log[:50],
        "stats": stats,
        "recommendations": recommendations,
        "rationing": sensor_data["flow_rate"] < RATIONING_THRESHOLD,
        "door_close_attempts": door_close_attempts,
        "protection_active": bool(protection_ends),
        "pump_on": pump_on,
        "elevator_on": elevator_on,
        "protection_remaining": int(max(0, max(protection_ends.values()) - time.time()))
        if protection_ends
        else 0,
        "protection_targets": list(protection_ends.keys()),
    }


# ----------------------------------------------------------------------
# Credenciales (ahora lee directamente desde el .env si existe)
# ----------------------------------------------------------------------
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    os.environ[key.strip()] = val.strip().strip("'\"")

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ----------------------------------------------------------------------
# Obtener destinatarios de email desde la BD Django por edificio
# ----------------------------------------------------------------------
def get_building_emails(edificio_id=None):
    if not DJANGO_CONNECTED:
        return []
    try:
        if not edificio_id:
            # Buscar el edificio del primer equipo de monitoreo disponible
            equipo = EquipoMonitoreo.objects.first()
            if equipo and equipo.id_edificio:
                edificio_id = equipo.id_edificio.id_edificio
            else:
                # Si no hay equipo, obtener el primer edificio
                first_edf = Edificio.objects.first()
                if first_edf:
                    edificio_id = first_edf.id_edificio
                else:
                    return []
        
        users = UsuarioEdificio.objects.filter(id_edificio_id=edificio_id).select_related('id_usuario__id_persona')
        emails = []
        for u in users:
            if u.id_usuario and u.id_usuario.id_persona and u.id_usuario.id_persona.email:
                email = u.id_usuario.id_persona.email.strip()
                if email and email not in emails:
                    emails.append(email)
        return emails
    except Exception as e:
        logger.error(f"Error al obtener correos del edificio {edificio_id}: {e}")
        return []


subscribers = {"email": {"Bajo": [], "Medio": [], "Alto": [], "Crítico": []}}

# ----------------------------------------------------------------------
# Umbrales de riesgo (configurables)
# ----------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    "flow_rate": {"direction": "higher", "low": 20, "medium": 35, "high": 45},
    "pressure": {"direction": "higher", "low": 5, "medium": 7, "high": 9},
    "temperature": {"direction": "higher", "low": 70, "medium": 85, "high": 100},
    "vibration": {"direction": "higher", "low": 4, "medium": 7, "high": 10},
    "tank_level": {"direction": "lower", "low": 30, "medium": 15, "high": 5},
    "speed": {"direction": "higher", "low": 1.5, "medium": 2.5, "high": 3.5},
    "load": {"direction": "higher", "low": 400, "medium": 700, "high": 900},
    "trip_count": {"direction": "higher", "low": 10000, "medium": 20000, "high": 30000},
    "energy": {"direction": "higher", "low": 8, "medium": 12, "high": 15},
    "voltage": {"direction": "range", "low": 200, "high": 240},
    "current": {"direction": "higher", "low": 30, "medium": 40, "high": 50},
}
NO_RISK_VARS = ["position", "door_status", "motor_stuck"]
RATIONING_THRESHOLD = 8.0
MAX_HISTORY_SIZE = 500

thresholds = DEFAULT_THRESHOLDS.copy()
alert_enabled = True
alert_log = []
last_email_sent_time = 0
pending_notifications = deque()
MAX_LOG_ENTRIES = 100
PROTECTION_HOLD_SECONDS = 8
PROTECTION_TOGGLE_INTERVAL = 8
SIMULATION_NORMAL_DURATION = 10
protection_active = False
pump_on = True
elevator_on = True
last_protection_toggle = time.time()
protection_end = 0
protection_targets = set()
active_alerts = {}
# No usamos fallas agendadas: las fallas se generan aleatoriamente y cada dispositivo es independiente
sensor_data = {
    "flow_rate": 15.0,
    "pressure": 4.0,
    "temperature": 50.0,
    "vibration": 2.0,
    "tank_level": 80.0,
    "position": 0,
    "speed": 0.0,
    "load": 200,
    "trip_count": 5000,
    "door_status": "closed",
    "energy": 5.0,
    "voltage": 220.0,
    "current": 20.0,
    "motor_stuck": False,
}
history = []

# Protección por dispositivo: mapping device -> protection_end_timestamp
protection_ends = {}
# Flag para activar logs de simulación
LOG_SIM = True
# Probabilidad de que la otra unidad falle simultáneamente (0-1)
SIMULTANEOUS_FAIL_PROB = 0.3
# Probabilidad de que un intento de cierre de puerta tenga éxito en un piso detenido
DOOR_CLOSE_SUCCESS_PROB = 0.25
# Probabilidad de que la puerta se abra por inactividad en piso detenido
DOOR_OPEN_PROB = 0.4
# Intentos máximos de cierre de puerta en piso sin ascenso/descenso
MAX_DOOR_CLOSE_ATTEMPTS = 2
# Contador de intentos fallidos de cierre de puerta
door_close_attempts = 0


# ----------------------------------------------------------------------
# Funciones auxiliares
# ----------------------------------------------------------------------
def get_unit(var):
    units = {
        "flow_rate": "L/s",
        "pressure": "bar",
        "temperature": "°C",
        "vibration": "mm/s",
        "tank_level": "%",
        "position": "piso",
        "speed": "m/s",
        "load": "kg",
        "trip_count": "viajes",
        "door_status": "",
        "energy": "kW",
        "voltage": "V",
        "current": "A",
        "motor_stuck": "",
    }
    return units.get(var, "")


def classify_risk(variable, value):
    if variable == "motor_stuck":
        return ("Crítico", "red") if value else ("Bajo", "green")
    if variable in NO_RISK_VARS:
        return "Bajo", "green"
    if variable in ("flow_rate", "pressure") and value == 0:
        return "Crítico", "red"
    if variable not in thresholds:
        return "Desconocido", "gray"
    cfg = thresholds[variable]
    d = cfg["direction"]
    if d == "range":
        low, high = cfg["low"], cfg["high"]
        return ("Bajo", "green") if low <= value <= high else ("Alto", "orange")
    else:
        low, med, high = cfg["low"], cfg["medium"], cfg["high"]
        if d == "higher":
            if value <= low:
                return "Bajo", "green"
            elif value <= med:
                return "Medio", "yellow"
            elif value <= high:
                return "Alto", "orange"
            else:
                return "Crítico", "red"
        else:
            if value >= low:
                return "Bajo", "green"
            elif value >= med:
                return "Medio", "yellow"
            elif value >= high:
                return "Alto", "orange"
            else:
                return "Crítico", "red"


def generate_recommendations(data, stats=None):
    recs = []
    if data["temperature"] > 85:
        recs.append("Temperatura del motor muy alta (>85°C). Revisar refrigeración.")
    elif data["temperature"] > 70:
        recs.append("Temperatura elevada. Monitorear.")
    if data["flow_rate"] < 10:
        recs.append("Caudal bajo (<10 L/s). Revisar bomba.")
    elif data["flow_rate"] < 20:
        recs.append("Caudal bajo óptimo. Revisar filtros.")
    if data["pressure"] > 8:
        recs.append("Presión excesiva (>8 bar). Riesgo de fugas.")
    if data["vibration"] > 7:
        recs.append("Vibración anómala (>7 mm/s). Verificar alineamiento.")
    if data["tank_level"] < 20:
        recs.append("Nivel de tanque crítico (<20%). Reposición urgente.")
    elif data["tank_level"] < 30:
        recs.append("Nivel de tanque bajo.")
    if data["load"] > 800:
        recs.append("Sobrepeso en ascensor (>800 kg). Reducir carga.")
    if data["voltage"] < 200 or data["voltage"] > 240:
        recs.append("Inestabilidad eléctrica. Revisar suministro.")
    if data["current"] > 45:
        recs.append("Sobrecarga eléctrica (corriente >45A).")
    if data["motor_stuck"]:
        recs.append("MOTOR PEGADO. Mantenimiento urgente.")
    at_floor = abs(data["position"] - round(data["position"])) < 0.05
    if (
        data["speed"] == 0
        and at_floor
        and door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS
    ):
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} DOORS: speed={data['speed']} at_floor={at_floor} door_close_attempts={door_close_attempts} position={data['position']}"
            )
        recs.append(
            f"Revisar puertas: {door_close_attempts} intentos de cierre fallidos."
        )
    if not recs:
        recs.append("Todos los parámetros normales. Operación estable.")
    return recs[:5]


def reset_critical_values(targets):
    """Resetear valores críticos asociados a los dispositivos deshabilitados para evitar re-triggers inmediatos."""
    global sensor_data
    if not targets:
        return
    if "pump" in targets:
        sensor_data["flow_rate"] = 25.0
        sensor_data["pressure"] = 4.0
        sensor_data["temperature"] = 50.0
        sensor_data["vibration"] = 1.5
        sensor_data["tank_level"] = 80.0
        sensor_data["voltage"] = 220.0
        sensor_data["current"] = 18.0
    if "elevator" in targets:
        sensor_data["position"] = 0
        sensor_data["speed"] = 0.0
        sensor_data["load"] = 200
        sensor_data["motor_stuck"] = False
        sensor_data["door_status"] = "closed"
        sensor_data["energy"] = 5.0
        sensor_data["temperature"] = 50.0
        global door_close_attempts
        door_close_attempts = 0


# Se eliminó la lógica de fallas agendadas. Las fallas se generan aleatoriamente
# durante `update_sensor_data()` y son manejadas por protección por dispositivo.


# ----------------------------------------------------------------------
# Envío de alertas (reales si hay credenciales)
# ----------------------------------------------------------------------
def send_email_alert(
    risk_level, subject, body, attachment_pdf=None, attachment_name="reporte.pdf", recipients=None
):
    if recipients is None:
        recipients = get_building_emails()
    if not recipients:
        logger.info(f"No hay suscriptores para nivel {risk_level} en email")
        return
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            f"⚠️ CREDENCIALES SMTP NO CONFIGURADAS. No se enviará email real a {recipients}."
        )
        return
    try:
        # Definir colores según riesgo al estilo Swiss (design-tokens.css)
        if risk_level == "Bajo":
            bg_color = "#f0fdf4"
            border_color = "#bbf7d0"
            text_color = "#16a34a"
        elif risk_level == "Medio":
            bg_color = "#fffbeb"
            border_color = "#fde68a"
            text_color = "#b45309"
        elif risk_level in ("Alto", "Crítico"):
            bg_color = "#fef2f2"
            border_color = "#fecaca"
            text_color = "#dc2626"
        else:
            bg_color = "#f5f5f5"
            border_color = "#e0e0e0"
            text_color = "#6b6b6b"

        # Formatear el cuerpo de texto plano a HTML estructurado
        lines = body.strip().split('\n')
        html_paragraphs = []
        in_details = False
        in_actions = False
        details_rows = []
        action_text = ""
        
        for line in lines:
            line_strip = line.strip()
            if not line_strip:
                continue
            if "DETALLES DEL EVENTO:" in line_strip:
                in_details = True
                in_actions = False
                continue
            elif "MEDIDAS CORRECTIVAS SUGERIDAS:" in line_strip:
                in_details = False
                in_actions = True
                continue
            elif line_strip.startswith("---") or line_strip.startswith("==="):
                continue
                
            if in_details:
                if ":" in line_strip:
                    parts = line_strip.split(":", 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    details_rows.append(f"""
                      <tr>
                        <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; font-weight: 700; width: 35%; color: #0a0a0a;">{key}</td>
                        <td style="padding: 10px 0; border-bottom: 1px solid #e0e0e0; color: #2e2e2e;">{val}</td>
                      </tr>
                    """)
                else:
                    if details_rows:
                        html_paragraphs.append(f"<p style='margin: 0 0 12px 0;'>{line_strip}</p>")
            elif in_actions:
                if line_strip.startswith("Accion:") or line_strip.startswith("Acción:"):
                    action_text = line_strip.split(":", 1)[1].strip()
                else:
                    action_text += " " + line_strip
            else:
                if "SISTEMA INES" in line_strip and "REPORTE" in line_strip:
                    html_paragraphs.append(f"<h2 style='margin: 0 0 16px 0; font-size: 16px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 2px solid #0a0a0a; padding-bottom: 8px;'>{line_strip}</h2>")
                else:
                    html_paragraphs.append(f"<p style='margin: 0 0 12px 0;'>{line_strip}</p>")

        formatted_content = "".join(html_paragraphs)
        if details_rows:
            formatted_content += f"""
            <h3 style="margin: 20px 0 10px 0; font-size: 13px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #0a0a0a;">Detalles del Evento</h3>
            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse; margin-bottom: 24px; font-size: 13px;">
              {"".join(details_rows)}
            </table>
            """
        if action_text:
            formatted_content += f"""
            <div style="margin: 24px 0; padding: 16px; background-color: {bg_color}; border: 1px solid {border_color}; border-left: 4px solid {text_color};">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: {text_color}; display: block; margin-bottom: 6px;">Medida Correctiva Recomendada</span>
              <p style="margin: 0; font-size: 13px; font-weight: 500; color: #0a0a0a; line-height: 1.4;">{action_text}</p>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; color: #0a0a0a;">
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f5f5f5; padding: 24px 0;">
    <tr>
      <td align="center">
        <!-- Contenedor Principal (Retícula Suiza - Bordes Rectos) -->
        <table border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border: 1px solid #0a0a0a; border-collapse: collapse;">
          <!-- Cabecera -->
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: #ffffff;">
              <span style="font-size: 14px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #0a0a0a;">SISTEMA INES</span>
            </td>
          </tr>
          <!-- Estado / Banner de Riesgo -->
          <tr>
            <td style="padding: 24px; border-bottom: 1px solid #0a0a0a; background-color: {bg_color}; border-left: 6px solid {text_color};">
              <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: {text_color}; display: block; margin-bottom: 4px;">NIVEL DE RIESGO: {risk_level.upper()}</span>
              <h1 style="margin: 0; font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; color: #0a0a0a;">Notificación de Alerta y Monitoreo</h1>
            </td>
          </tr>
          <!-- Contenido -->
          <tr>
            <td style="padding: 24px; font-size: 14px; line-height: 1.55; color: #2e2e2e;">
              {formatted_content}
            </td>
          </tr>
          <!-- Pie de página -->
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

        msg = MIMEMultipart('mixed')
        msg["From"] = SMTP_USER
        msg["Subject"] = subject

        # Agregar alternativas text/plain y text/html
        alt_part = MIMEMultipart('alternative')
        alt_part.attach(MIMEText(body, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_content, "html", "utf-8"))
        msg.attach(alt_part)

        if attachment_pdf:
            attachment_pdf.seek(0)
            part = MIMEApplication(attachment_pdf.read(), _subtype="pdf")
            part.add_header(
                "Content-Disposition", "attachment", filename=attachment_name
            )
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        for rec in recipients:
            if "To" in msg:
                del msg["To"]
            msg["To"] = rec
            server.send_message(msg)
            logger.info(f"✅ Email REAL enviado a {rec} (riesgo {risk_level})")
        server.quit()
    except Exception as e:
        logger.error(f"Error enviando email: {e}")


def persist_notification_in_django(variable, value, risk_level, recommended_action):
    if not DJANGO_CONNECTED:
        return
    try:
        equipo = (
            EquipoMonitoreo.objects.first()
            if EquipoMonitoreo.objects.exists()
            else None
        )
        Notificacion.objects.create(
            id_usuario_id=None,
            id_equipo_monitoreo=equipo,
            fecha=timezone.now(),
            mensaje=f"[{risk_level}] {variable} = {value} - {recommended_action}",
        )
    except Exception as e:
        logger.warning("No se pudo guardar notificación en la DB de Django: %s", e)


def enter_protection_mode(reason=None, targets=None):
    """Activar protección para los `targets` indicados (por dispositivo)."""
    global pump_on, elevator_on, protection_ends
    if not targets:
        logger.warning("Protección solicitada sin targets; no se hará nada.")
        return
    now = time.time()
    targets_set = set(targets)
    for device in targets_set:
        protection_ends[device] = now + PROTECTION_HOLD_SECONDS
        if device == "pump":
            pump_on = False
        elif device == "elevator":
            elevator_on = False
    reason_text = f" ({reason})" if reason else ""
    targets_text = " y ".join(sorted(targets_set))
    logger.warning(f"PROTECCIÓN ACTIVADA{reason_text}. Apagando: {targets_text}.")
    notification_payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variable": "Protección automática",
        "value": None,
        "risk": "Crítico",
        "message": f"Protección automática activada{reason_text}. Targets: {targets_text}.",
    }
    alert_log.insert(0, notification_payload)
    pending_notifications.append(notification_payload)
    try:
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass


def update_protection_state():
    """Restaurar dispositivos cuya protección expiró (por dispositivo)."""
    global pump_on, elevator_on, protection_ends
    now = time.time()
    expired = [d for d, end in protection_ends.items() if end and now >= end]
    for device in expired:
        if device == "pump":
            pump_on = True
        elif device == "elevator":
            elevator_on = True
        try:
            reset_critical_values({device})
        except Exception:
            logger.exception("Error reseteando valores críticos para %s", device)
        # Limpiar alertas activas relacionadas con el dispositivo
        try:
            if device == "pump":
                for v in [
                    "flow_rate",
                    "pressure",
                    "temperature",
                    "vibration",
                    "tank_level",
                    "voltage",
                    "current",
                    "Racionamiento",
                ]:
                    active_alerts.pop(v, None)
            elif device == "elevator":
                for v in [
                    "position",
                    "speed",
                    "load",
                    "trip_count",
                    "door_status",
                    "energy",
                    "motor_stuck",
                ]:
                    active_alerts.pop(v, None)
        except Exception:
            pass
        del protection_ends[device]
        logger.info("✅ Protección finalizada para %s. Dispositivo restaurado.", device)
        notification_payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "variable": f"Protección {device}",
            "value": None,
            "risk": "Info",
            "message": f"Protección finalizada para {device}. Operación normal restaurada.",
        }
        alert_log.insert(0, notification_payload)
        pending_notifications.append(notification_payload)
        try:
            socketio.emit("notification", notification_payload, broadcast=True)
        except Exception:
            pass


def get_professional_action(variable, risk_level, value):
    actions = {
        "flow_rate": {
            "Alto": "Flujo de agua elevado. Monitorear valvulas de alivio y posibles fugas.",
            "Crítico": "Caudal critico (interrupcion total o exceso grave). Apagado preventivo de bomba activado. Inspeccionar tuberia principal."
        },
        "pressure": {
            "Alto": "Presion superior al limite recomendado. Verificar regulador de presion y manometros.",
            "Crítico": "Presion critica. Riesgo inminente de ruptura de tuberias. Apagar bomba y liberar presion."
        },
        "temperature": {
            "Alto": "Temperatura elevada en el motor de la bomba. Incrementar ventilacion en sala de maquinas.",
            "Crítico": "Temperatura del motor critica. Riesgo de sobrecalentamiento y fundicion. Apagado de emergencia y revision de refrigeracion."
        },
        "vibration": {
            "Alto": "Nivel de vibracion por encima del estandar. Programar mantenimiento mecanico.",
            "Crítico": "Vibracion mecanica severa. Desalineacion severa o falla de rodamientos. Apagar equipo inmediatamente."
        },
        "tank_level": {
            "Alto": "Nivel de tanque elevado. Monitorear llenado automatico.",
            "Medio": "Nivel de tanque bajo.",
            "Crítico": "Nivel de tanque critico. Riesgo de cavitacion de la bomba. Detener succion y rellenar tanque urgentemente."
        },
        "speed": {
            "Alto": "Velocidad de ascensor por encima del limite de viaje seguro. Programar revision de variador de frecuencia.",
            "Crítico": "Exceso de velocidad critico. Frenado de emergencia activado. Inspeccion tecnica de seguridad obligatoria."
        },
        "load": {
            "Alto": "Carga de cabina cercana al limite de diseno. Monitorear comportamiento de motor.",
            "Crítico": "Sobrecarga en cabina de ascensor. Desalojar exceso de peso para reanudar operacion."
        },
        "energy": {
            "Alto": "Consumo de energia inusualmente elevado. Monitorear eficiencia.",
            "Crítico": "Pico de energia critico. Posible cortocircuito o sobreesfuerzo del motor. Revisar protecciones electricas."
        },
        "voltage": {
            "Alto": "Inestabilidad en voltaje (fuera del rango 200V-240V). Riesgo para componentes electronicos.",
            "Crítico": "Fluctuacion critica de tension electrica. Desconectar equipos para evitar danos."
        },
        "current": {
            "Alto": "Corriente de motor alta. Monitorear temperatura del bobinado.",
            "Crítico": "Amperaje critico (sobrecarga electrica). Apagado automatico de proteccion activo."
        },
        "motor_stuck": {
            "Crítico": "Eje del motor del ascensor trabado/bloqueado. Detener cabina y realizar liberacion de emergencia de pasajeros."
        },
        "Racionamiento": {
            "Crítico": "Caudal por debajo del minimo admisible (racionamiento de agua activo). Restringir consumo general."
        }
    }
    var_actions = actions.get(variable, {})
    return var_actions.get(risk_level, f"Verificar sensor {variable} (Valor actual: {value}). Programar revision preventiva.")


def send_alert(variable, value, risk_level, recommended_action):
    global active_alerts, last_email_sent_time
    if not alert_enabled:
        logger.info("Alertas desactivadas por el usuario")
        return
    if variable in active_alerts and active_alerts[variable] == risk_level:
        return
    active_alerts[variable] = risk_level
    device_target = None
    try:
        bomba_vars = [
            "flow_rate",
            "pressure",
            "temperature",
            "vibration",
            "tank_level",
            "voltage",
            "current",
        ]
        ascensor_vars = [
            "position",
            "speed",
            "load",
            "trip_count",
            "door_status",
            "energy",
            "motor_stuck",
        ]
        if variable in bomba_vars or variable == "Racionamiento":
            device_target = "pump"
        elif variable in ascensor_vars or variable == "motor_stuck":
            device_target = "elevator"
    except Exception:
        device_target = None
    if LOG_SIM:
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} ALERT: {variable}={value} level={risk_level} mapped={device_target} protection_ends={protection_ends}"
        )
    if risk_level in ("Alto", "Crítico"):
        if device_target:
            enter_protection_mode(
                f"Alerta {risk_level} de {variable}", targets={device_target}
            )
        else:
            logger.warning(
                f"Alerta crítica para {variable} sin mapeo a dispositivo; no se activará protección automática."
            )
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[INES - Alerta de Monitoreo] Estado {risk_level.upper()}: Anomalia en {variable.replace('_', ' ').title()}"
    body = f"""SISTEMA INES — REPORTE AUTOMATICO DE ANOMALIA

Se ha detectado una lectura fuera de los rangos operacionales recomendados en los sensores de monitoreo de la infraestructura.

DETALLES DEL EVENTO:
--------------------------------------------
Fecha/Hora:   {timestamp}
Parametro:    {variable.replace('_', ' ').upper()}
Lectura:      {value} {get_unit(variable)}
Nivel Riesgo: {risk_level.upper()}

MEDIDAS CORRECTIVAS SUGERIDAS:
--------------------------------------------
Accion:       {recommended_action}

Este es un mensaje de contingencia generado de forma automatica por el modulo de proteccion del Sistema INES. Por favor, proceda con la inspeccion tecnica correspondiente de los equipos implicados.
"""

    now = time.time()
    if now - last_email_sent_time > 300:  # 5 minutes cooldown
        last_email_sent_time = now
        threading.Thread(
            target=send_email_alert, args=(risk_level, subject, body), daemon=True
        ).start()

    notification_payload = {
        "timestamp": timestamp,
        "variable": variable,
        "value": value,
        "risk": risk_level,
        "message": recommended_action,
    }
    alert_log.insert(0, notification_payload)
    pending_notifications.append(notification_payload)
    persist_notification_in_django(variable, value, risk_level, recommended_action)
    try:
        socketio.emit("notification", notification_payload, broadcast=True)
    except Exception:
        pass
    while len(alert_log) > MAX_LOG_ENTRIES:
        alert_log.pop()


def check_rationing(flow_rate):
    if flow_rate < RATIONING_THRESHOLD:
        send_alert(
            "Racionamiento",
            flow_rate,
            "Crítico",
            f"Caudal muy bajo ({flow_rate} L/s). Reducir consumo.",
        )
        return True
    return False


def check_motor_stuck(speed, load, temperature):
    return speed == 0 and (load > 700 or temperature > 90)


# ----------------------------------------------------------------------
# Simulación de datos (cada 2 segundos)
# ----------------------------------------------------------------------
def update_sensor_data():
    global sensor_data
    # Generación de fallas aleatorias para bomba y ascensor (independientes)
    # Si un dispositivo está en protección, no cambiamos sus valores (se retiene la falla)
    # Inyectar falla de bomba aleatoria si no está protegida
    if "pump" not in protection_ends and pump_on and random.random() < 0.002:
        sensor_data["flow_rate"] = 0.0
        sensor_data["pressure"] = 0.0
        sensor_data["vibration"] = 12.0
        sensor_data["temperature"] = 85.0
        sensor_data["current"] = 40.0
        logger.info("Inyectada falla aleatoria: pump")
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: pump falla -> protection_ends={protection_ends}"
            )
        # posibilidad de fallo simultáneo en ascensor
        if (
            "elevator" not in protection_ends
            and elevator_on
            and random.random() < SIMULTANEOUS_FAIL_PROB
        ):
            sensor_data["speed"] = 0.0
            sensor_data["load"] = 950
            sensor_data["motor_stuck"] = True
            sensor_data["door_status"] = "closed"
            sensor_data["energy"] = 12.0
            sensor_data["temperature"] = 95.0
            logger.info("Inyectada falla simultánea: elevator")
            if LOG_SIM:
                print(
                    f"[SIM] {time.strftime('%H:%M:%S')} INYECCION-SIMULT: elevator falla -> protection_ends={protection_ends}"
                )
    # Inyectar falla de ascensor aleatoria si no está protegida
    if "elevator" not in protection_ends and elevator_on and random.random() < 0.002:
        sensor_data["speed"] = 0.0
        sensor_data["load"] = 950
        sensor_data["motor_stuck"] = True
        sensor_data["door_status"] = "closed"
        sensor_data["energy"] = 12.0
        sensor_data["temperature"] = 95.0
        logger.info("Inyectada falla aleatoria: elevator")
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: elevator falla -> protection_ends={protection_ends}"
            )
        # posibilidad de fallo simultáneo en bomba
        if (
            "pump" not in protection_ends
            and pump_on
            and random.random() < SIMULTANEOUS_FAIL_PROB
        ):
            sensor_data["flow_rate"] = 0.0
            sensor_data["pressure"] = 0.0
            sensor_data["vibration"] = 12.0
            sensor_data["temperature"] = 85.0
            sensor_data["current"] = 40.0
            logger.info("Inyectada falla simultánea: pump")
            if LOG_SIM:
                print(
                    f"[SIM] {time.strftime('%H:%M:%S')} INYECCION-SIMULT: pump falla -> protection_ends={protection_ends}"
                )
    pump_protected = "pump" in protection_ends or not pump_on
    elevator_protected = "elevator" in protection_ends or not elevator_on

    if pump_protected:
        # Mantener la falla de bomba durante la protección y evitar normalización prematura.
        sensor_data["flow_rate"] = round(max(0, min(60, sensor_data["flow_rate"])), 1)
        sensor_data["pressure"] = round(max(0, min(12, sensor_data["pressure"])), 1)
        sensor_data["temperature"] = round(
            max(20, min(130, sensor_data["temperature"])), 1
        )
        sensor_data["vibration"] = round(max(0, min(15, sensor_data["vibration"])), 1)
        sensor_data["tank_level"] = round(
            max(0, min(100, sensor_data["tank_level"])), 1
        )
        sensor_data["voltage"] = round(max(180, min(260, sensor_data["voltage"])), 1)
        sensor_data["current"] = round(max(0, min(70, sensor_data["current"])), 1)
    else:
        fd = sensor_data["flow_rate"] + random.uniform(-1.5, 1.5)
        if random.random() < 0.05:
            fd += random.uniform(5, 15)
        sensor_data["flow_rate"] = round(max(0, min(60, fd)), 1)
        sensor_data["current"] = round(
            max(
                0,
                min(
                    70,
                    sensor_data["current"]
                    + random.uniform(-1, 1)
                    + (sensor_data["load"] / 100) * 0.1,
                ),
            ),
            1,
        )

        p = (
            sensor_data["pressure"]
            + random.uniform(-0.3, 0.3)
            + (sensor_data["flow_rate"] - 20) * 0.02
        )
        sensor_data["pressure"] = round(max(0, min(12, p)), 1)
        t = (
            sensor_data["temperature"]
            + random.uniform(-0.5, 1.0)
            + max(0, (sensor_data["pressure"] - 5) * 0.2)
        )
        if random.random() < 0.03:
            t += random.uniform(5, 20)
        sensor_data["temperature"] = round(max(20, min(130, t)), 1)
        v = (
            sensor_data["vibration"]
            + random.uniform(-0.3, 0.5)
            + (sensor_data["flow_rate"] / 30)
            + (max(0, sensor_data["temperature"] - 70) / 20)
        )
        sensor_data["vibration"] = round(max(0, min(15, v)), 1)
        lvl = sensor_data["tank_level"] - sensor_data["flow_rate"] * 0.1
        if random.random() < 0.1:
            lvl += random.uniform(5, 15)
        sensor_data["tank_level"] = round(max(0, min(100, lvl)), 1)

    prev_pos = sensor_data["position"]
    prev_door = sensor_data["door_status"]
    pos = prev_pos
    spd = sensor_data["speed"]
    global door_close_attempts
    if not elevator_on:
        spd = 0
        sensor_data["door_status"] = "closed"
        door_close_attempts = 0
        # Mantener carga actual mientras el ascensor está en protección
        # (no reducirla automáticamente)
    else:
        if random.random() < 0.3:
            spd = random.choice([0, random.uniform(0.5, 2.5)])
        pos += spd * 2
        if pos > 20:
            pos, spd = 20, 0
        if pos < 0:
            pos, spd = 0, 0
        at_floor = abs(pos - round(pos)) < 0.05
        if spd != 0:
            sensor_data["door_status"] = "closed"
            door_close_attempts = 0
        else:
            if not at_floor:
                sensor_data["door_status"] = "closed"
                door_close_attempts = 0
            else:
                if prev_door == "open":
                    if door_close_attempts < MAX_DOOR_CLOSE_ATTEMPTS:
                        if random.random() < DOOR_CLOSE_SUCCESS_PROB:
                            sensor_data["door_status"] = "closed"
                        else:
                            sensor_data["door_status"] = "open"
                        door_close_attempts += 1
                        if LOG_SIM:
                            print(
                                f"[SIM] {time.strftime('%H:%M:%S')} DOORS_EVENT: increment attempts -> {door_close_attempts}"
                            )
                    else:
                        sensor_data["door_status"] = "open"
                elif door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
                    sensor_data["door_status"] = "open"
                else:
                    if random.random() < DOOR_OPEN_PROB:
                        sensor_data["door_status"] = "open"
                    else:
                        sensor_data["door_status"] = "closed"
        sensor_data["load"] = round(
            max(
                0,
                min(
                    1200,
                    sensor_data["load"]
                    + (random.randint(-100, 150) if random.random() < 0.2 else 0),
                ),
            )
        )
        if random.random() < 0.1:
            sensor_data["trip_count"] += 1
    # Reset attempts si el ascensor se mueve o cambia piso
    if abs(pos - prev_pos) > 0.1 or spd != 0:
        if door_close_attempts != 0 and LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} DOORS_EVENT: reset attempts (pos change or movement) -> was {door_close_attempts}"
            )
        door_close_attempts = 0
    sensor_data["position"] = round(pos, 1)
    sensor_data["speed"] = round(spd, 1)
    if elevator_protected:
        sensor_data["energy"] = round(max(0, min(20, sensor_data["energy"])), 1)
    else:
        energy = (sensor_data["load"] / 500) * spd * 2 + random.uniform(0.5, 2)
        sensor_data["energy"] = round(max(0, min(20, energy)), 1)
    if pump_protected:
        sensor_data["voltage"] = round(max(180, min(260, sensor_data["voltage"])), 1)
    else:
        volt = sensor_data["voltage"] + random.uniform(-3, 3)
        if random.random() < 0.02:
            volt += random.uniform(-20, 20)
        sensor_data["voltage"] = round(max(180, min(260, volt)), 1)
    curr = sensor_data["current"]
    if not pump_on:
        curr = round(max(0, curr), 1)
    else:
        curr = round(
            max(
                0,
                min(
                    70, curr + random.uniform(-1, 1) + (sensor_data["load"] / 100) * 0.1
                ),
            ),
            1,
        )
    sensor_data["current"] = curr
    stuck = check_motor_stuck(
        sensor_data["speed"], sensor_data["load"], sensor_data["temperature"]
    )
    sensor_data["motor_stuck"] = stuck


def generate_data_and_emit():
    while True:
        eventlet.sleep(5)
        update_protection_state()
        update_sensor_data()
        for var, value in sensor_data.items():
            if var == "motor_stuck":
                if value:
                    action = get_professional_action(var, "Crítico", value)
                    send_alert(
                        var, value, "Crítico", action
                    )
                else:
                    active_alerts.pop(var, None)
                continue
            risk, _ = classify_risk(var, value)
            if risk in ("Alto", "Crítico"):
                action = get_professional_action(var, risk, value)
                send_alert(
                    var, value, risk, action
                )
            else:
                active_alerts.pop(var, None)
        check_rationing(sensor_data["flow_rate"])
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        new_readings = []
        for var, value in sensor_data.items():
            risk, color = (
                classify_risk(var, value)
                if var != "motor_stuck"
                else ("Crítico" if value else "Bajo", "red" if value else "green")
            )
            sensor_type = (
                "Bomba"
                if var
                in [
                    "flow_rate",
                    "pressure",
                    "temperature",
                    "vibration",
                    "tank_level",
                    "voltage",
                    "current",
                ]
                else "Ascensor"
            )
            new_readings.append(
                {
                    "timestamp": timestamp,
                    "type": sensor_type,
                    "variable": var,
                    "value": value,
                    "risk": risk,
                    "color": color,
                }
            )
        global history
        history.extend(new_readings)
        if len(history) > MAX_HISTORY_SIZE:
            history = history[-MAX_HISTORY_SIZE:]
        stats = {}
        for var in [
            "temperature",
            "flow_rate",
            "pressure",
            "vibration",
            "tank_level",
            "load",
            "voltage",
            "current",
        ]:
            vals = [
                r["value"]
                for r in history
                if r["variable"] == var and isinstance(r["value"], (int, float))
            ]
            if vals:
                stats[var] = {
                    "avg": sum(vals) / len(vals),
                    "min": min(vals),
                    "max": max(vals),
                }
        payload = build_live_payload()
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} LOOP: pump_on={pump_on} elevator_on={elevator_on} protection_ends={protection_ends}"
            )
        socketio.emit("sensor_update", payload)


# ----------------------------------------------------------------------
# Reporte PDF mejorado (con diseño coherente con la web)
# ----------------------------------------------------------------------
class PDFReport(FPDF):
    def header(self):
        # Cabecera principal solo en la primera página o cabecera reducida en páginas posteriores
        if self.page_no() == 1:
            # Dibujar una línea negra gruesa superior (estilo minimalista de la web)
            self.set_fill_color(10, 10, 10)
            self.rect(10, 10, 190, 2, "F")
            self.ln(5)
        else:
            # Cabecera secundaria para páginas siguientes
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(95, 95, 95)
            self.cell(0, 10, "SISTEMA PCLogo - Reporte de Monitoreo", 0, 0, "L")
            self.cell(0, 10, f"Página {self.page_no()}", 0, 1, "R")
            self.set_draw_color(10, 10, 10)
            self.set_line_width(0.6)
            self.line(10, 18, 200, 18)
            self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(95, 95, 95)
        self.cell(0, 10, f"Generado por INES - Página {self.page_no()}", 0, 0, "C")


def generate_pdf_report(period):
    if not PDF_AVAILABLE:
        raise ImportError("fpdf2 no instalado")
    now = datetime.now()
    if period == "minute":
        start_time = now - timedelta(minutes=1)
        period_name = "Último minuto"
    elif period == "ten_minutes":
        start_time = now - timedelta(minutes=10)
        period_name = "Últimos 10 minutos"
    elif period == "hour":
        start_time = now - timedelta(hours=1)
        period_name = "Última hora"
    elif period == "day":
        start_time = now - timedelta(days=1)
        period_name = "Último día"
    elif period == "week":
        start_time = now - timedelta(days=7)
        period_name = "Última semana"
    else:
        start_time = now - timedelta(days=30)
        period_name = "Último mes"
    filtered_readings = [
        r
        for r in history
        if datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S") >= start_time
    ]
    numeric_vars = [
        "flow_rate",
        "pressure",
        "temperature",
        "vibration",
        "tank_level",
        "speed",
        "load",
        "trip_count",
        "energy",
        "voltage",
        "current",
    ]
    stats = {}
    for var in numeric_vars:
        vals = [
            r["value"]
            for r in filtered_readings
            if r["variable"] == var and isinstance(r["value"], (int, float))
        ]
        if vals:
            stats[var] = {
                "min": min(vals),
                "max": max(vals),
                "avg": sum(vals) / len(vals),
                "count": len(vals),
            }
        else:
            stats[var] = {"min": "N/A", "max": "N/A", "avg": "N/A", "count": 0}
    alerts_in_period = [
        a
        for a in alert_log
        if datetime.strptime(a["timestamp"], "%Y-%m-%d %H:%M:%S") >= start_time
    ]
    pdf = PDFReport()
    pdf.set_line_width(0.6)
    pdf.add_page()
    
    # Título principal minimalista
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, "INES", ln=1, align="L")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 8, "REPORTE DE MONITOREO AUTOMATIZADO", ln=1, align="L")
    pdf.ln(5)
    
    # Metadata del reporte
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(0, 6, f"Generado: {now.strftime('%d/%m/%Y %H:%M:%S')}", ln=1, align="L")
    pdf.cell(
        0,
        6,
        f"Periodo de Análisis: {period_name} (desde {start_time.strftime('%d/%m/%Y %H:%M:%S')})",
        ln=1,
        align="L",
    )
    pdf.ln(8)
    
    # Leyenda de riesgos estilizada con la paleta de la web y bordes gruesos negros
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "LEYENDA DE RIESGOS", ln=1)
    pdf.ln(2)
    
    # Bajo (Verde)
    pdf.set_fill_color(240, 253, 244)
    pdf.set_text_color(22, 101, 52)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Bajo", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Valores normales de funcionamiento", 1, 1, "L")
    
    # Medio (Amarillo/Ámbar)
    pdf.set_fill_color(255, 251, 235)
    pdf.set_text_color(146, 64, 14)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Medio", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Cerca del limite sugerido, requiere observacion", 1, 1, "L")
    
    # Alto (Naranja)
    pdf.set_fill_color(255, 247, 237)
    pdf.set_text_color(194, 65, 12)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Alto", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Fuera de rango seguro, requiere revision preventiva", 1, 1, "L")
    
    # Crítico (Rojo)
    pdf.set_fill_color(254, 242, 242)
    pdf.set_text_color(153, 27, 27)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(30, 8, "  Critico", 1, 0, "L", True)
    pdf.set_text_color(95, 95, 95)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(160, 8, " Estado de peligro, requiere accion correctiva inmediata", 1, 1, "L")
    pdf.ln(10)
    
    # Gráfico de barras estilizado
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "VALORES PROMEDIO DEL PERIODO", ln=1)
    pdf.ln(2)
    bar_vars = [
        "temperature",
        "pressure",
        "flow_rate",
        "vibration",
        "tank_level",
        "load",
        "energy",
        "voltage",
        "current",
    ]
    display_names = {
        "temperature": "Temp. (C)",
        "pressure": "Presion (bar)",
        "flow_rate": "Caudal (L/s)",
        "vibration": "Vibracion (mm/s)",
        "tank_level": "Tanque (%)",
        "load": "Carga (kg)",
        "energy": "Energia (kW)",
        "voltage": "Voltaje (V)",
        "current": "Corriente (A)",
    }
    labels = []
    avgs = []
    for v in bar_vars:
        if v in stats and isinstance(stats[v]["avg"], float):
            labels.append(display_names.get(v, v))
            avgs.append(stats[v]["avg"])
    if avgs:
        max_avg = max(avgs)
        x0 = 15
        y0 = pdf.get_y()
        bar_width = 16
        spacing = 4
        max_bar_height = 50
        pdf.set_font("Helvetica", "", 7)
        for i, (lab, val) in enumerate(zip(labels, avgs)):
            x = x0 + i * (bar_width + spacing)
            if x + bar_width > 200:
                break
            height = (val / max_avg) * max_bar_height if max_avg > 0 else 10
            # Usar color carbón/azul oscuro para las barras (#1E293B) y borde negro grueso
            pdf.set_fill_color(30, 41, 59)
            pdf.set_draw_color(10, 10, 10)
            pdf.rect(x, y0 + max_bar_height - height, bar_width, height, "FD")
            
            # Valor encima de la barra
            pdf.set_text_color(30, 41, 59)
            pdf.set_xy(x, y0 + max_bar_height - height - 4)
            pdf.cell(bar_width, 4, f"{val:.1f}", 0, 0, "C")
            
            # Label debajo de la barra
            pdf.set_text_color(95, 95, 95)
            pdf.set_xy(x, y0 + max_bar_height + 2)
            pdf.cell(bar_width, 4, lab, 0, 0, "C")
        pdf.set_y(y0 + max_bar_height + 12)
    pdf.ln(6)
    
    # Tabla valores actuales
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "VALORES ACTUALES DE SENSORES", ln=1)
    pdf.ln(2)
    
    # Cabecera de la tabla
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(10, 10, 10) # Cabecera oscura
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(80, 8, "  Variable", 1, 0, "L", True)
    pdf.cell(50, 8, "  Valor Actual", 1, 0, "L", True)
    pdf.cell(60, 8, "Riesgo / Estado", 1, 1, "C", True)
    
    pdf.set_font("Helvetica", "", 9)
    pdf.set_draw_color(10, 10, 10)
    for var, val in sensor_data.items():
        risk, color = classify_risk(var, val)
        if color == "green":
            fill = (240, 253, 244)
            text_c = (22, 101, 52)
        elif color == "yellow":
            fill = (255, 251, 235)
            text_c = (146, 64, 14)
        elif color == "orange":
            fill = (255, 247, 237)
            text_c = (194, 65, 12)
        elif color == "red":
            fill = (254, 242, 242)
            text_c = (153, 27, 27)
        else:
            fill = (249, 250, 251)
            text_c = (55, 65, 81)
            
        if isinstance(val, bool):
            val_str = "Sí" if val else "No"
        else:
            val_str = f"{val} {get_unit(var)}"
            
        # Dibujar fila con bordes negros
        pdf.set_text_color(26, 26, 26)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(80, 8, f"  {var.replace('_', ' ').title()}", 1, 0, "L")
        pdf.cell(50, 8, f"  {val_str}", 1, 0, "L")
        
        # Celda tipo Badge para riesgo con borde negro
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(60, 8, risk, 1, 1, "C", True)
    pdf.ln(8)
    
    # Forzar salto de página si queda poco espacio
    if pdf.get_y() > 220:
        pdf.add_page()
        
    # Estadísticas
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, f"ESTADISTICAS DE VARIABLES ({period_name.upper()})", ln=1)
    pdf.ln(2)
    
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(10, 10, 10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(10, 10, 10)
    pdf.cell(55, 7, "  Variable", 1, 0, "L", True)
    pdf.cell(32, 7, "Minimo", 1, 0, "C", True)
    pdf.cell(32, 7, "Maximo", 1, 0, "C", True)
    pdf.cell(36, 7, "Promedio", 1, 0, "C", True)
    pdf.cell(35, 7, "Lecturas", 1, 1, "C", True)
    
    pdf.set_font("Helvetica", "", 8)
    pdf.set_draw_color(10, 10, 10)
    pdf.set_text_color(26, 26, 26)
    for var in numeric_vars:
        s = stats[var]
        pdf.cell(55, 6, f"  {var.replace('_', ' ').title()}", 1)
        pdf.cell(32, 6, str(s["min"]), 1, 0, "C")
        pdf.cell(32, 6, str(s["max"]), 1, 0, "C")
        avg_val = f"{s['avg']:.2f}" if isinstance(s["avg"], float) else "N/A"
        pdf.cell(36, 6, avg_val, 1, 0, "C")
        pdf.cell(35, 6, str(s["count"]), 1, 1, "C")
    pdf.ln(8)
    
    # Recomendaciones y Alertas
    if pdf.get_y() > 210:
        pdf.add_page()
        
    # Recomendaciones
    recs = []
    if "temperature" in stats and isinstance(stats["temperature"]["avg"], float):
        if stats["temperature"]["avg"] > 85:
            recs.append("Temperatura promedio elevada. Mejorar ventilación de sala.")
    if "flow_rate" in stats and isinstance(stats["flow_rate"]["avg"], float):
        if stats["flow_rate"]["avg"] < 10:
            recs.append("Caudal promedio bajo. Revisar bomba hidráulica y filtros.")
    if "pressure" in stats and isinstance(stats["pressure"]["avg"], float):
        if stats["pressure"]["avg"] > 7:
            recs.append("Presion media alta. Verificar reguladores de presion.")
    if "tank_level" in stats and isinstance(stats["tank_level"]["avg"], float):
        if stats["tank_level"]["avg"] < 25:
            recs.append("Nivel de tanque bajo. Aumentar frecuencia de recarga.")
    if not recs:
        recs.append("Todos los parámetros promedio se encuentran estables.")
        
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "DIAGNOSTICO Y RECOMENDACIONES", ln=1)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(55, 65, 81)
    for rec in recs[:5]:
        pdf.cell(0, 6, f"- {rec}", ln=1)
    pdf.ln(8)
    
    # Alertas
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, f"ALERTAS DETECTADAS EN EL PERIODO: {len(alerts_in_period)}", ln=1)
    pdf.ln(2)
    if alerts_in_period:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(254, 242, 242)
        pdf.set_text_color(153, 27, 27)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(50, 7, "  Fecha/Hora", 1, 0, "L", True)
        pdf.cell(50, 7, "  Variable", 1, 0, "L", True)
        pdf.cell(40, 7, "Valor", 1, 0, "C", True)
        pdf.cell(50, 7, "Riesgo", 1, 1, "C", True)
        
        pdf.set_font("Helvetica", "", 8)
        pdf.set_draw_color(10, 10, 10)
        pdf.set_text_color(26, 26, 26)
        for a in alerts_in_period[:15]:
            pdf.cell(50, 6, f"  {a['timestamp']}", 1)
            pdf.cell(50, 6, f"  {a['variable']}", 1)
            pdf.cell(40, 6, str(a["value"]), 1, 0, "C")
            pdf.cell(50, 6, a["risk"], 1, 1, "C")
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(95, 95, 95)
        pdf.cell(0, 8, "No se registraron alertas críticas durante este período.", ln=1)
    pdf.ln(8)
    
    # Racionamiento de agua
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, "ESTADO GENERAL DE RACIONAMIENTO", ln=1)
    pdf.ln(2)
    
    if sensor_data["flow_rate"] < RATIONING_THRESHOLD:
        pdf.set_fill_color(254, 242, 242)
        pdf.set_text_color(153, 27, 27)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(0, 10, "  RACIONAMIENTO ACTIVO - Caudal por debajo del minimo admisible", 1, 1, "L", True)
    else:
        pdf.set_fill_color(240, 253, 244)
        pdf.set_text_color(22, 101, 52)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(0, 10, "  Racionamiento inactivo. Flujo hidraulico normal.", 1, 1, "L", True)
        
    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, str):
        pdf_output = pdf_output.encode("latin-1")
    return BytesIO(pdf_output)


# ----------------------------------------------------------------------
# Servidor Flask
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "clave-segura"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")


@app.after_request
def apply_cors(response):
    response.headers.set("Access-Control-Allow-Origin", "*")
    response.headers.set("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    response.headers.set("Access-Control-Allow-Credentials", "true")
    return response


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/status")
def api_status():
    return jsonify(build_live_payload())


@app.route("/stream/monitoreo")
def stream_monitoring():
    def event_stream():
        while True:
            eventlet.sleep(5)
            monitoring_payload = build_live_payload()
            yield f"data: {json.dumps(monitoring_payload)}\n\n"
            while pending_notifications:
                notification = pending_notifications.popleft()
                yield "event: notification\n"
                yield f"data: {json.dumps(notification)}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/notifications")
def api_notifications():
    if not DJANGO_CONNECTED:
        return jsonify({"error": "Django no está disponible"}), 500
    try:
        notifications = Notificacion.objects.select_related(
            "id_equipo_monitoreo__id_edificio"
        ).order_by("-fecha")[:50]
        payload = []
        for n in notifications:
            payload.append(
                {
                    "id": n.id_notificacion,
                    "fecha": n.fecha.isoformat() if n.fecha else None,
                    "mensaje": n.mensaje,
                    "equipo": n.id_equipo_monitoreo.nb_equipo
                    if n.id_equipo_monitoreo
                    else None,
                    "edificio": n.id_equipo_monitoreo.id_edificio.nb_edificio
                    if n.id_equipo_monitoreo and n.id_equipo_monitoreo.id_edificio
                    else None,
                }
            )
        return jsonify(payload)
    except Exception as e:
        logger.warning("Error al buscar notificaciones Django: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/get_thresholds")
def get_thresholds():
    return jsonify(thresholds)


@app.route("/update_thresholds", methods=["POST"])
def update_thresholds():
    global thresholds
    thresholds.update(request.json)
    return jsonify({"status": "ok", "thresholds": thresholds})


@app.route("/toggle_alerts", methods=["POST"])
def toggle_alerts():
    global alert_enabled
    alert_enabled = request.json.get("enabled", True)
    return jsonify({"status": "ok", "alert_enabled": alert_enabled})


@app.route("/get_alert_log")
def get_alert_log():
    return jsonify(alert_log[:100])


@app.route("/clear_history", methods=["POST"])
def clear_history():
    global history
    history.clear()
    return jsonify({"status": "ok", "message": "Historial limpiado"})


@app.route("/clear_alerts", methods=["POST"])
def clear_alerts():
    global alert_log
    alert_log = []
    if DJANGO_CONNECTED:
        try:
            equipo = EquipoMonitoreo.objects.first() if EquipoMonitoreo.objects.exists() else None
            if equipo:
                Notificacion.objects.filter(id_equipo_monitoreo=equipo).delete()
            else:
                Notificacion.objects.all().delete()
            logger.info("Notificaciones de Django eliminadas")
        except Exception as e:
            logger.warning("Error al eliminar notificaciones en Django: %s", e)
    return jsonify({"status": "ok", "message": "Alertas limpiadas"})


@app.route("/api/edificios", methods=["GET"])
def api_edificios():
    if not DJANGO_CONNECTED:
        return jsonify([{"id": 1, "nombre": "Edificio Simulado (Sin DB)"}])
    try:
        edificios = Edificio.objects.all().order_by("nb_edificio")
        return jsonify([{"id": e.id_edificio, "nombre": e.nb_edificio or f"Edificio #{e.id_edificio}"} for e in edificios])
    except Exception as e:
        logger.error(f"Error cargando edificios: {e}")
        return jsonify([{"id": 1, "nombre": "Edificio Simulado (Error)"}])


@app.route("/api/usuarios_edificio/<int:edificio_id>", methods=["GET"])
def api_usuarios_edificio(edificio_id):
    if not DJANGO_CONNECTED:
        return jsonify([])
    try:
        users = UsuarioEdificio.objects.filter(id_edificio_id=edificio_id).select_related('id_usuario__id_persona')
        payload = []
        for u in users:
            if u.id_usuario and u.id_usuario.id_persona:
                p = u.id_usuario.id_persona
                if p.email:
                    payload.append({
                        "nombre": p.name or "",
                        "apellido": p.apellido or "",
                        "email": p.email.strip()
                    })
        return jsonify(payload)
    except Exception as e:
        logger.error(f"Error cargando usuarios de edificio: {e}")
        return jsonify([])


@app.route("/api/send_test_email", methods=["POST"])
def api_send_test_email():
    data = request.json
    email = data.get("email")
    risk_level = data.get("risk_level", "Bajo")
    message = "Este es tu reporte del edificio generado por el sistema de monitoreo."
    try:
        pdf_io = generate_pdf_report("hour")
        threading.Thread(
            target=send_email_alert,
            args=(risk_level, "Reporte de Edificio - PCLogo", message, pdf_io, "reporte.pdf", [email]),
            daemon=True
        ).start()
    except Exception as e:
        logger.error(f"Error generando o enviando PDF a {email}: {e}")
        threading.Thread(
            target=send_email_alert,
            args=(risk_level, "Reporte de Edificio - PCLogo", message + f"\n\n(No se pudo adjuntar el reporte: {e})", None, "reporte.pdf", [email]),
            daemon=True
        ).start()
    return jsonify({"status": "ok", "message": f"Prueba enviada a {email}"})


@app.route("/api/send_all_subscribers", methods=["POST"])
def api_send_all_subscribers():
    data = request.json
    edificio_id = data.get("edificio_id")
    risk_level = data.get("risk_level", "Bajo")
    emails = get_building_emails(edificio_id)
    if not emails:
        return jsonify({"status": "error", "message": "No hay correos registrados para este edificio"}), 400
    
    message = "Este es el reporte del edificio enviado a todos los suscriptores."
    try:
        pdf_io = generate_pdf_report("hour")
        threading.Thread(
            target=send_email_alert,
            args=(risk_level, "Reporte de Edificio (Masivo) - PCLogo", message, pdf_io, "reporte.pdf", emails),
            daemon=True
        ).start()
    except Exception as e:
        logger.error(f"Error generando o enviando PDF masivo: {e}")
        threading.Thread(
            target=send_email_alert,
            args=(risk_level, "Reporte de Edificio (Masivo) - PCLogo", message + f"\n\n(No se pudo adjuntar el reporte: {e})", None, "reporte.pdf", emails),
            daemon=True
        ).start()
    return jsonify({"status": "ok", "message": f"Prueba enviada a {len(emails)} destinatarios"})


@app.route("/manual_update", methods=["POST"])
def manual_update():
    data = request.json
    variable = data.get("variable")
    value = data.get("value")
    if variable not in sensor_data:
        return jsonify({"status": "error", "message": "Variable no válida"}), 400
    if variable == "door_status":
        if value not in ["open", "closed"]:
            return jsonify(
                {"status": "error", "message": 'door_status debe ser "open" o "closed"'}
            ), 400
        sensor_data[variable] = value
    elif variable == "motor_stuck":
        sensor_data[variable] = bool(value)
    else:
        try:
            sensor_data[variable] = float(value)
        except ValueError:
            return jsonify(
                {"status": "error", "message": "Valor numérico inválido"}
            ), 400
    risk, _ = (
        classify_risk(variable, sensor_data[variable])
        if variable != "motor_stuck"
        else ("Crítico" if sensor_data[variable] else "Bajo")
    )
    if risk in ("Alto", "Crítico") and alert_enabled:
        action = get_professional_action(variable, risk, sensor_data[variable])
        send_alert(
            variable,
            sensor_data[variable],
            risk,
            f"Valor manual ({sensor_data[variable]}): {action}",
        )
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    sensor_type = (
        "Bomba"
        if variable
        in [
            "flow_rate",
            "pressure",
            "temperature",
            "vibration",
            "tank_level",
            "voltage",
            "current",
        ]
        else "Ascensor"
    )
    history.append(
        {
            "timestamp": timestamp,
            "type": sensor_type,
            "variable": f"{variable} (manual)",
            "value": sensor_data[variable],
            "risk": risk,
            "color": "red" if risk in ("Alto", "Crítico") else "green",
        }
    )
    if len(history) > MAX_HISTORY_SIZE:
        history.pop(0)
    stats = {}
    for var in [
        "temperature",
        "flow_rate",
        "pressure",
        "vibration",
        "tank_level",
        "load",
        "voltage",
        "current",
    ]:
        vals = [
            r["value"]
            for r in history
            if r["variable"] == var and isinstance(r["value"], (int, float))
        ]
        if vals:
            stats[var] = {
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }
    recs = generate_recommendations(sensor_data, stats)
    socketio.emit(
        "sensor_update",
        {
            "current": sensor_data,
            "history": history,
            "thresholds": thresholds,
            "alert_enabled": alert_enabled,
            "alert_log": alert_log[:50],
            "rationing": sensor_data["flow_rate"] < RATIONING_THRESHOLD,
            "door_close_attempts": door_close_attempts,
            "recommendations": recs,
            "stats": stats,
        },
    )
    return jsonify(
        {
            "status": "ok",
            "variable": variable,
            "value": sensor_data[variable],
            "risk": risk,
        }
    )


@app.route("/generate_report", methods=["POST"])
def generate_report():
    period = request.json.get("period", "hour")
    try:
        pdf_buffer = generate_pdf_report(period)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"reporte_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype="application/pdf",
        )
    except Exception as e:
        logger.error(f"Error PDF: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@socketio.on("connect")
def handle_connect():
    payload = build_live_payload()
    emit("init_data", payload)


# ----------------------------------------------------------------------
# Plantilla HTML completa (con gráficos de barras y diagnóstico)
# ----------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>INES — Panel de Monitoreo</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        /* ── Design Tokens ── */
        :root {
            --font: 'DM Sans', system-ui, sans-serif;
            --color-ink: #0a0a0a;
            --color-ink-soft: #1a1a1a;
            --color-surface: #ffffff;
            --color-bg: #f5f5f5;
            --color-border: #e0e0e0;
            --color-border-strong: #b0b0b0;
            --color-text-primary: #1a1a1a;
            --color-text-secondary: #5f5f5f;
            --color-text-placeholder: #a0a0a0;

            /* Estados funcionales (solo para semáforos) */
            --state-ok: #166534;
            --state-ok-bg: #f0fdf4;
            --state-ok-border: #bbf7d0;
            --state-warn: #92400e;
            --state-warn-bg: #fffbeb;
            --state-warn-border: #fde68a;
            --state-critical: #991b1b;
            --state-critical-bg: #fef2f2;
            --state-critical-border: #fecaca;
            --state-inactive: #374151;
            --state-inactive-bg: #f9fafb;
            --state-inactive-border: #e5e7eb;

            --radius: 0px;
            --sp-1: 8px; --sp-2: 16px; --sp-3: 24px; --sp-4: 32px; --sp-5: 40px;
            --text-xs: 0.75rem; --text-sm: 0.875rem; --text-base: 1rem;
            --text-lg: 1.125rem; --text-xl: 1.25rem; --text-2xl: 1.5rem;
            --weight-normal: 400; --weight-medium: 500; --weight-bold: 700;
            --tracking-wide: 0.06em; --tracking-tight: -0.02em;
            --leading-tight: 1.2; --leading-normal: 1.5;
            --transition-base: 0.15s ease;
            --transition-fast: 0.1s ease;
        }

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: var(--font);
            background: var(--color-bg);
            color: var(--color-text-primary);
            font-size: var(--text-base);
            line-height: var(--leading-normal);
            font-weight: var(--weight-normal);
            -webkit-font-smoothing: antialiased;
        }

        /* ── Layout ── */
        .page-wrapper { max-width: 1400px; margin: 0 auto; padding: var(--sp-4); }

        .page-header {
            border-bottom: 2px solid var(--color-ink);
            padding-bottom: var(--sp-2);
            margin-bottom: var(--sp-4);
        }

        .page-title {
            font-size: var(--text-2xl);
            font-weight: var(--weight-bold);
            letter-spacing: var(--tracking-tight);
            color: var(--color-ink);
            line-height: var(--leading-tight);
        }

        .page-subtitle {
            font-size: var(--text-sm);
            color: var(--color-text-secondary);
            margin-top: 4px;
        }

        /* ── Paneles / Tarjetas ── */
        .panel {
            background: var(--color-surface);
            border: 2px solid var(--color-ink);
            box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15);
            padding: var(--sp-3);
            margin-bottom: var(--sp-3);
            border-radius: 0px;
        }

        .panel-title {
            font-size: var(--text-base);
            font-weight: var(--weight-bold);
            letter-spacing: var(--tracking-tight);
            color: var(--color-ink);
            margin-bottom: var(--sp-2);
            padding-bottom: var(--sp-1);
            border-bottom: 2px solid var(--color-ink);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .panel-title i { color: var(--color-ink); font-size: 0.9rem; }

        /* ── Grids ── */
        .grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--sp-2); }
        .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-2); }
        .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2px; background: var(--color-ink); border: 2px solid var(--color-ink); box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15); border-radius: 0px; }
        .grid-auto { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 2px; background: var(--color-ink); border: 2px solid var(--color-ink); box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15); border-radius: 0px; }
        .grid-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--sp-2); margin-bottom: var(--sp-3); }

        .grid-4 > *, .grid-auto > * { background: var(--color-surface); }

        /* ── Fila de controles ── */
        .controls-row {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--sp-2);
            margin-bottom: var(--sp-3);
            padding: var(--sp-2) var(--sp-3);
            background: var(--color-surface);
            border: 2px solid var(--color-ink);
            box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15);
            border-radius: 0px;
        }

        .controls-row .spacer { flex: 1; }

        /* ── Botones ── */
        .btn {
            font-family: var(--font);
            font-size: var(--text-sm);
            font-weight: var(--weight-bold);
            cursor: pointer;
            border: 2px solid var(--color-ink);
            background: var(--color-ink);
            color: var(--color-surface);
            padding: 8px var(--sp-2);
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all var(--transition-fast);
            border-radius: 0px;
            box-shadow: 3px 3px 0px var(--color-ink);
        }

        .btn:hover {
            background: var(--color-surface);
            color: var(--color-ink);
            transform: translate(-1px, -1px);
            box-shadow: 4px 4px 0px rgba(10, 10, 10, 0.25);
            opacity: 1;
        }
        .btn:disabled { opacity: 0.35; cursor: not-allowed; }

        .btn-ghost {
            background: var(--color-surface);
            color: var(--color-ink);
            border: 2px solid var(--color-ink);
            box-shadow: 3px 3px 0px var(--color-ink);
        }

        .btn-danger {
            background: var(--state-critical);
            border-color: var(--state-critical);
            box-shadow: 3px 3px 0px var(--state-critical);
        }

        .btn-danger:hover {
            background: var(--color-surface);
            color: var(--state-critical);
            border-color: var(--state-critical);
            box-shadow: 4px 4px 0px rgba(153, 27, 27, 0.25);
        }

        .btn-ok {
            background: var(--state-ok);
            border-color: var(--state-ok);
            box-shadow: 3px 3px 0px var(--state-ok);
        }

        .btn-ok:hover {
            background: var(--color-surface);
            color: var(--state-ok);
            border-color: var(--state-ok);
            box-shadow: 4px 4px 0px rgba(22, 101, 52, 0.25);
        }

        /* ── Inputs y Selects ── */
        .form-group { display: flex; flex-direction: column; gap: 4px; }

        .form-label {
            font-size: var(--text-xs);
            font-weight: var(--weight-bold);
            text-transform: uppercase;
            letter-spacing: var(--tracking-wide);
            color: var(--color-ink);
        }

        input[type="text"],
        input[type="number"],
        input[type="email"],
        select {
            font-family: var(--font);
            font-size: var(--text-base);
            color: var(--color-text-primary);
            background: var(--color-bg);
            border: 2px solid var(--color-ink);
            padding: 9px var(--sp-1);
            width: 100%;
            outline: none;
            border-radius: 0px;
            transition: all var(--transition-base);
        }

        input:focus, select:focus {
            border-color: var(--color-ink);
            background: var(--color-surface);
            box-shadow: 4px 4px 0px rgba(10, 10, 10, 0.1);
        }

        /* ── Sensor Cards ── */
        .sensor-card {
            padding: var(--sp-3);
            background: var(--color-surface);
            border: 2px solid var(--color-ink);
            border-left: 6px solid var(--color-ink);
            box-shadow: 4px 4px 0px rgba(10, 10, 10, 0.15);
            border-radius: 0px;
        }

        .sensor-card.risk-low   { border-left-color: var(--state-ok); }
        .sensor-card.risk-med   { border-left-color: var(--state-warn); }
        .sensor-card.risk-high  { border-left-color: #c2410c; }
        .sensor-card.risk-crit  { border-left-color: var(--state-critical); }

        .sensor-card-name {
            font-size: var(--text-xs);
            font-weight: var(--weight-bold);
            text-transform: uppercase;
            letter-spacing: var(--tracking-wide);
            color: var(--color-ink);
            margin-bottom: 4px;
        }

        .sensor-card-value {
            font-size: var(--text-xl);
            font-weight: var(--weight-bold);
            color: var(--color-ink);
            line-height: var(--leading-tight);
        }

        .sensor-card-footer {
            margin-top: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* ── Risk Badges ── */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            font-size: var(--text-xs);
            font-weight: var(--weight-bold);
            text-transform: uppercase;
            letter-spacing: 0.03em;
            border: 2px solid var(--color-ink);
            border-radius: 0px;
        }

        .badge-low    { background: var(--state-ok-bg);       color: var(--state-ok); }
        .badge-med    { background: var(--state-warn-bg);     color: var(--state-warn); }
        .badge-high   { background: #fff7ed;                  color: #c2410c; }
        .badge-crit   { background: var(--state-critical-bg); color: var(--state-critical); }
        .badge-info   { background: var(--state-inactive-bg); color: var(--state-inactive); }

        /* ── Estado Sistema ── */
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: var(--sp-2);
            background: transparent;
            border: none;
            box-shadow: none;
            margin-bottom: var(--sp-3);
            border-radius: 0px;
        }

        .status-cell {
            background: var(--color-surface);
            padding: var(--sp-2) var(--sp-3);
            border: 2px solid var(--color-ink);
            box-shadow: 4px 4px 0px rgba(10, 10, 10, 0.15);
        }

        .status-cell-label {
            font-size: var(--text-xs);
            text-transform: uppercase;
            letter-spacing: var(--tracking-wide);
            color: var(--color-ink);
            font-weight: var(--weight-bold);
            margin-bottom: 2px;
        }

        .status-cell-value {
            font-size: var(--text-lg);
            font-weight: var(--weight-bold);
            color: var(--color-ink);
        }

        /* ── Secciones de Sensores ── */
        .sensor-section {
            margin-bottom: var(--sp-3);
        }

        .sensor-section-title {
            font-size: var(--text-sm);
            font-weight: var(--weight-bold);
            text-transform: uppercase;
            letter-spacing: var(--tracking-wide);
            color: var(--color-ink);
            margin-bottom: var(--sp-1);
            padding-bottom: var(--sp-1);
            border-bottom: 2px solid var(--color-ink);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .sensor-cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: var(--sp-3);
            background: transparent;
            border: none;
            box-shadow: none;
            border-radius: 0px;
        }

        /* ── Tabla ── */
        .table-wrapper {
            background: var(--color-surface);
            border: 2px solid var(--color-ink);
            box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15);
            overflow: hidden;
            margin-bottom: var(--sp-3);
            border-radius: 0px;
        }

        .scroll-table {
            max-height: 320px;
            overflow-y: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: var(--text-sm);
        }

        thead th {
            background: var(--color-bg);
            color: var(--color-ink);
            font-size: var(--text-xs);
            font-weight: var(--weight-bold);
            text-transform: uppercase;
            letter-spacing: var(--tracking-wide);
            padding: 8px var(--sp-2);
            text-align: left;
            border-bottom: 2px solid var(--color-ink);
            position: sticky;
            top: 0;
        }

        tbody td {
            padding: 10px var(--sp-2);
            border-top: 1px solid var(--color-ink);
            color: var(--color-text-primary);
        }

        tbody tr:hover td { background: var(--color-bg); }

        .row-crit td { background: var(--state-critical-bg); }
        .row-high td { background: var(--state-warn-bg); }

        /* ── Chart Container ── */
        .chart-panel {
            background: var(--color-surface);
            border: 2px solid var(--color-ink);
            box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15);
            padding: var(--sp-2);
            border-radius: 0px;
        }

        .chart-panel-title {
            font-size: var(--text-xs);
            font-weight: var(--weight-bold);
            text-transform: uppercase;
            letter-spacing: var(--tracking-wide);
            color: var(--color-ink);
            margin-bottom: var(--sp-1);
            padding-bottom: 6px;
            border-bottom: 2px solid var(--color-ink);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        canvas { max-height: 220px; width: 100%; }

        /* ── Alerta / Aviso ── */
        .sys-alert {
            padding: var(--sp-1) var(--sp-2);
            margin-bottom: var(--sp-2);
            font-size: var(--text-sm);
            font-weight: var(--weight-bold);
            display: flex;
            align-items: center;
            gap: var(--sp-1);
            border: 2px solid var(--color-ink);
            border-radius: 0px;
            box-shadow: 4px 4px 0px rgba(10, 10, 10, 0.1);
        }

        .sys-alert-warn {
            background: var(--state-warn-bg);
            color: var(--state-warn);
            border-color: var(--state-warn);
        }

        .sys-alert-crit {
            background: var(--state-critical-bg);
            color: var(--state-critical);
            border-color: var(--state-critical);
        }

        /* ── Racionamiento ── */
        #rationingIndicator {
            display: none;
            background: var(--state-critical);
            color: #fff;
            padding: 4px var(--sp-1);
            font-size: var(--text-xs);
            font-weight: var(--weight-bold);
            text-transform: uppercase;
            letter-spacing: var(--tracking-wide);
            border: 2px solid var(--color-ink);
        }

        #rationingIndicator.visible { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 44px; padding: 0 var(--sp-2); }

        /* ── Suscriptores ── */
        .subs-table { font-size: var(--text-sm); width: 100%; border-collapse: collapse; }
        .subs-table th { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: var(--tracking-wide); color: var(--color-ink); font-weight: var(--weight-bold); padding: 6px var(--sp-1); border-bottom: 2px solid var(--color-ink); text-align: left; }
        .subs-table td { padding: 8px var(--sp-1); border-top: 1px solid var(--color-ink); }
        .subs-table button {
            background: var(--color-surface) !important;
            border: 2px solid var(--color-ink) !important;
            color: var(--color-ink) !important;
            border-radius: 0px !important;
            font-family: var(--font);
            font-size: var(--text-xs);
            font-weight: var(--weight-bold);
            padding: 4px 8px !important;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            transition: all var(--transition-fast);
            letter-spacing: 0.01em;
            box-shadow: 2px 2px 0px var(--color-ink);
        }
        .subs-table button:hover {
            background: var(--color-ink) !important;
            color: var(--color-surface) !important;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px rgba(10, 10, 10, 0.25);
            opacity: 1 !important;
        }
        .btn-test-sub { color: var(--color-ink); margin-right: var(--sp-1); }
        .btn-rm-sub   { color: var(--state-critical); }

        .subs-container { max-height: 220px; overflow-y: auto; border: 2px solid var(--color-ink); border-radius: 0px; }

        /* ── Responsive ── */
        @media (max-width: 1024px) {
            .grid-2, .grid-3 { grid-template-columns: 1fr; }
            .grid-charts { grid-template-columns: 1fr; }
        }

        @media (max-width: 640px) {
            .page-wrapper { padding: var(--sp-2); }
            .controls-row { flex-direction: column; align-items: flex-start; }
        }

        /* ── Modal Custom ── */
        .custom-modal-backdrop {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(10, 10, 10, 0.4);
            backdrop-filter: blur(4px);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 99999;
            opacity: 0;
            transition: opacity 150ms ease;
        }
        .custom-modal-backdrop.active {
            opacity: 1;
        }
        .custom-modal-container {
            background: var(--color-surface);
            border: 2px solid var(--color-ink);
            padding: var(--sp-3);
            width: 90%;
            max-width: 440px;
            box-shadow: 8px 8px 0px rgba(10, 10, 10, 0.15);
            transform: scale(0.92);
            transition: transform 150ms ease;
            box-sizing: border-box;
            border-radius: 0px !important;
        }
        .custom-modal-backdrop.active .custom-modal-container {
            transform: scale(1);
        }
    </style>
</head>
<body>
    <div class="page-wrapper">

        <!-- Encabezado -->
        <header class="page-header">
            <h1 class="page-title"><i class="fa-solid fa-chart-line"></i> INES — Panel de Monitoreo</h1>
            <p class="page-subtitle">Sensores de bomba, ascensor, eléctricos y motor · Actualización en vivo</p>
        </header>

        <!-- Barra de controles -->
        <div class="controls-row" style="display:flex; align-items:center; gap:var(--sp-2);">
            <button id="toggleAlertsBtn" class="btn" style="height: 44px; display:inline-flex; align-items:center;">
                <i class="fas fa-bell"></i> Desactivar Alertas
            </button>
            <button id="clearHistoryBtn" class="btn btn-ghost" style="height: 44px; display:inline-flex; align-items:center;">
                <i class="fas fa-trash-alt"></i> Limpiar Historial
            </button>
            <button id="clearAlertsBtn" class="btn btn-ghost" style="height: 44px; display:inline-flex; align-items:center;">
                <i class="fas fa-bell-slash"></i> Limpiar Alertas
            </button>
            <div id="rationingIndicator"><i class="fas fa-droplet-slash"></i> Racionamiento activo</div>
            <div class="spacer"></div>
            <select id="reportPeriodSelect" style="width:auto; height: 44px; display:inline-flex; align-items:center;">
                <option value="minute">Último minuto</option>
                <option value="ten_minutes">Últimos 10 min</option>
                <option value="hour" selected>Última hora</option>
                <option value="day">Último día</option>
                <option value="week">Última semana</option>
                <option value="month">Último mes</option>
            </select>
            <button id="generateReportBtn" class="btn btn-ok" style="height: 44px; display:inline-flex; align-items:center;">
                <i class="fas fa-file-pdf"></i> Generar PDF
            </button>
        </div>

        <!-- Aviso de credenciales -->
        <div id="credsWarning" class="sys-alert sys-alert-warn" style="display:none;">
            <i class="fas fa-triangle-exclamation"></i>
            <span id="credsMsg"></span>
        </div>

        <!-- Estado del sistema -->
        <div class="status-grid" id="statusGrid">
            <div class="status-cell">
                <div class="status-cell-label">Protección</div>
                <div class="status-cell-value" id="protectionStatus">INACTIVA</div>
            </div>
            <div class="status-cell">
                <div class="status-cell-label">Bomba</div>
                <div class="status-cell-value" id="pumpStatus">ENCENDIDA</div>
            </div>
            <div class="status-cell">
                <div class="status-cell-label">Ascensor</div>
                <div class="status-cell-value" id="elevatorStatus">ENCENDIDO</div>
            </div>
            <div class="status-cell">
                <div class="status-cell-label">Última actualización</div>
                <div class="status-cell-value" id="lastUpdate">--:--:--</div>
            </div>
        </div>

        <!-- Stats + Recomendaciones -->
        <div class="grid-2" style="margin-bottom: var(--sp-3);">
            <div class="panel">
                <h2 class="panel-title"><i class="fa-solid fa-chart-bar"></i> Estadísticas recientes</h2>
                <div id="statsPanel" style="font-size:var(--text-sm); color:var(--color-text-secondary);">Cargando...</div>
            </div>
            <div class="panel">
                <h2 class="panel-title"><i class="fa-solid fa-lightbulb"></i> Recomendaciones</h2>
                <div id="doorAttemptsInfo" style="font-size:var(--text-xs); color:var(--color-text-secondary); margin-bottom:8px;"></div>
                <div id="recommendationsPanel" style="font-size:var(--text-sm);">Cargando...</div>
            </div>
        </div>

        <!-- Suscriptores -->
        <div class="panel">
            <h2 class="panel-title"><i class="fa-solid fa-envelope"></i> Envío de Alertas por Correo</h2>
            <div style="display: flex; flex-wrap: wrap; gap: var(--sp-2); align-items: flex-end; margin-bottom: var(--sp-2);">
                <div class="form-group" style="flex: 1; min-width: 200px;">
                    <label class="form-label">Edificio (edf)</label>
                    <select id="subBuildingSelect" style="height: 44px;">
                        <option value="">Cargando edificios...</option>
                    </select>
                </div>
                <div class="form-group" style="width: 150px;">
                    <label class="form-label">Nivel de riesgo prueba</label>
                    <select id="subRiskLevel" style="height: 44px;">
                        <option value="Bajo">Bajo</option>
                        <option value="Medio">Medio</option>
                        <option value="Alto">Alto</option>
                        <option value="Crítico">Crítico</option>
                    </select>
                </div>
                <div>
                    <button id="sendAllSubscribersBtn" class="btn btn-ok" style="height: 44px; display: inline-flex; align-items: center; justify-content: center;">
                        <i class="fas fa-paper-plane"></i> Enviar a todos
                    </button>
                </div>
            </div>
            <div class="subs-container">
                <div id="subscribersList" style="padding: var(--sp-1); font-size:var(--text-sm); color:var(--color-text-secondary);">Cargando usuarios...</div>
            </div>
            <p style="margin-top:8px; font-size:var(--text-xs); color:var(--color-text-placeholder);">* El botón "Enviar a todos" envía el reporte en PDF por correo a todas las personas del edificio seleccionado. El botón "Enviar prueba" en la lista envía de manera individual.</p>
        </div>

        <!-- Control manual -->
        <div class="panel">
            <h2 class="panel-title"><i class="fa-solid fa-sliders"></i> Control manual de sensores</h2>
            <div style="display:flex; flex-wrap:wrap; gap:var(--sp-2); align-items:flex-end;">
                <div class="form-group" style="flex:1; min-width:180px;">
                    <label class="form-label">Sensor</label>
                    <select id="manualSensorSelect"></select>
                </div>
                <div class="form-group" style="flex:1; min-width:180px; position:relative;">
                    <label class="form-label">Valor</label>
                    <input type="text" id="manualValueInput" placeholder="Ingrese valor">
                </div>
                <div>
                    <button id="sendManualBtn" class="btn" style="height: 44px; display: inline-flex; align-items: center; justify-content: center;">
                        <i class="fas fa-paper-plane"></i> Enviar
                    </button>
                </div>
            </div>
            <div style="font-size:var(--text-xs); margin-top:8px; height:18px;" id="manualRiskPreview"></div>
            <div id="manualMessage" style="margin-top:8px; font-size:var(--text-sm);"></div>
            <div id="sensorTypeIndicator" style="margin-top:6px; font-size:var(--text-sm); font-weight:var(--weight-medium); color:var(--color-text-secondary);"></div>
        </div>

        <!-- Tarjetas de sensores: Bomba -->
        <div class="sensor-section">
            <div class="sensor-section-title">
                <i class="fa-solid fa-oil-can"></i> Sensores de Bomba y Eléctricos
            </div>
            <div class="sensor-cards-grid" id="bombaCards"></div>
        </div>

        <!-- Tarjetas de sensores: Ascensor -->
        <div class="sensor-section">
            <div class="sensor-section-title">
                <i class="fa-solid fa-elevator"></i> Sensores de Ascensor y Motor
            </div>
            <div class="sensor-cards-grid" id="ascensorCards"></div>
        </div>

        <!-- Gráficos -->
        <h2 style="font-size:var(--text-base); font-weight:var(--weight-medium); text-transform:uppercase; letter-spacing:var(--tracking-wide); color:var(--color-text-secondary); margin-bottom:var(--sp-1);">
            <i class="fa-solid fa-chart-bar"></i> Lecturas en tiempo real
        </h2>
        <div class="grid-charts">
            <div class="chart-panel">
                <div class="chart-panel-title"><i class="fa-solid fa-oil-can"></i> Variables de Bomba / Eléctricas</div>
                <canvas id="chart1"></canvas>
            </div>
            <div class="chart-panel">
                <div class="chart-panel-title"><i class="fa-solid fa-elevator"></i> Variables de Ascensor / Motor</div>
                <canvas id="chart2"></canvas>
            </div>
        </div>

        <!-- Historial -->
        <h2 style="font-size:var(--text-base); font-weight:var(--weight-medium); text-transform:uppercase; letter-spacing:var(--tracking-wide); color:var(--color-text-secondary); margin-bottom:var(--sp-1); margin-top:var(--sp-3);">
            <i class="fa-solid fa-list-ul"></i> Historial completo
        </h2>
        <div class="table-wrapper">
            <div class="scroll-table" style="max-height: 500px;">
                <table>
                    <thead><tr><th>Fecha y hora</th><th>Tipo</th><th>Variable</th><th>Valor</th><th>Riesgo</th></tr></thead>
                    <tbody id="historyBody"><tr><td colspan="5" style="text-align:center; padding:var(--sp-3); color:var(--color-text-secondary);">Cargando...</td></tr></tbody>
                </table>
            </div>
        </div>

        <!-- Alertas -->
        <h2 style="font-size:var(--text-base); font-weight:var(--weight-medium); text-transform:uppercase; letter-spacing:var(--tracking-wide); color:var(--color-text-secondary); margin-bottom:var(--sp-1);">
            <i class="fa-solid fa-bell"></i> Alertas recientes
        </h2>
        <div class="table-wrapper">
            <div class="scroll-table" style="max-height: 500px;">
                <table>
                    <thead><tr><th>Fecha y hora</th><th>Variable</th><th>Valor</th><th>Riesgo</th><th>Mensaje</th></tr></thead>
                    <tbody id="alertTableBody"><tr><td colspan="5" style="text-align:center; padding:var(--sp-3); color:var(--color-text-secondary);">No hay alertas</td></tr></tbody>
                </table>
            </div>
        </div>

        <!-- Umbrales -->
        <h2 style="font-size:var(--text-base); font-weight:var(--weight-medium); text-transform:uppercase; letter-spacing:var(--tracking-wide); color:var(--color-text-secondary); margin-bottom:var(--sp-1);">
            <i class="fa-solid fa-gears"></i> Umbrales de riesgo
        </h2>
        <div class="panel">
            <div id="thresholdsPanel" class="grid-2"></div>
            <div style="margin-top:var(--sp-2); display:flex; align-items:center; gap:var(--sp-2);">
                <button id="saveThresholdsBtn" class="btn btn-ok"><i class="fas fa-check"></i> Guardar Umbrales</button>
                <span id="saveMessage" style="font-size:var(--text-sm); color:var(--state-ok);"></span>
            </div>
        </div>

    </div><!-- /page-wrapper -->

    <script>
        let socket = io();
        let chart1, chart2, chart3, chart4;
        let currentThresholds = {};
        let subscribers = {};

        // ── Helper de Modales Personalizados ──
        function showCustomModal({ title, message, type = 'info', showCancel = false }) {
            return new Promise((resolve) => {
                const backdrop = document.createElement('div');
                backdrop.className = 'custom-modal-backdrop';

                const container = document.createElement('div');
                container.className = 'custom-modal-container';

                let iconHtml = '';
                if (type === 'success') {
                    iconHtml = '<i class="fa-solid fa-circle-check" style="color: var(--state-ok); font-size: var(--text-xl);"></i>';
                } else if (type === 'error') {
                    iconHtml = '<i class="fa-solid fa-circle-xmark" style="color: var(--state-critical); font-size: var(--text-xl);"></i>';
                } else if (type === 'warn' || type === 'confirm') {
                    iconHtml = '<i class="fa-solid fa-triangle-exclamation" style="color: var(--state-warn); font-size: var(--text-xl);"></i>';
                } else {
                    iconHtml = '<i class="fa-solid fa-circle-info" style="color: var(--color-ink); font-size: var(--text-xl);"></i>';
                }

                container.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: var(--sp-2);">
                        ${iconHtml}
                        <span style="font-size: var(--text-lg); font-weight: var(--weight-bold); color: var(--color-ink); text-transform: uppercase; letter-spacing: var(--tracking-wide);">${title}</span>
                    </div>
                    <div style="font-size: var(--text-sm); color: var(--color-text-secondary); line-height: var(--leading-normal); margin-bottom: var(--sp-3); word-break: break-word;">
                        ${message}
                    </div>
                    <div style="display: flex; justify-content: flex-end; gap: var(--sp-2);">
                        ${showCancel ? `<button id="customModalCancelBtn" class="btn btn-ghost" style="border: 1px solid var(--color-ink); padding: 8px var(--sp-2); cursor: pointer;">Cancelar</button>` : ''}
                        <button id="customModalConfirmBtn" class="btn btn-ok" style="background: var(--color-ink); color: var(--color-surface); border: 1px solid var(--color-ink); padding: 8px var(--sp-2); cursor: pointer;">Aceptar</button>
                    </div>
                `;

                backdrop.appendChild(container);
                document.body.appendChild(backdrop);

                // Forzar reflujo y activar clase de animación
                setTimeout(() => {
                    backdrop.classList.add('active');
                }, 10);

                const cleanUp = (value) => {
                    backdrop.classList.remove('active');
                    setTimeout(() => {
                        backdrop.remove();
                        resolve(value);
                    }, 150);
                };

                container.querySelector('#customModalConfirmBtn').addEventListener('click', () => cleanUp(true));
                if (showCancel) {
                    container.querySelector('#customModalCancelBtn').addEventListener('click', () => cleanUp(false));
                }
            });
        }

        window.showAlert = function(message, type = 'info') {
            let title = 'Notificación';
            if (type === 'error') title = 'Error';
            else if (type === 'success') title = 'Éxito';
            else if (type === 'warn') title = 'Advertencia';
            return showCustomModal({ title, message, type, showCancel: false });
        };

        window.showConfirm = function(message) {
            return showCustomModal({ title: 'Confirmar', message, type: 'confirm', showCancel: true });
        };
        const NO_RISK_VARS = ['position','door_status','motor_stuck'];
        const BOMBA_VARS = ['flow_rate','pressure','temperature','vibration','tank_level','voltage','current'];
        const ASCENSOR_VARS = ['position','speed','load','trip_count','door_status','energy','motor_stuck'];

        function getVariableName(variable) {
            const names = {
                flow_rate: 'Caudal',
                pressure: 'Presión',
                temperature: 'Temperatura',
                vibration: 'Vibración',
                tank_level: 'Nivel de tanque',
                voltage: 'Voltaje',
                current: 'Corriente',
                position: 'Posición',
                speed: 'Velocidad',
                load: 'Carga',
                trip_count: 'Viajes',
                door_status: 'Estado de puerta',
                energy: 'Energía',
                motor_stuck: 'Motor pegado'
            };
            return names[variable] || variable.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        }

        function getUnit(v){ return {flow_rate:'L/s',pressure:'bar',temperature:'°C',vibration:'mm/s',tank_level:'%',position:'piso',speed:'m/s',load:'kg',trip_count:'viajes',door_status:'',energy:'kW',voltage:'V',current:'A'}[v]||''; }

        function getRiskClass(varName, value){
            if(NO_RISK_VARS.includes(varName)){
                let crit = (varName==='motor_stuck' && value);
                return { card:'risk-'+(crit?'crit':'low'), badge:'badge-'+(crit?'crit':'low'), label:crit?'Crítico':'Bajo' };
            }
            let cfg = currentThresholds[varName];
            if(!cfg) return { card:'', badge:'badge-info', label:'Desconocido' };
            let risk='Bajo', cls='low';
            if(cfg.direction==='range'){
                if(!(value>=cfg.low && value<=cfg.high)){ risk='Alto'; cls='high'; }
            } else {
                let d=cfg.direction, low=cfg.low, med=cfg.medium, high=cfg.high;
                if(d==='higher'){
                    if(value>high){risk='Crítico';cls='crit';}
                    else if(value>med){risk='Alto';cls='high';}
                    else if(value>low){risk='Medio';cls='med';}
                } else {
                    if(value<high){risk='Crítico';cls='crit';}
                    else if(value<med){risk='Alto';cls='high';}
                    else if(value<low){risk='Medio';cls='med';}
                }
            }
            return { card:'risk-'+cls, badge:'badge-'+cls, label:risk };
        }

        function updateCards(data){
            let b=document.getElementById('bombaCards'), a=document.getElementById('ascensorCards');
            b.innerHTML=''; a.innerHTML='';
            for(let [k,v] of Object.entries(data)){
                let ri = getRiskClass(k,v);
                let dn = getVariableName(k).toUpperCase();
                let valStr = typeof v === 'boolean' ? (v?'Sí':'No') : 
                             (k === 'door_status' ? (v === 'open' ? 'Abierta' : (v === 'closed' ? 'Cerrada' : v)) :
                             `${v} ${getUnit(k)}`);
                let card = document.createElement('div');
                card.className = `sensor-card ${ri.card}`;
                card.innerHTML = `
                    <div class="sensor-card-name">${dn}</div>
                    <div class="sensor-card-value">${valStr}</div>
                    <div class="sensor-card-footer">
                        <span class="badge ${ri.badge}">${ri.label}</span>
                    </div>`;
                if(BOMBA_VARS.includes(k)) b.appendChild(card);
                else if(ASCENSOR_VARS.includes(k)) a.appendChild(card);
            }
        }

        function updateHistoryTable(hist){
            let tbody=document.getElementById('historyBody'); tbody.innerHTML='';
            if(!hist||hist.length===0){ tbody.innerHTML='<tr><td colspan="5" style="text-align:center;padding:var(--sp-3);color:var(--color-text-secondary);">No hay registros</td></tr>'; return; }
            let lastRecords = hist.slice(-30);
            for(let i=lastRecords.length-1;i>=0;i--){
                let r=lastRecords[i];
                let cls = r.risk==='Crítico'?'row-crit':r.risk==='Alto'?'row-high':'';
                let badgeCls = {Bajo:'badge-low',Medio:'badge-med',Alto:'badge-high',Crítico:'badge-crit'}[r.risk]||'badge-info';
                let tr=document.createElement('tr'); tr.className=cls;
                let varName = r.variable.includes(' (manual)') ? getVariableName(r.variable.replace(' (manual)', '')) + ' (manual)' : getVariableName(r.variable);
                let valDisplay = r.variable.includes('door_status') ? (r.value === 'open' ? 'Abierta' : (r.value === 'closed' ? 'Cerrada' : r.value)) : r.value;
                tr.innerHTML=`<td>${r.timestamp}</td><td>${r.type}</td><td>${varName}</td><td>${valDisplay}</td><td><span class="badge ${badgeCls}">${r.risk}</span></td>`;
                tbody.appendChild(tr);
            }
        }

        function updateAlertTable(alerts){
            let tbody=document.getElementById('alertTableBody'); tbody.innerHTML='';
            if(!alerts||alerts.length===0){ tbody.innerHTML='<tr><td colspan="5" style="text-align:center;padding:var(--sp-3);color:var(--color-text-secondary);">No hay alertas</td></tr>'; return; }
            for(let a of alerts){
                let cls = a.risk==='Crítico'?'row-crit':a.risk==='Alto'?'row-high':'';
                let badgeCls = {Bajo:'badge-low',Medio:'badge-med',Alto:'badge-high',Crítico:'badge-crit'}[a.risk]||'badge-info';
                let tr=document.createElement('tr'); tr.className=cls;
                let varName = getVariableName(a.variable);
                let valDisplay = a.variable.includes('door_status') ? (a.value === 'open' ? 'Abierta' : (a.value === 'closed' ? 'Cerrada' : a.value)) : a.value;
                tr.innerHTML=`<td>${a.timestamp}</td><td>${varName}</td><td>${valDisplay}</td><td><span class="badge ${badgeCls}">${a.risk}</span></td><td>${a.message}</td>`;
                tbody.appendChild(tr);
            }
        }

        function initCharts(){
            const chartDefaults = {
                responsive:true,
                plugins:{ 
                    legend:{ display: false },
                    tooltip:{ callbacks:{ label: ctx => `${ctx.label}: ${ctx.raw}` } } 
                },
                scales:{ 
                    x:{ ticks:{ font:{ family:"'DM Sans', system-ui", size:10 } } }, 
                    y:{ beginAtZero: true, ticks:{ font:{ family:"'DM Sans', system-ui", size:10 } } } 
                }
            };
            chart1 = new Chart(document.getElementById('chart1').getContext('2d'),{ 
                type:'bar', 
                data:{ 
                    labels:['Caudal (L/s)', 'Presión (bar)', 'Temp (°C)', 'Vibración (mm/s)', 'Tanque (%)', 'Voltaje (V)', 'Corriente (A)'], 
                    datasets:[{
                        backgroundColor: '#0a0a0a',
                        borderColor: '#0a0a0a',
                        borderWidth: 1,
                        data: [0, 0, 0, 0, 0, 0, 0]
                    }]
                }, 
                options: chartDefaults 
            });
            chart2 = new Chart(document.getElementById('chart2').getContext('2d'),{ 
                type:'bar', 
                data:{ 
                    labels:['Velocidad (m/s)', 'Carga (kg)', 'Energía (kW)'], 
                    datasets:[{
                        backgroundColor: '#0a0a0a',
                        borderColor: '#0a0a0a',
                        borderWidth: 1,
                        data: [0, 0, 0]
                    }]
                }, 
                options: chartDefaults 
            });
        }

        function updateCharts(hist){
            if(!hist||hist.length===0) return;
            let getLatest = (v) => {
                let r = hist.filter(item => item.variable === v).pop();
                return r ? r.value : 0;
            };
            chart1.data.datasets[0].data = [
                getLatest('flow_rate'),
                getLatest('pressure'),
                getLatest('temperature'),
                getLatest('vibration'),
                getLatest('tank_level'),
                getLatest('voltage'),
                getLatest('current')
            ];
            chart1.update();
            
            chart2.data.datasets[0].data = [
                getLatest('speed'),
                getLatest('load'),
                getLatest('energy')
            ];
            chart2.update();
        }

        function updateStatsAndRecs(stats, recs, attempts){
            let statsDiv=document.getElementById('statsPanel');
            if(stats && Object.keys(stats).length){
                let rows = Object.entries(stats).map(([k,v])=>
                    `<tr><td style="padding:4px 8px; font-weight:var(--weight-medium);">${getVariableName(k).toUpperCase()}</td>`+
                    `<td style="padding:4px 8px;">${v.avg.toFixed(1)}</td>`+
                    `<td style="padding:4px 8px;">${v.min}</td>`+
                    `<td style="padding:4px 8px;">${v.max}</td></tr>`).join('');
                statsDiv.innerHTML=`<table style="width:100%;border-collapse:collapse;font-size:var(--text-xs);">
                    <thead><tr>
                        <th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--color-border);">Variable</th>
                        <th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--color-border);">Prom.</th>
                        <th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--color-border);">Mín.</th>
                        <th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--color-border);">Máx.</th>
                    </tr></thead><tbody>${rows}</tbody></table>`;
            } else {
                statsDiv.innerHTML='<p style="color:var(--color-text-secondary);">No hay datos.</p>';
            }
            let recDiv=document.getElementById('recommendationsPanel');
            if(recs&&recs.length){
                recDiv.innerHTML='<ul style="padding-left:var(--sp-2); margin:0;">'+recs.map(r=>`<li style="margin-bottom:4px;">${r}</li>`).join('')+'</ul>';
            } else {
                recDiv.innerHTML='<p style="color:var(--color-text-secondary);">Sin recomendaciones activas.</p>';
            }
            let attDiv=document.getElementById('doorAttemptsInfo');
            if(typeof attempts==='number' && attempts>0){
                attDiv.innerHTML=`<span class="badge badge-high">Intentos cierre de puerta: ${attempts}</span>`;
            } else { attDiv.innerHTML=''; }
        }

        function renderThresholdsPanel(th){
            let panel=document.getElementById('thresholdsPanel'); panel.innerHTML='';
            for(let [k,cfg] of Object.entries(th)){
                if(NO_RISK_VARS.includes(k)) continue;
                let div=document.createElement('div');
                div.style.cssText='border:1px solid var(--color-border);padding:var(--sp-1);';
                if(cfg.direction==='range'){
                    div.innerHTML=`<div style="font-size:var(--text-xs);font-weight:var(--weight-medium);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:var(--color-text-secondary);margin-bottom:6px;">${getVariableName(k)} (rango)</div>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-1);">
                            <div class="form-group"><label class="form-label">Mín</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}"></div>
                            <div class="form-group"><label class="form-label">Máx</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}"></div>
                        </div><input type="hidden" data-var="${k}" data-level="direction" value="range">`;
                } else {
                    div.innerHTML=`<div style="font-size:var(--text-xs);font-weight:var(--weight-medium);text-transform:uppercase;letter-spacing:var(--tracking-wide);color:var(--color-text-secondary);margin-bottom:6px;">${getVariableName(k)}</div>
                        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--sp-1);">
                            <div class="form-group"><label class="form-label">Bajo</label><input type="number" step="any" data-var="${k}" data-level="low" value="${cfg.low}"></div>
                            <div class="form-group"><label class="form-label">Medio</label><input type="number" step="any" data-var="${k}" data-level="medium" value="${cfg.medium}"></div>
                            <div class="form-group"><label class="form-label">Alto</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}"></div>
                        </div><input type="hidden" data-var="${k}" data-level="direction" value="${cfg.direction}">`;
                }
                panel.appendChild(div);
            }
        }

        async function saveThresholds(){
            let newTh={};
            document.querySelectorAll('#thresholdsPanel input[type="number"]').forEach(inp=>{
                let v=inp.dataset.var, l=inp.dataset.level;
                if(!newTh[v]) newTh[v]={direction:document.querySelector(`#thresholdsPanel input[data-var="${v}"][data-level="direction"]`).value};
                newTh[v][l]=parseFloat(inp.value);
            });
            let resp=await fetch('/update_thresholds',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(newTh)});
            let res=await resp.json();
            if(res.status==='ok'){
                document.getElementById('saveMessage').innerText='✓ Guardados';
                setTimeout(()=>document.getElementById('saveMessage').innerText='',2000);
                currentThresholds=res.thresholds;
            }
        }

        async function toggleAlerts(){
            let btn=document.getElementById('toggleAlertsBtn');
            let isCurrentlyEnabled=btn.innerText.includes('Desactivar');
            let targetState=!isCurrentlyEnabled;
            let resp=await fetch('/toggle_alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:targetState})});
            let data=await resp.json();
            if(data.status==='ok') btn.innerHTML=data.alert_enabled?'<i class="fas fa-bell"></i> Desactivar Alertas':'<i class="fas fa-bell-slash"></i> Activar Alertas';
        }

        async function clearHistory(){
            if(await window.showConfirm('¿Limpiar historial de lecturas?')){
                let resp=await fetch('/clear_history',{method:'POST'});
                if(resp.ok) {
                    await window.showAlert('Historial limpiado.', 'success');
                    updateHistoryTable([]);
                    updateCharts([]);
                } else {
                    await window.showAlert('Error al limpiar.', 'error');
                }
            }
        }

        async function clearAlerts(){
            if(await window.showConfirm('¿Limpiar historial de alertas y notificaciones?')){
                let resp=await fetch('/clear_alerts',{method:'POST'});
                if(resp.ok) {
                    await window.showAlert('Alertas limpiadas.', 'success');
                    updateAlertTable([]);
                } else {
                    await window.showAlert('Error al limpiar alertas.', 'error');
                }
            }
        }

        function populateManualSensorSelect(){
            let sel=document.getElementById('manualSensorSelect'); sel.innerHTML='';
            [...BOMBA_VARS,...ASCENSOR_VARS].forEach(v=>{
                let opt=document.createElement('option'); opt.value=v;
                opt.textContent=(BOMBA_VARS.includes(v)?'Bomba: ':'Ascensor: ')+getVariableName(v).toUpperCase();
                sel.appendChild(opt);
            });
        }

        function updateSensorTypeIndicator(){
            let v=document.getElementById('manualSensorSelect').value;
            document.getElementById('sensorTypeIndicator').textContent=BOMBA_VARS.includes(v)?'Bomba / Eléctrico':'Ascensor / Motor';
        }

        function updateManualRiskPreview(){
            let v=document.getElementById('manualSensorSelect').value;
            let raw=document.getElementById('manualValueInput').value;
            let span=document.getElementById('manualRiskPreview');
            if(raw===''){span.innerHTML='';return;}
            let val=raw;
            if(v==='door_status'){}
            else if(v==='motor_stuck') val=(raw==='true'||raw==='1');
            else{let n=parseFloat(raw); if(isNaN(n)){span.innerHTML='<span style="color:var(--state-critical)">Valor inválido</span>';return;} val=n;}
            let ri=getRiskClass(v,val);
            span.innerHTML=`Riesgo estimado: <span class="badge ${ri.badge}">${ri.label}</span>`;
        }

        async function sendManualValue(){
            let v=document.getElementById('manualSensorSelect').value;
            let raw=document.getElementById('manualValueInput').value;
            let msgEl=document.getElementById('manualMessage');
            if(raw===''){msgEl.innerHTML='<span style="color:var(--state-critical)">Ingrese un valor</span>';return;}
            let val=raw;
            if(v==='door_status'){val=raw.toLowerCase(); if(!['open','closed'].includes(val)){msgEl.innerHTML='<span style="color:var(--state-critical)">Debe ser "open" o "closed"</span>';return;}}
            else if(v==='motor_stuck') val=(raw==='true'||raw==='1');
            else{let n=parseFloat(raw); if(isNaN(n)){msgEl.innerHTML='<span style="color:var(--state-critical)">Valor numérico inválido</span>';return;} val=n;}
            try{
                let resp=await fetch('/manual_update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({variable:v,value:val})});
                let res=await resp.json();
                if(res.status==='ok'){msgEl.innerHTML=`<span style="color:var(--state-ok)">✓ ${v} = ${res.value} (${res.risk})</span>`; setTimeout(()=>msgEl.innerHTML='',3000);}
                else{msgEl.innerHTML=`<span style="color:var(--state-critical)">Error: ${res.message}</span>`;}
            }catch(e){msgEl.innerHTML='<span style="color:var(--state-critical)">Error de conexión</span>';}
        }

        async function generateReport(){
            let period=document.getElementById('reportPeriodSelect').value;
            let btn=document.getElementById('generateReportBtn');
            btn.disabled=true; btn.innerHTML='<i class="fas fa-spinner fa-spin"></i> Generando...';
            try{
                let resp=await fetch('/generate_report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({period})});
                if(resp.ok){
                    let blob=await resp.blob();
                    let url=URL.createObjectURL(blob);
                    let a=document.createElement('a'); a.href=url;
                    a.download=`reporte_${period}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.pdf`;
                    document.body.appendChild(a); a.click(); URL.revokeObjectURL(url); a.remove();
                }else{
                    let err=await resp.text();
                    try{let e=JSON.parse(err);await window.showAlert('Error: '+e.message, 'error');}catch(e){await window.showAlert('Error: '+err, 'error');}
                }
            }catch(e){await window.showAlert('Error de conexión', 'error');}
            finally{btn.disabled=false; btn.innerHTML='<i class="fas fa-file-pdf"></i> Generar PDF';}
        }

        let activeUsers = [];

        async function loadBuildings() {
            try {
                let resp = await fetch('/api/edificios');
                let buildings = await resp.json();
                let select = document.getElementById('subBuildingSelect');
                select.innerHTML = '';
                buildings.forEach(b => {
                    let opt = document.createElement('option');
                    opt.value = b.id;
                    opt.textContent = b.nombre;
                    select.appendChild(opt);
                });
                if (buildings.length > 0) {
                    loadUsersForBuilding(buildings[0].id);
                } else {
                    document.getElementById('subscribersList').innerHTML = '<p style="padding:var(--sp-1);color:var(--color-text-secondary);font-size:var(--text-sm);">No hay edificios registrados.</p>';
                }
            } catch (e) {
                console.error("Error al cargar edificios:", e);
            }
        }

        async function loadUsersForBuilding(edificioId) {
            if (!edificioId) return;
            let container = document.getElementById('subscribersList');
            container.innerHTML = '<p style="padding:var(--sp-1);color:var(--color-text-secondary);font-size:var(--text-sm);">Cargando usuarios...</p>';
            try {
                let resp = await fetch(`/api/usuarios_edificio/${edificioId}`);
                activeUsers = await resp.json();
                updateSubscribersList();
            } catch (e) {
                console.error("Error al cargar usuarios:", e);
                container.innerHTML = '<p style="padding:var(--sp-1);color:var(--state-critical);font-size:var(--text-sm);">Error al cargar usuarios.</p>';
            }
        }

        function updateSubscribersList() {
            let container = document.getElementById('subscribersList');
            if (!activeUsers || activeUsers.length === 0) {
                container.innerHTML = '<p style="padding:var(--sp-1);color:var(--color-text-secondary);font-size:var(--text-sm);">No hay usuarios asociados a este edificio.</p>';
                return;
            }
            let rows = '';
            activeUsers.forEach(u => {
                rows += `<tr>
                    <td>${u.nombre} ${u.apellido}</td>
                    <td>${u.email}</td>
                    <td><button class="btn-test-sub test-subscriber" data-email="${u.email}">Enviar prueba</button></td>
                </tr>`;
            });
            container.innerHTML = `<table class="subs-table">
                <thead>
                    <tr>
                        <th>Nombre</th>
                        <th>Correo Electrónico</th>
                        <th>Acción</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>`;

            document.querySelectorAll('.test-subscriber').forEach(btn => {
                btn.addEventListener('click', async () => {
                    let email = btn.dataset.email;
                    let risk = document.getElementById('subRiskLevel').value;
                    btn.disabled = true;
                    btn.innerText = 'Enviando...';
                    try {
                        let resp = await fetch('/api/send_test_email', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ email: email, risk_level: risk })
                        });
                        let data = await resp.json();
                        await window.showAlert(data.message, resp.ok ? 'success' : 'error');
                    } catch (e) {
                        await window.showAlert('Error al conectar con el servidor.', 'error');
                    } finally {
                        btn.disabled = false;
                        btn.innerText = 'Enviar prueba';
                    }
                });
            });
        }

        async function sendAllSubscribers() {
            let select = document.getElementById('subBuildingSelect');
            let edificioId = select.value;
            if (!edificioId) {
                await window.showAlert('Por favor seleccione un edificio.', 'warn');
                return;
            }
            let risk = document.getElementById('subRiskLevel').value;
            let btn = document.getElementById('sendAllSubscribersBtn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
            try {
                let resp = await fetch('/api/send_all_subscribers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ edificio_id: edificioId, risk_level: risk })
                });
                let data = await resp.json();
                await window.showAlert(data.message, resp.ok ? 'success' : 'error');
            } catch (e) {
                await window.showAlert('Error al conectar con el servidor.', 'error');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-paper-plane"></i> Enviar a todos';
            }
        }

        // Eventos
        document.getElementById('subBuildingSelect').addEventListener('change', (e) => loadUsersForBuilding(e.target.value));
        document.getElementById('sendAllSubscribersBtn').addEventListener('click', sendAllSubscribers);
        document.getElementById('saveThresholdsBtn').addEventListener('click', saveThresholds);
        document.getElementById('toggleAlertsBtn').addEventListener('click', toggleAlerts);
        document.getElementById('clearHistoryBtn').addEventListener('click', clearHistory);
        document.getElementById('clearAlertsBtn').addEventListener('click', clearAlerts);
        document.getElementById('manualValueInput').addEventListener('input', updateManualRiskPreview);
        document.getElementById('manualSensorSelect').addEventListener('change', ()=>{ updateManualRiskPreview(); updateSensorTypeIndicator(); });
        document.getElementById('sendManualBtn').addEventListener('click', sendManualValue);
        document.getElementById('generateReportBtn').addEventListener('click', generateReport);

        // Socket
        socket.on('connect', ()=>console.log('[INES] Socket conectado'));
        socket.on('init_data', (data)=>{ applyPayload(data); });

        function applyPayload(data){
            if(data.thresholds) currentThresholds=data.thresholds;
            if(data.subscribers) subscribers=data.subscribers;
            if(data.thresholds) renderThresholdsPanel(data.thresholds);
            if(data.current) updateCards(data.current);
            if(data.history){ updateHistoryTable(data.history); updateCharts(data.history); }
            if(data.alert_log) updateAlertTable(data.alert_log);
            updateStatsAndRecs(data.stats, data.recommendations, data.door_close_attempts);
            document.getElementById('lastUpdate').innerText = new Date().toLocaleTimeString();
            document.getElementById('toggleAlertsBtn').innerHTML = data.alert_enabled ?
                '<i class="fas fa-bell"></i> Desactivar Alertas' :
                '<i class="fas fa-bell-slash"></i> Activar Alertas';
            let ri = document.getElementById('rationingIndicator');
            if(data.rationing) ri.classList.add('visible'); else ri.classList.remove('visible');
            document.getElementById('protectionStatus').innerText = data.protection_active ? 'ACTIVA' : 'INACTIVA';
            document.getElementById('pumpStatus').innerText = data.pump_on ? 'ENCENDIDA' : 'APAGADA';
            document.getElementById('elevatorStatus').innerText = data.elevator_on ? 'ENCENDIDO' : 'APAGADO';
        }


        socket.on('sensor_update', (data)=>{ applyPayload(data); });

        initCharts();
        populateManualSensorSelect();
        updateSensorTypeIndicator();
        loadBuildings();
    </script>
</body>
</html>
"""
# ----------------------------------------------------------------------
# Inicio del servidor
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Para diagnóstico en el frontend, pasamos información de credenciales
    socketio.start_background_task(generate_data_and_emit)
    webbrowser.open("http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
