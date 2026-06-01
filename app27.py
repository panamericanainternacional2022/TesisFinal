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
    print("⚠️ fpdf2 no instalado. Reportes PDF no disponibles. Instale: pip install fpdf2")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Integración con Django para persistir alertas en la base de datos
# ----------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
DJANGO_CONNECTED = False
try:
    import django
    django.setup()
    from django.utils import timezone
    from core.models import Notificacion, EquipoMonitoreo
    DJANGO_CONNECTED = True
    logger.info('Django integrado correctamente en app27.py')
except Exception as e:
    logger.warning('No se pudo inicializar Django desde app27.py: %s', e)

# ----------------------------------------------------------------------
# Payload y estructura de datos para streaming en vivo
# ----------------------------------------------------------------------

def titleize_name(text):
    return ' '.join(word.capitalize() for word in text.replace('_', ' ').split())


def build_live_payload():
    stats = {}
    for var in ['temperature','flow_rate','pressure','vibration','tank_level','load','voltage','current']:
        vals = [r['value'] for r in history if r['variable'] == var and isinstance(r['value'], (int, float))]
        if vals:
            stats[var] = {'avg': sum(vals) / len(vals), 'min': min(vals), 'max': max(vals)}

    sensors = []
    for var, value in sensor_data.items():
        if var == 'motor_stuck':
            risk, color = ('Crítico', 'red') if value else ('Bajo', 'green')
        else:
            risk, color = classify_risk(var, value)
        sensors.append({
            'id': var,
            'nombre': titleize_name(var),
            'riesgo': risk,
            'color': color,
        })

    recommendations = generate_recommendations(sensor_data, stats)

    return {
        'current': sensor_data,
        'sensors': sensors,
        'history': history[-100:],
        'thresholds': thresholds,
        'alert_enabled': alert_enabled,
        'alert_log': alert_log[:50],
        'stats': stats,
        'recommendations': recommendations,
        'rationing': sensor_data['flow_rate'] < RATIONING_THRESHOLD,
        'door_close_attempts': door_close_attempts,
        'protection_active': bool(protection_ends),
        'pump_on': pump_on,
        'elevator_on': elevator_on,
        'protection_remaining': int(max(0, max(protection_ends.values()) - time.time())) if protection_ends else 0,
        'protection_targets': list(protection_ends.keys()),
    }

# ----------------------------------------------------------------------
# Credenciales desde variables de entorno (obligatorias para envíos reales)
# ----------------------------------------------------------------------
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', '')

# ----------------------------------------------------------------------
# Suscriptores (persistencia)
# ----------------------------------------------------------------------
SUBSCRIBERS_FILE = "subscribers.json"

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'r') as f:
            return json.load(f)
    else:
        return {
            "email": {"Bajo": [], "Medio": [], "Alto": [], "Crítico": []},
            "whatsapp": {"Bajo": [], "Medio": [], "Alto": [], "Crítico": []},
            "telegram": {"Bajo": [], "Medio": [], "Alto": [], "Crítico": []}
        }

def save_subscribers(data):
    with open(SUBSCRIBERS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

subscribers = load_subscribers()

# ----------------------------------------------------------------------
# Umbrales de riesgo (configurables)
# ----------------------------------------------------------------------
DEFAULT_THRESHOLDS = {
    'flow_rate': {'direction': 'higher', 'low': 20, 'medium': 35, 'high': 45},
    'pressure': {'direction': 'higher', 'low': 5, 'medium': 7, 'high': 9},
    'temperature': {'direction': 'higher', 'low': 70, 'medium': 85, 'high': 100},
    'vibration': {'direction': 'higher', 'low': 4, 'medium': 7, 'high': 10},
    'tank_level': {'direction': 'lower', 'low': 30, 'medium': 15, 'high': 5},
    'speed': {'direction': 'higher', 'low': 1.5, 'medium': 2.5, 'high': 3.5},
    'load': {'direction': 'higher', 'low': 400, 'medium': 700, 'high': 900},
    'trip_count': {'direction': 'higher', 'low': 10000, 'medium': 20000, 'high': 30000},
    'energy': {'direction': 'higher', 'low': 8, 'medium': 12, 'high': 15},
    'voltage': {'direction': 'range', 'low': 200, 'high': 240},
    'current': {'direction': 'higher', 'low': 30, 'medium': 40, 'high': 50},
}
NO_RISK_VARS = ['position', 'door_status', 'motor_stuck']
RATIONING_THRESHOLD = 8.0
MAX_HISTORY_SIZE = 500

thresholds = DEFAULT_THRESHOLDS.copy()
alert_enabled = True
alert_log = []
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
    'flow_rate': 15.0, 'pressure': 4.0, 'temperature': 50.0, 'vibration': 2.0, 'tank_level': 80.0,
    'position': 0, 'speed': 0.0, 'load': 200, 'trip_count': 5000, 'door_status': 'closed', 'energy': 5.0,
    'voltage': 220.0, 'current': 20.0, 'motor_stuck': False,
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
    units = {'flow_rate':'L/s','pressure':'bar','temperature':'°C','vibration':'mm/s','tank_level':'%','position':'piso','speed':'m/s','load':'kg','trip_count':'viajes','door_status':'','energy':'kW','voltage':'V','current':'A','motor_stuck':''}
    return units.get(var, '')

def classify_risk(variable, value):
    if variable == 'motor_stuck':
        return ("Crítico","red") if value else ("Bajo","green")
    if variable in NO_RISK_VARS:
        return "Bajo", "green"
    if variable in ('flow_rate', 'pressure') and value == 0:
        return "Crítico", "red"
    if variable not in thresholds:
        return "Desconocido", "gray"
    cfg = thresholds[variable]
    d = cfg['direction']
    if d == 'range':
        low, high = cfg['low'], cfg['high']
        return ("Bajo","green") if low <= value <= high else ("Alto","orange")
    else:
        low, med, high = cfg['low'], cfg['medium'], cfg['high']
        if d == 'higher':
            if value <= low: return "Bajo","green"
            elif value <= med: return "Medio","yellow"
            elif value <= high: return "Alto","orange"
            else: return "Crítico","red"
        else:
            if value >= low: return "Bajo","green"
            elif value >= med: return "Medio","yellow"
            elif value >= high: return "Alto","orange"
            else: return "Crítico","red"

def generate_recommendations(data, stats=None):
    recs = []
    if data['temperature'] > 85:
        recs.append("⚠️ Temperatura del motor muy alta (>85°C). Revisar refrigeración.")
    elif data['temperature'] > 70:
        recs.append("📈 Temperatura elevada. Monitorear.")
    if data['flow_rate'] < 10:
        recs.append("🚰 Caudal bajo (<10 L/s). Revisar bomba.")
    elif data['flow_rate'] < 20:
        recs.append("💧 Caudal bajo óptimo. Revisar filtros.")
    if data['pressure'] > 8:
        recs.append("💥 Presión excesiva (>8 bar). Riesgo de fugas.")
    if data['vibration'] > 7:
        recs.append("📳 Vibración anómala (>7 mm/s). Verificar alineamiento.")
    if data['tank_level'] < 20:
        recs.append("⛽ Nivel de tanque crítico (<20%). Reposición urgente.")
    elif data['tank_level'] < 30:
        recs.append("⚠️ Nivel de tanque bajo.")
    if data['load'] > 800:
        recs.append("🏋️ Sobrepeso en ascensor (>800 kg). Reducir carga.")
    if data['voltage'] < 200 or data['voltage'] > 240:
        recs.append("⚡ Inestabilidad eléctrica. Revisar suministro.")
    if data['current'] > 45:
        recs.append("🔌 Sobrecarga eléctrica (corriente >45A).")
    if data['motor_stuck']:
        recs.append("🛑 MOTOR PEGADO. Mantenimiento urgente.")
    at_floor = abs(data['position'] - round(data['position'])) < 0.05
    if data['speed'] == 0 and at_floor and door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
        if LOG_SIM:
            print(f"[SIM] {time.strftime('%H:%M:%S')} DOORS: speed={data['speed']} at_floor={at_floor} door_close_attempts={door_close_attempts} position={data['position']}")
        recs.append(f"⚠️ Revisar puertas: {door_close_attempts} intentos de cierre fallidos.")
    if not recs:
        recs.append("✅ Todos los parámetros normales. Operación estable.")
    return recs[:5]


def reset_critical_values(targets):
    """Resetear valores críticos asociados a los dispositivos deshabilitados para evitar re-triggers inmediatos."""
    global sensor_data
    if not targets:
        return
    if 'pump' in targets:
        sensor_data['flow_rate'] = 25.0
        sensor_data['pressure'] = 4.0
        sensor_data['temperature'] = 50.0
        sensor_data['vibration'] = 1.5
        sensor_data['tank_level'] = 80.0
        sensor_data['voltage'] = 220.0
        sensor_data['current'] = 18.0
    if 'elevator' in targets:
        sensor_data['position'] = 0
        sensor_data['speed'] = 0.0
        sensor_data['load'] = 200
        sensor_data['motor_stuck'] = False
        sensor_data['door_status'] = 'closed'
        sensor_data['energy'] = 5.0
        sensor_data['temperature'] = 50.0
        global door_close_attempts
        door_close_attempts = 0


# Se eliminó la lógica de fallas agendadas. Las fallas se generan aleatoriamente
# durante `update_sensor_data()` y son manejadas por protección por dispositivo.

# ----------------------------------------------------------------------
# Envío de alertas (reales si hay credenciales)
# ----------------------------------------------------------------------
def send_email_alert(risk_level, subject, body):
    recipients = subscribers["email"].get(risk_level, [])
    if not recipients:
        logger.info(f"No hay suscriptores para nivel {risk_level} en email")
        return
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(f"⚠️ CREDENCIALES SMTP NO CONFIGURADAS. No se enviará email real a {recipients}.")
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        for rec in recipients:
            msg['To'] = rec
            server.send_message(msg)
            logger.info(f"✅ Email REAL enviado a {rec} (riesgo {risk_level})")
        server.quit()
    except Exception as e:
        logger.error(f"Error enviando email: {e}")

def send_telegram_alert(risk_level, message):
    recipients = subscribers["telegram"].get(risk_level, [])
    if not recipients:
        logger.info(f"No hay suscriptores para nivel {risk_level} en Telegram")
        return
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN no configurado. No se enviará mensaje real.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        for chat_id in recipients:
            payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
            resp = requests.post(url, data=payload, timeout=5)
            if resp.status_code == 200:
                logger.info(f"✅ Telegram REAL enviado a {chat_id} (riesgo {risk_level})")
            else:
                logger.error(f"Error Telegram: {resp.text}")
    except Exception as e:
        logger.error(f"Error Telegram: {e}")

def send_whatsapp_alert(risk_level, message):
    recipients = subscribers["whatsapp"].get(risk_level, [])
    if not recipients:
        logger.info(f"No hay suscriptores para nivel {risk_level} en WhatsApp")
        return
    if not TWILIO_ACCOUNT_SID or not TWILIO_WHATSAPP_FROM:
        logger.warning("⚠️ Credenciales Twilio no configuradas. No se enviará WhatsApp real.")
        return
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        for to in recipients:
            client.messages.create(body=message, from_=TWILIO_WHATSAPP_FROM, to=to)
            logger.info(f"✅ WhatsApp REAL enviado a {to} (riesgo {risk_level})")
    except ImportError:
        logger.warning("Twilio no instalado: pip install twilio")
    except Exception as e:
        logger.error(f"Error WhatsApp: {e}")

def persist_notification_in_django(variable, value, risk_level, recommended_action):
    if not DJANGO_CONNECTED:
        return
    try:
        equipo = EquipoMonitoreo.objects.first() if EquipoMonitoreo.objects.exists() else None
        Notificacion.objects.create(
            id_usuario_id=None,
            id_equipo_monitoreo=equipo,
            fecha=timezone.now(),
            mensaje=f"[{risk_level}] {variable} = {value} - {recommended_action}"
        )
    except Exception as e:
        logger.warning('No se pudo guardar notificación en la DB de Django: %s', e)


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
        if device == 'pump':
            pump_on = False
        elif device == 'elevator':
            elevator_on = False
    reason_text = f" ({reason})" if reason else ''
    targets_text = ' y '.join(sorted(targets_set))
    logger.warning(f"⚠️ PROTECCIÓN ACTIVADA{reason_text}. Apagando: {targets_text}.")
    notification_payload = {
        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
        'variable': 'Protección automática',
        'value': None,
        'risk': 'Crítico',
        'message': f'Protección automática activada{reason_text}. Targets: {targets_text}.'
    }
    alert_log.insert(0, notification_payload)
    pending_notifications.append(notification_payload)
    try:
        socketio.emit('notification', notification_payload, broadcast=True)
    except Exception:
        pass


def update_protection_state():
    """Restaurar dispositivos cuya protección expiró (por dispositivo)."""
    global pump_on, elevator_on, protection_ends
    now = time.time()
    expired = [d for d, end in protection_ends.items() if end and now >= end]
    for device in expired:
        if device == 'pump':
            pump_on = True
        elif device == 'elevator':
            elevator_on = True
        try:
            reset_critical_values({device})
        except Exception:
            logger.exception('Error reseteando valores críticos para %s', device)
        # Limpiar alertas activas relacionadas con el dispositivo
        try:
            if device == 'pump':
                for v in ['flow_rate','pressure','temperature','vibration','tank_level','voltage','current','Racionamiento']:
                    active_alerts.pop(v, None)
            elif device == 'elevator':
                for v in ['position','speed','load','trip_count','door_status','energy','motor_stuck']:
                    active_alerts.pop(v, None)
        except Exception:
            pass
        del protection_ends[device]
        logger.info("✅ Protección finalizada para %s. Dispositivo restaurado.", device)
        notification_payload = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'variable': f'Protección {device}',
            'value': None,
            'risk': 'Info',
            'message': f'Protección finalizada para {device}. Operación normal restaurada.'
        }
        alert_log.insert(0, notification_payload)
        pending_notifications.append(notification_payload)
        try:
            socketio.emit('notification', notification_payload, broadcast=True)
        except Exception:
            pass


def send_alert(variable, value, risk_level, recommended_action):
    global active_alerts
    if not alert_enabled:
        logger.info("Alertas desactivadas por el usuario")
        return
    if variable in active_alerts and active_alerts[variable] == risk_level:
        return
    active_alerts[variable] = risk_level
    device_target = None
    try:
        bomba_vars = ['flow_rate','pressure','temperature','vibration','tank_level','voltage','current']
        ascensor_vars = ['position','speed','load','trip_count','door_status','energy','motor_stuck']
        if variable in bomba_vars or variable == 'Racionamiento':
            device_target = 'pump'
        elif variable in ascensor_vars or variable == 'motor_stuck':
            device_target = 'elevator'
    except Exception:
        device_target = None
    if LOG_SIM:
        print(f"[SIM] {time.strftime('%H:%M:%S')} ALERT: {variable}={value} level={risk_level} mapped={device_target} protection_ends={protection_ends}")
    if risk_level in ('Alto', 'Crítico'):
        if device_target:
            enter_protection_mode(f'Alerta {risk_level} de {variable}', targets={device_target})
        else:
            logger.warning(f"Alerta crítica para {variable} sin mapeo a dispositivo; no se activará protección automática.")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[ALERTA {risk_level.upper()}] {variable} = {value}"
    body = f"{timestamp}\nSensor: {variable}\nValor: {value}\nRiesgo: {risk_level}\nAcciÃ³n: {recommended_action}"
    threading.Thread(target=send_email_alert, args=(risk_level, subject, body), daemon=True).start()
    threading.Thread(target=send_telegram_alert, args=(risk_level, body), daemon=True).start()
    threading.Thread(target=send_whatsapp_alert, args=(risk_level, body), daemon=True).start()
    notification_payload = {
        'timestamp': timestamp,
        'variable': variable,
        'value': value,
        'risk': risk_level,
        'message': recommended_action
    }
    alert_log.insert(0, notification_payload)
    pending_notifications.append(notification_payload)
    persist_notification_in_django(variable, value, risk_level, recommended_action)
    try:
        socketio.emit('notification', notification_payload, broadcast=True)
    except Exception:
        pass
    while len(alert_log) > MAX_LOG_ENTRIES:
        alert_log.pop()

def check_rationing(flow_rate):
    if flow_rate < RATIONING_THRESHOLD:
        send_alert("Racionamiento", flow_rate, "Crítico", f"Caudal muy bajo ({flow_rate} L/s). Reducir consumo.")
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
    if 'pump' not in protection_ends and pump_on and random.random() < 0.15:
        sensor_data['flow_rate'] = 0.0
        sensor_data['pressure'] = 0.0
        sensor_data['vibration'] = 12.0
        sensor_data['temperature'] = 85.0
        sensor_data['current'] = 40.0
        logger.info('Inyectada falla aleatoria: pump')
        if LOG_SIM: print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: pump falla -> protection_ends={protection_ends}")
        # posibilidad de fallo simultáneo en ascensor
        if 'elevator' not in protection_ends and elevator_on and random.random() < SIMULTANEOUS_FAIL_PROB:
            sensor_data['speed'] = 0.0
            sensor_data['load'] = 950
            sensor_data['motor_stuck'] = True
            sensor_data['door_status'] = 'closed'
            sensor_data['energy'] = 12.0
            sensor_data['temperature'] = 95.0
            logger.info('Inyectada falla simultánea: elevator')
            if LOG_SIM: print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION-SIMULT: elevator falla -> protection_ends={protection_ends}")
    # Inyectar falla de ascensor aleatoria si no está protegida
    if 'elevator' not in protection_ends and elevator_on and random.random() < 0.12:
        sensor_data['speed'] = 0.0
        sensor_data['load'] = 950
        sensor_data['motor_stuck'] = True
        sensor_data['door_status'] = 'closed'
        sensor_data['energy'] = 12.0
        sensor_data['temperature'] = 95.0
        logger.info('Inyectada falla aleatoria: elevator')
        if LOG_SIM: print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: elevator falla -> protection_ends={protection_ends}")
        # posibilidad de fallo simultáneo en bomba
        if 'pump' not in protection_ends and pump_on and random.random() < SIMULTANEOUS_FAIL_PROB:
            sensor_data['flow_rate'] = 0.0
            sensor_data['pressure'] = 0.0
            sensor_data['vibration'] = 12.0
            sensor_data['temperature'] = 85.0
            sensor_data['current'] = 40.0
            logger.info('Inyectada falla simultánea: pump')
            if LOG_SIM: print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION-SIMULT: pump falla -> protection_ends={protection_ends}")
    pump_protected = 'pump' in protection_ends or not pump_on
    elevator_protected = 'elevator' in protection_ends or not elevator_on

    if pump_protected:
        # Mantener la falla de bomba durante la protección y evitar normalización prematura.
        sensor_data['flow_rate'] = round(max(0, min(60, sensor_data['flow_rate'])), 1)
        sensor_data['pressure'] = round(max(0, min(12, sensor_data['pressure'])), 1)
        sensor_data['temperature'] = round(max(20, min(130, sensor_data['temperature'])), 1)
        sensor_data['vibration'] = round(max(0, min(15, sensor_data['vibration'])), 1)
        sensor_data['tank_level'] = round(max(0, min(100, sensor_data['tank_level'])), 1)
        sensor_data['voltage'] = round(max(180, min(260, sensor_data['voltage'])), 1)
        sensor_data['current'] = round(max(0, min(70, sensor_data['current'])), 1)
    else:
        fd = sensor_data['flow_rate'] + random.uniform(-1.5, 1.5)
        if random.random() < 0.05: fd += random.uniform(5, 15)
        sensor_data['flow_rate'] = round(max(0, min(60, fd)), 1)
        sensor_data['current'] = round(max(0, min(70, sensor_data['current'] + random.uniform(-1, 1) + (sensor_data['load'] / 100) * 0.1)), 1)

        p = sensor_data['pressure'] + random.uniform(-0.3, 0.3) + (sensor_data['flow_rate'] - 20) * 0.02
        sensor_data['pressure'] = round(max(0, min(12, p)), 1)
        t = sensor_data['temperature'] + random.uniform(-0.5, 1.0) + max(0, (sensor_data['pressure'] - 5) * 0.2)
        if random.random() < 0.03: t += random.uniform(5, 20)
        sensor_data['temperature'] = round(max(20, min(130, t)), 1)
        v = sensor_data['vibration'] + random.uniform(-0.3, 0.5) + (sensor_data['flow_rate'] / 30) + (max(0, sensor_data['temperature']-70)/20)
        sensor_data['vibration'] = round(max(0, min(15, v)), 1)
        lvl = sensor_data['tank_level'] - sensor_data['flow_rate'] * 0.1
        if random.random() < 0.1: lvl += random.uniform(5, 15)
        sensor_data['tank_level'] = round(max(0, min(100, lvl)), 1)

    prev_pos = sensor_data['position']
    prev_door = sensor_data['door_status']
    pos = prev_pos
    spd = sensor_data['speed']
    global door_close_attempts
    if not elevator_on:
        spd = 0
        sensor_data['door_status'] = 'closed'
        door_close_attempts = 0
        # Mantener carga actual mientras el ascensor está en protección
        # (no reducirla automáticamente)
    else:
        if random.random() < 0.3:
            spd = random.choice([0, random.uniform(0.5, 2.5)])
        pos += spd * 2
        if pos > 20: pos, spd = 20, 0
        if pos < 0: pos, spd = 0, 0
        at_floor = abs(pos - round(pos)) < 0.05
        if spd != 0:
            sensor_data['door_status'] = 'closed'
            door_close_attempts = 0
        else:
            if not at_floor:
                sensor_data['door_status'] = 'closed'
                door_close_attempts = 0
            else:
                if prev_door == 'open':
                    if door_close_attempts < MAX_DOOR_CLOSE_ATTEMPTS:
                        if random.random() < DOOR_CLOSE_SUCCESS_PROB:
                            sensor_data['door_status'] = 'closed'
                        else:
                            sensor_data['door_status'] = 'open'
                        door_close_attempts += 1
                        if LOG_SIM:
                            print(f"[SIM] {time.strftime('%H:%M:%S')} DOORS_EVENT: increment attempts -> {door_close_attempts}")
                    else:
                        sensor_data['door_status'] = 'open'
                elif door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
                    sensor_data['door_status'] = 'open'
                else:
                    if random.random() < DOOR_OPEN_PROB:
                        sensor_data['door_status'] = 'open'
                    else:
                        sensor_data['door_status'] = 'closed'
        sensor_data['load'] = round(max(0, min(1200, sensor_data['load'] + (random.randint(-100, 150) if random.random() < 0.2 else 0))))
        if random.random() < 0.1:
            sensor_data['trip_count'] += 1
    # Reset attempts si el ascensor se mueve o cambia piso
    if abs(pos - prev_pos) > 0.1 or spd != 0:
        if door_close_attempts != 0 and LOG_SIM:
            print(f"[SIM] {time.strftime('%H:%M:%S')} DOORS_EVENT: reset attempts (pos change or movement) -> was {door_close_attempts}")
        door_close_attempts = 0
    sensor_data['position'] = round(pos, 1)
    sensor_data['speed'] = round(spd, 1)
    if elevator_protected:
        sensor_data['energy'] = round(max(0, min(20, sensor_data['energy'])), 1)
    else:
        energy = (sensor_data['load'] / 500) * spd * 2 + random.uniform(0.5, 2)
        sensor_data['energy'] = round(max(0, min(20, energy)), 1)
    if pump_protected:
        sensor_data['voltage'] = round(max(180, min(260, sensor_data['voltage'])), 1)
    else:
        volt = sensor_data['voltage'] + random.uniform(-3, 3)
        if random.random() < 0.02:
            volt += random.uniform(-20, 20)
        sensor_data['voltage'] = round(max(180, min(260, volt)), 1)
    curr = sensor_data['current']
    if not pump_on:
        curr = round(max(0, curr), 1)
    else:
        curr = round(max(0, min(70, curr + random.uniform(-1, 1) + (sensor_data['load'] / 100) * 0.1)), 1)
    sensor_data['current'] = curr
    stuck = check_motor_stuck(sensor_data['speed'], sensor_data['load'], sensor_data['temperature'])
    sensor_data['motor_stuck'] = stuck

def generate_data_and_emit():
    while True:
        eventlet.sleep(2)
        update_protection_state()
        update_sensor_data()
        for var, value in sensor_data.items():
            if var == 'motor_stuck':
                if value:
                    send_alert(var, value, "Crítico", "Motor pegado - Revisar inmediatamente")
                else:
                    active_alerts.pop(var, None)
                continue
            risk, _ = classify_risk(var, value)
            if risk in ('Alto', 'Crítico'):
                send_alert(var, value, risk, f"Revisar {var}. Valor {value} - Riesgo {risk}")
            else:
                active_alerts.pop(var, None)
        check_rationing(sensor_data['flow_rate'])
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        new_readings = []
        for var, value in sensor_data.items():
            risk, color = classify_risk(var, value) if var != 'motor_stuck' else ("Crítico" if value else "Bajo", "red" if value else "green")
            sensor_type = 'Bomba' if var in ['flow_rate','pressure','temperature','vibration','tank_level','voltage','current'] else 'Ascensor'
            new_readings.append({'timestamp': timestamp, 'type': sensor_type, 'variable': var, 'value': value, 'risk': risk, 'color': color})
        global history
        history.extend(new_readings)
        if len(history) > MAX_HISTORY_SIZE:
            history = history[-MAX_HISTORY_SIZE:]
        stats = {}
        for var in ['temperature','flow_rate','pressure','vibration','tank_level','load','voltage','current']:
            vals = [r['value'] for r in history if r['variable'] == var and isinstance(r['value'], (int, float))]
            if vals:
                stats[var] = {'avg': sum(vals)/len(vals), 'min': min(vals), 'max': max(vals)}
        payload = build_live_payload()
        if LOG_SIM:
            print(f"[SIM] {time.strftime('%H:%M:%S')} LOOP: pump_on={pump_on} elevator_on={elevator_on} protection_ends={protection_ends}")
        socketio.emit('sensor_update', payload)

# ----------------------------------------------------------------------
# Reporte PDF mejorado (con gráfico de barras)
# ----------------------------------------------------------------------
class PDFReport(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'R')
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generate_pdf_report(period):
    if not PDF_AVAILABLE:
        raise ImportError("fpdf2 no instalado")
    now = datetime.now()
    if period == 'minute':
        start_time = now - timedelta(minutes=1); period_name = "Último minuto"
    elif period == 'ten_minutes':
        start_time = now - timedelta(minutes=10); period_name = "Últimos 10 minutos"
    elif period == 'hour':
        start_time = now - timedelta(hours=1); period_name = "Última hora"
    elif period == 'day':
        start_time = now - timedelta(days=1); period_name = "Último día"
    elif period == 'week':
        start_time = now - timedelta(days=7); period_name = "Última semana"
    else:
        start_time = now - timedelta(days=30); period_name = "Último mes"
    filtered_readings = [r for r in history if datetime.strptime(r['timestamp'], "%Y-%m-%d %H:%M:%S") >= start_time]
    numeric_vars = ['flow_rate','pressure','temperature','vibration','tank_level','speed','load','trip_count','energy','voltage','current']
    stats = {}
    for var in numeric_vars:
        vals = [r['value'] for r in filtered_readings if r['variable']==var and isinstance(r['value'],(int,float))]
        if vals:
            stats[var] = {'min':min(vals), 'max':max(vals), 'avg':sum(vals)/len(vals), 'count':len(vals)}
        else:
            stats[var] = {'min':'N/A', 'max':'N/A', 'avg':'N/A', 'count':0}
    alerts_in_period = [a for a in alert_log if datetime.strptime(a['timestamp'],"%Y-%m-%d %H:%M:%S") >= start_time]
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 20)
    pdf.cell(0, 20, 'SISTEMA PCLogo', ln=1, align='C')
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Reporte de Monitoreo', ln=1, align='C')
    pdf.ln(10)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 8, f'Generado: {now.strftime("%d/%m/%Y %H:%M:%S")}', ln=1, align='C')
    pdf.cell(0, 8, f'Período: {period_name} (desde {start_time.strftime("%d/%m/%Y %H:%M:%S")})', ln=1, align='C')
    pdf.ln(10)
    # Leyenda de riesgos
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Leyenda de Riesgos', ln=1)
    pdf.set_font('Arial', '', 10)
    pdf.set_fill_color(34,197,94); pdf.cell(30,8,' Bajo',1,0,'L',True); pdf.cell(160,8,'Valores normales',1,1,'L')
    pdf.set_fill_color(234,179,8); pdf.cell(30,8,' Medio',1,0,'L',True); pdf.cell(160,8,'Cerca del límite, monitorear',1,1,'L')
    pdf.set_fill_color(249,115,22); pdf.cell(30,8,' Alto',1,0,'L',True); pdf.cell(160,8,'Fuera de rango peligroso',1,1,'L')
    pdf.set_fill_color(239,68,68); pdf.cell(30,8,' Crítico',1,0,'L',True); pdf.cell(160,8,'Acción inmediata',1,1,'L')
    pdf.ln(8)
    # Gráfico de barras
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Gráfico de Barras: Valores Promedio', ln=1)
    bar_vars = ['temperature','pressure','flow_rate','vibration','tank_level','load','energy','voltage','current']
    display_names = {'temperature':'Temp. (°C)','pressure':'Presión (bar)','flow_rate':'Caudal (L/s)','vibration':'Vibración (mm/s)','tank_level':'Nivel tanque (%)','load':'Carga (kg)','energy':'Energía (kW)','voltage':'Voltaje (V)','current':'Corriente (A)'}
    labels = []
    avgs = []
    for v in bar_vars:
        if v in stats and isinstance(stats[v]['avg'], float):
            labels.append(display_names.get(v, v))
            avgs.append(stats[v]['avg'])
    if avgs:
        max_avg = max(avgs)
        x0 = 30
        y0 = pdf.get_y()
        bar_width = 30
        spacing = 12
        max_bar_height = 80
        pdf.set_font('Arial', '', 7)
        for i, (lab, val) in enumerate(zip(labels, avgs)):
            x = x0 + i*(bar_width + spacing)
            if x + bar_width > 190: break
            height = (val / max_avg) * max_bar_height if max_avg>0 else 10
            pdf.set_fill_color(70,130,200)
            pdf.rect(x, y0+max_bar_height-height, bar_width, height, 'F')
            pdf.set_xy(x, y0+max_bar_height-height-4)
            pdf.cell(bar_width, 4, f'{val:.1f}', 0, 0, 'C')
            pdf.set_xy(x, y0+max_bar_height+2)
            pdf.cell(bar_width, 5, lab, 0, 0, 'C')
        pdf.set_y(y0+max_bar_height+15)
    pdf.ln(5)
    # Tabla valores actuales
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Valores Actuales', ln=1)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(80, 8, 'Variable', 1, 0, 'C', 1)
    pdf.cell(50, 8, 'Valor', 1, 0, 'C', 1)
    pdf.cell(60, 8, 'Riesgo', 1, 1, 'C', 1)
    pdf.set_font('Arial', '', 9)
    for var, val in sensor_data.items():
        risk, color = classify_risk(var, val)
        if color == 'green': fill = (34,197,94)
        elif color == 'yellow': fill = (234,179,8)
        elif color == 'orange': fill = (249,115,22)
        elif color == 'red': fill = (239,68,68)
        else: fill = (200,200,200)
        pdf.set_fill_color(*fill)
        if isinstance(val, bool): val_str = "Sí" if val else "No"
        else: val_str = f"{val} {get_unit(var)}"
        pdf.cell(80, 8, var.replace('_',' ').title(), 1, 0, 'L', True)
        pdf.cell(50, 8, val_str, 1, 0, 'L', True)
        pdf.cell(60, 8, risk, 1, 1, 'C', True)
    pdf.ln(5)
    # Estadísticas
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f'Estadísticas - {period_name}', ln=1)
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(240,240,240)
    pdf.cell(50, 7, 'Variable', 1, 0, 'C', 1)
    pdf.cell(35, 7, 'Mínimo', 1, 0, 'C', 1)
    pdf.cell(35, 7, 'Máximo', 1, 0, 'C', 1)
    pdf.cell(35, 7, 'Promedio', 1, 0, 'C', 1)
    pdf.cell(35, 7, 'Lecturas', 1, 1, 'C', 1)
    pdf.set_font('Arial', '', 8)
    for var in numeric_vars:
        s = stats[var]
        pdf.cell(50, 6, var.replace('_',' ').title(), 1)
        pdf.cell(35, 6, str(s['min']), 1)
        pdf.cell(35, 6, str(s['max']), 1)
        avg_val = f"{s['avg']:.2f}" if isinstance(s['avg'], float) else "N/A"
        pdf.cell(35, 6, avg_val, 1)
        pdf.cell(35, 6, str(s['count']), 1, 1)
    pdf.ln(5)
    # Recomendaciones
    recs = []
    if 'temperature' in stats and isinstance(stats['temperature']['avg'], float):
        if stats['temperature']['avg'] > 85: recs.append("Temperatura promedio elevada. Mejorar ventilación.")
    if 'flow_rate' in stats and isinstance(stats['flow_rate']['avg'], float):
        if stats['flow_rate']['avg'] < 10: recs.append("Caudal promedio bajo. Revisar bomba y filtros.")
    if 'pressure' in stats and isinstance(stats['pressure']['avg'], float):
        if stats['pressure']['avg'] > 7: recs.append("Presión media alta. Verificar reguladores.")
    if 'tank_level' in stats and isinstance(stats['tank_level']['avg'], float):
        if stats['tank_level']['avg'] < 25: recs.append("Nivel de tanque bajo. Aumentar frecuencia de recarga.")
    if not recs: recs.append("Parámetros dentro de rangos normales.")
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Recomendaciones', ln=1)
    pdf.set_font('Arial', '', 10)
    for rec in recs[:5]:
        pdf.cell(0, 6, f'- {rec}', ln=1)
    pdf.ln(5)
    # Alertas
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f'Alertas en el período: {len(alerts_in_period)}', ln=1)
    if alerts_in_period:
        pdf.set_font('Arial', 'B', 9)
        pdf.set_fill_color(255,220,220)
        pdf.cell(50, 7, 'Fecha/Hora', 1, 0, 'C', 1)
        pdf.cell(50, 7, 'Variable', 1, 0, 'C', 1)
        pdf.cell(40, 7, 'Valor', 1, 0, 'C', 1)
        pdf.cell(50, 7, 'Riesgo', 1, 1, 'C', 1)
        pdf.set_font('Arial', '', 8)
        for a in alerts_in_period[:15]:
            pdf.cell(50, 6, a['timestamp'], 1)
            pdf.cell(50, 6, a['variable'], 1)
            pdf.cell(40, 6, str(a['value']), 1)
            pdf.cell(50, 6, a['risk'], 1, 1)
    else:
        pdf.cell(0, 8, 'No hubo alertas en este período.', ln=1)
    # Racionamiento
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 12)
    if sensor_data['flow_rate'] < RATIONING_THRESHOLD:
        pdf.set_text_color(255,0,0)
        pdf.cell(0, 10, '⚠️ RACIONAMIENTO ACTIVO - Caudal por debajo del mínimo', ln=1, align='C')
    else:
        pdf.set_text_color(0,150,0)
        pdf.cell(0, 10, 'Racionamiento inactivo. Caudal normal.', ln=1, align='C')
    pdf_output = pdf.output(dest='S')
    if isinstance(pdf_output, str):
        pdf_output = pdf_output.encode('latin-1')
    return BytesIO(pdf_output)

# ----------------------------------------------------------------------
# Servidor Flask
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave-segura'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

@app.after_request
def apply_cors(response):
    response.headers.set('Access-Control-Allow-Origin', '*')
    response.headers.set('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.set('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    response.headers.set('Access-Control-Allow-Credentials', 'true')
    return response

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def api_status():
    return jsonify(build_live_payload())

@app.route('/stream/monitoreo')
def stream_monitoring():
    def event_stream():
        while True:
            eventlet.sleep(2)
            monitoring_payload = build_live_payload()
            yield f"data: {json.dumps(monitoring_payload)}\n\n"
            while pending_notifications:
                notification = pending_notifications.popleft()
                yield f"event: notification\n"
                yield f"data: {json.dumps(notification)}\n\n"
    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/api/notifications')
def api_notifications():
    if not DJANGO_CONNECTED:
        return jsonify({'error': 'Django no está disponible'}), 500
    try:
        notifications = Notificacion.objects.select_related('id_equipo_monitoreo__id_edificio').order_by('-fecha')[:50]
        payload = []
        for n in notifications:
            payload.append({
                'id': n.id_notificacion,
                'fecha': n.fecha.isoformat() if n.fecha else None,
                'mensaje': n.mensaje,
                'equipo': n.id_equipo_monitoreo.nb_equipo if n.id_equipo_monitoreo else None,
                'edificio': n.id_equipo_monitoreo.id_edificio.nb_edificio if n.id_equipo_monitoreo and n.id_equipo_monitoreo.id_edificio else None,
            })
        return jsonify(payload)
    except Exception as e:
        logger.warning('Error al buscar notificaciones Django: %s', e)
        return jsonify({'error': str(e)}), 500

@app.route('/get_thresholds')
def get_thresholds():
    return jsonify(thresholds)

@app.route('/update_thresholds', methods=['POST'])
def update_thresholds():
    global thresholds
    thresholds.update(request.json)
    return jsonify({'status': 'ok', 'thresholds': thresholds})

@app.route('/toggle_alerts', methods=['POST'])
def toggle_alerts():
    global alert_enabled
    alert_enabled = request.json.get('enabled', True)
    return jsonify({'status': 'ok', 'alert_enabled': alert_enabled})

@app.route('/get_alert_log')
def get_alert_log():
    return jsonify(alert_log[:100])

@app.route('/clear_history', methods=['POST'])
def clear_history():
    global history
    history = []
    return jsonify({'status': 'ok', 'message': 'Historial limpiado'})

@app.route('/get_subscribers', methods=['GET'])
def get_subscribers():
    return jsonify(subscribers)

@app.route('/add_subscriber', methods=['POST'])
def add_subscriber():
    data = request.json
    channel = data.get('channel')
    risk_level = data.get('risk_level')
    contact = data.get('contact')
    if channel not in subscribers or risk_level not in subscribers[channel]:
        return jsonify({'status': 'error', 'message': 'Canal o nivel inválido'}), 400
    if contact in subscribers[channel][risk_level]:
        return jsonify({'status': 'error', 'message': 'El contacto ya existe'}), 400
    subscribers[channel][risk_level].append(contact)
    save_subscribers(subscribers)
    return jsonify({'status': 'ok', 'subscribers': subscribers})

@app.route('/remove_subscriber', methods=['POST'])
def remove_subscriber():
    data = request.json
    channel = data.get('channel')
    risk_level = data.get('risk_level')
    contact = data.get('contact')
    if channel in subscribers and risk_level in subscribers[channel]:
        if contact in subscribers[channel][risk_level]:
            subscribers[channel][risk_level].remove(contact)
            save_subscribers(subscribers)
            return jsonify({'status': 'ok'})
    return jsonify({'status': 'error', 'message': 'No encontrado'}), 400

@app.route('/test_alert/<channel>/<risk_level>/<contact>')
def test_alert(channel, risk_level, contact):
    if channel not in ['email', 'whatsapp', 'telegram']:
        return f"Canal inválido", 400
    original = subscribers[channel].get(risk_level, [])
    if contact not in original:
        subscribers[channel][risk_level].append(contact)
    message = f"🔔 ALERTA DE PRUEBA: Nivel {risk_level.upper()} - Verificación del sistema PCLogo."
    if channel == 'email':
        send_email_alert(risk_level, "Prueba PCLogo", message)
    elif channel == 'telegram':
        send_telegram_alert(risk_level, message)
    elif channel == 'whatsapp':
        send_whatsapp_alert(risk_level, message)
    if contact not in original:
        subscribers[channel][risk_level] = original
        save_subscribers(subscribers)
    return f"Prueba enviada a {contact} (riesgo {risk_level}) - Revisa logs y tu dispositivo."

@app.route('/manual_update', methods=['POST'])
def manual_update():
    data = request.json
    variable = data.get('variable')
    value = data.get('value')
    if variable not in sensor_data:
        return jsonify({'status': 'error', 'message': 'Variable no válida'}), 400
    if variable == 'door_status':
        if value not in ['open', 'closed']:
            return jsonify({'status': 'error', 'message': 'door_status debe ser "open" o "closed"'}), 400
        sensor_data[variable] = value
    elif variable == 'motor_stuck':
        sensor_data[variable] = bool(value)
    else:
        try:
            sensor_data[variable] = float(value)
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Valor numérico inválido'}), 400
    risk, _ = classify_risk(variable, sensor_data[variable]) if variable != 'motor_stuck' else ("Crítico" if sensor_data[variable] else "Bajo")
    if risk in ('Alto', 'Crítico') and alert_enabled:
        send_alert(variable, sensor_data[variable], risk, f"Valor manual: {sensor_data[variable]} - Riesgo {risk}")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    sensor_type = 'Bomba' if variable in ['flow_rate','pressure','temperature','vibration','tank_level','voltage','current'] else 'Ascensor'
    history.append({
        'timestamp': timestamp, 'type': sensor_type, 'variable': f"{variable} (manual)",
        'value': sensor_data[variable], 'risk': risk, 'color': 'red' if risk in ('Alto','Crítico') else 'green'
    })
    if len(history) > MAX_HISTORY_SIZE: history.pop(0)
    stats = {}
    for var in ['temperature','flow_rate','pressure','vibration','tank_level','load','voltage','current']:
        vals = [r['value'] for r in history if r['variable'] == var and isinstance(r['value'], (int,float))]
        if vals:
            stats[var] = {'avg': sum(vals)/len(vals), 'min': min(vals), 'max': max(vals)}
    recs = generate_recommendations(sensor_data, stats)
    socketio.emit('sensor_update', {
        'current': sensor_data, 'history': history, 'thresholds': thresholds,
        'alert_enabled': alert_enabled, 'alert_log': alert_log[:50],
        'rationing': sensor_data['flow_rate'] < RATIONING_THRESHOLD,
        'door_close_attempts': door_close_attempts,
        'recommendations': recs, 'stats': stats
    })
    return jsonify({'status': 'ok', 'variable': variable, 'value': sensor_data[variable], 'risk': risk})

@app.route('/generate_report', methods=['POST'])
def generate_report():
    period = request.json.get('period', 'hour')
    try:
        pdf_buffer = generate_pdf_report(period)
        return send_file(pdf_buffer, as_attachment=True,
                         download_name=f"reporte_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                         mimetype='application/pdf')
    except Exception as e:
        logger.error(f"Error PDF: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    payload = build_live_payload()
    emit('init_data', payload)

# ----------------------------------------------------------------------
# Plantilla HTML completa (con gráficos de barras y diagnóstico)
# ----------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PCLogo - Monitoreo Avanzado</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        .risk-green { background-color: #10b981; color: white; }
        .risk-yellow { background-color: #f59e0b; color: black; }
        .risk-orange { background-color: #f97316; color: white; }
        .risk-red { background-color: #ef4444; color: white; }
        .card { transition: 0.2s; }
        .card:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(0,0,0,0.1); }
        .section-bomba { border-left: 4px solid #3b82f6; padding-left: 1rem; margin-top: 1rem; }
        .section-ascensor { border-left: 4px solid #8b5cf6; padding-left: 1rem; margin-top: 1rem; }
        .chart-container { background: white; border-radius: 0.75rem; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 1.5rem; }
        .rationing-badge { background: #dc2626; color: white; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: bold; animation: pulse 1s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
        canvas { max-height: 280px; width: 100%; }
        .rec-card { background: #f0f9ff; border-left: 4px solid #0284c7; }
        .scroll-table { max-height: 400px; overflow-y: auto; display: block; }
        .scroll-table table { width: 100%; }
        .scroll-table thead tr { position: sticky; top: 0; background: #f3f4f6; }
        .alert-row-critical { background-color: #fee2e2; }
        .alert-row-high { background-color: #ffedd5; }
        .warning-badge { background-color: #fef08a; color: #854d0e; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; }
    </style>
</head>
<body class="bg-gray-100 p-6">
    <div class="container mx-auto">
        <h1 class="text-3xl font-bold text-gray-800 mb-2">📊 PCLogo - Sistema de Monitoreo Avanzado</h1>
        <p class="text-gray-600 mb-6">Sensores de bomba, ascensor, eléctricos y motor</p>

        <div class="mb-4 flex flex-wrap justify-between items-center gap-2">
            <div class="flex gap-3">
                <button id="toggleAlertsBtn" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded shadow">
                    <i class="fas fa-bell"></i> Desactivar Alertas
                </button>
                <div id="rationingIndicator" class="hidden rationing-badge"><i class="fas fa-tint"></i> RACIONAMIENTO ACTIVO</div>
                <button id="clearHistoryBtn" class="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded shadow">
                    <i class="fas fa-trash-alt"></i> Limpiar Historial
                </button>
            </div>
            <div class="flex gap-2">
                <select id="reportPeriodSelect" class="border rounded p-2 bg-white shadow-sm">
                    <option value="minute">📄 Último minuto</option>
                    <option value="ten_minutes">📄 Últimos 10 min</option>
                    <option value="hour">📄 Última hora</option>
                    <option value="day">📄 Último día</option>
                    <option value="week">📄 Última semana</option>
                    <option value="month">📄 Último mes</option>
                </select>
                <button id="generateReportBtn" class="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded shadow">
                    <i class="fas fa-file-pdf"></i> Generar PDF
                </button>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 w-full">
                <div class="bg-white p-3 rounded-lg shadow text-sm text-gray-700">
                    <strong>Estado de protección:</strong> <span id="protectionStatus">OFF</span>
                </div>
                <div class="bg-white p-3 rounded-lg shadow text-sm text-gray-700">
                    <strong>Bomba:</strong> <span id="pumpStatus">ON</span>
                </div>
                <div class="bg-white p-3 rounded-lg shadow text-sm text-gray-700">
                    <strong>Ascensor:</strong> <span id="elevatorStatus">ON</span>
                </div>
            </div>
            <div class="text-sm text-gray-500">Última actualización: <span id="lastUpdate">--</span></div>
        </div>

        <!-- Diagnóstico de credenciales -->
        <div id="credsWarning" class="mb-4 p-2 rounded bg-yellow-100 text-yellow-800 text-sm hidden">
            ⚠️ <span id="credsMsg"></span>
        </div>

        <!-- Panel de estadísticas y recomendaciones -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <div class="bg-white p-4 rounded-xl shadow">
                <h2 class="text-xl font-bold text-gray-700 mb-2">📈 Estadísticas Recientes</h2>
                <div id="statsPanel" class="text-sm space-y-1"><p>Cargando...</p></div>
            </div>
            <div class="rec-card p-4 rounded-xl shadow">
                <h2 class="text-xl font-bold text-gray-700 mb-2">💡 Recomendaciones</h2>
                <div id="doorAttemptsInfo" class="text-xs text-gray-600 mb-2"></div>
                <div id="recommendationsPanel" class="text-sm space-y-2"><p>Cargando...</p></div>
            </div>
        </div>

        <!-- Suscriptores -->
        <div class="bg-white p-5 rounded-xl shadow-md mb-6">
            <h2 class="text-xl font-semibold mb-3">📢 Suscriptores de Alertas por Criticidad</h2>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                <div><label class="block text-sm font-medium">Canal</label><select id="subChannel" class="mt-1 block w-full border rounded p-2"><option value="email">Correo</option><option value="whatsapp">WhatsApp</option><option value="telegram">Telegram</option></select></div>
                <div><label class="block text-sm font-medium">Nivel Riesgo</label><select id="subRiskLevel" class="mt-1 block w-full border rounded p-2"><option value="Bajo">Bajo</option><option value="Medio">Medio</option><option value="Alto">Alto</option><option value="Crítico">Crítico</option></select></div>
                <div><label class="block text-sm font-medium">Contacto</label><input type="text" id="subContact" class="mt-1 block w-full border rounded p-2" placeholder="email / teléfono / chat_id"></div>
                <div class="flex items-end"><button id="addSubscriberBtn" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded shadow w-full"><i class="fas fa-plus"></i> Agregar</button></div>
            </div>
            <div id="subscribersList" class="text-sm border rounded p-3 max-h-60 overflow-y-auto">Cargando...</div>
            <div class="mt-2 text-xs text-gray-500">* Botón "Probar" envía una alerta de prueba al contacto.</div>
        </div>

        <!-- Control manual -->
        <div class="bg-white p-5 rounded-xl shadow-md mb-6">
            <h2 class="text-xl font-semibold mb-3">🎮 Control Manual de Sensores</h2>
            <div class="flex flex-wrap gap-4 items-end">
                <div class="flex-1 min-w-[200px]">
                    <label class="block text-sm font-medium text-gray-700">Sensor</label>
                    <select id="manualSensorSelect" class="mt-1 block w-full border-gray-300 rounded-md p-2 border"></select>
                </div>
                <div class="flex-1 min-w-[200px]">
                    <label class="block text-sm font-medium text-gray-700">Valor</label>
                    <input type="text" id="manualValueInput" class="mt-1 block w-full border-gray-300 rounded-md p-2 border" placeholder="Ingrese valor">
                    <div class="text-xs mt-1" id="manualRiskPreview"></div>
                </div>
                <div>
                    <button id="sendManualBtn" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded shadow">
                        <i class="fas fa-paper-plane"></i> Enviar
                    </button>
                </div>
            </div>
            <div id="manualMessage" class="mt-2 text-sm text-gray-600"></div>
            <div id="sensorTypeIndicator" class="mt-2 text-sm font-semibold"></div>
        </div>

        <!-- Tarjetas de sensores -->
        <div class="section-bomba"><h2 class="text-2xl font-bold text-blue-700 mb-3">🛢️ Sensores de Bomba y Eléctricos</h2><div id="bombaCards" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mb-8"></div></div>
        <div class="section-ascensor"><h2 class="text-2xl font-bold text-purple-700 mb-3">🛗 Sensores de Ascensor y Motor</h2><div id="ascensorCards" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mb-8"></div></div>

        <!-- Gráficos de barras -->
        <h2 class="text-2xl font-semibold mt-4 mb-2">📊 Evolución (últimas 20 lecturas)</h2>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="chart-container"><h3 class="text-lg font-semibold mb-2">🌡️ Temperatura · Presión · Vibración</h3><canvas id="chart1"></canvas></div>
            <div class="chart-container"><h3 class="text-lg font-semibold mb-2">💧 Caudal · Carga · Velocidad</h3><canvas id="chart2"></canvas></div>
            <div class="chart-container"><h3 class="text-lg font-semibold mb-2">📊 Nivel de Tanque · Energía</h3><canvas id="chart3"></canvas></div>
            <div class="chart-container"><h3 class="text-lg font-semibold mb-2">⚡ Voltaje · Corriente</h3><canvas id="chart4"></canvas></div>
        </div>

        <!-- Historial y alertas -->
        <h2 class="text-2xl font-semibold mt-6 mb-2">📜 Historial Completo</h2>
        <div class="bg-white rounded-xl shadow overflow-hidden mb-6"><div class="scroll-table"><table class="min-w-full"><thead class="bg-gray-50"><tr><th class="p-2">Timestamp</th><th>Tipo</th><th>Variable</th><th>Valor</th><th>Riesgo</th></tr></thead><tbody id="historyBody"><tr><td colspan="5" class="text-center p-4">Cargando...</td></tr></tbody></table></div></div>

        <h2 class="text-2xl font-semibold mt-4 mb-2">🔔 Alertas Recientes</h2>
        <div class="bg-white rounded-xl shadow overflow-hidden mb-6"><div class="scroll-table"><table class="min-w-full"><thead class="bg-gray-50"><tr><th class="p-2">Timestamp</th><th>Variable</th><th>Valor</th><th>Riesgo</th><th>Mensaje</th></tr></thead><tbody id="alertTableBody"><tr><td colspan="5" class="text-center p-4">No hay alertas</td></tr></tbody></table></div></div>

        <!-- Umbrales -->
        <h2 class="text-2xl font-semibold mt-4 mb-2">⚙️ Umbrales de Riesgo</h2>
        <div class="bg-white p-5 rounded-xl shadow mb-6"><div id="thresholdsPanel" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div><div class="mt-4"><button id="saveThresholdsBtn" class="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded shadow">Guardar Umbrales</button><span id="saveMessage" class="ml-2 text-sm text-green-600"></span></div></div>
    </div>

    <script>
        let socket = io();
        let chart1, chart2, chart3, chart4;
        let currentThresholds = {};
        let subscribers = {};
        const NO_RISK_VARS = ['position','door_status','motor_stuck'];
        const BOMBA_VARS = ['flow_rate','pressure','temperature','vibration','tank_level','voltage','current'];
        const ASCENSOR_VARS = ['position','speed','load','trip_count','door_status','energy','motor_stuck'];

        function getUnit(v){ return {flow_rate:'L/s',pressure:'bar',temperature:'°C',vibration:'mm/s',tank_level:'%',position:'piso',speed:'m/s',load:'kg',trip_count:'viajes',door_status:'',energy:'kW',voltage:'V',current:'A'}[v]||''; }
        function getRiskInfo(varName,value){
            if(NO_RISK_VARS.includes(varName)) return {risk:varName==='motor_stuck'&&value?'Crítico':'Bajo', bgClass:varName==='motor_stuck'&&value?'risk-red':'risk-green', borderClass:varName==='motor_stuck'&&value?'border-red-500':'border-green-500'};
            let cfg=currentThresholds[varName]; if(!cfg) return {risk:'Desconocido',bgClass:'risk-gray',borderClass:'border-gray-500'};
            let risk='Bajo',color='green';
            if(cfg.direction==='range'){
                if(value>=cfg.low&&value<=cfg.high){risk='Bajo';color='green';}else{risk='Alto';color='orange';}
            }else{
                let d=cfg.direction, low=cfg.low, med=cfg.medium, high=cfg.high;
                if(d==='higher'){ if(value<=low){risk='Bajo';color='green';}else if(value<=med){risk='Medio';color='yellow';}else if(value<=high){risk='Alto';color='orange';}else{risk='Crítico';color='red';} }
                else{ if(value>=low){risk='Bajo';color='green';}else if(value>=med){risk='Medio';color='yellow';}else if(value>=high){risk='Alto';color='orange';}else{risk='Crítico';color='red';} }
            }
            return {risk, bgClass:`risk-${color}`, borderClass:`border-${color==='green'?'green-500':color==='yellow'?'yellow-500':color==='orange'?'orange-500':'red-500'}`};
        }
        function updateCards(data){
            let b=document.getElementById('bombaCards'), a=document.getElementById('ascensorCards');
            b.innerHTML=''; a.innerHTML='';
            for(let [k,v] of Object.entries(data)){
                let ri=getRiskInfo(k,v);
                let dn=k.replace(/_/g,' ').toUpperCase(); if(k==='motor_stuck') dn='MOTOR PEGADO';
                let card=document.createElement('div'); card.className=`card bg-white rounded-lg shadow p-4 border-l-8 ${ri.borderClass}`;
                card.innerHTML=`<div class="flex justify-between items-start"><div><h3 class="font-bold text-gray-700">${dn}</h3><p class="text-2xl font-bold">${v} ${getUnit(k)}</p></div><span class="px-2 py-1 rounded text-xs font-semibold ${ri.bgClass}">${ri.risk}</span></div>`;
                if(BOMBA_VARS.includes(k)) b.appendChild(card);
                else if(ASCENSOR_VARS.includes(k)) a.appendChild(card);
            }
        }
        function updateHistoryTable(hist){
            let tbody=document.getElementById('historyBody'); tbody.innerHTML='';
            if(hist.length===0){ tbody.innerHTML='<tr><td colspan="5" class="text-center p-4">No hay registros</td></tr>'; return; }
            for(let i=hist.length-1;i>=0;i--){
                let r=hist[i]; let rc=r.risk==='Bajo'?'text-green-600':(r.risk==='Medio'?'text-yellow-600':(r.risk==='Alto'?'text-orange-600':'text-red-600'));
                let tr=document.createElement('tr'); tr.innerHTML=`<td class="p-2">${r.timestamp}</td><td class="p-2">${r.type}</td><td class="p-2">${r.variable}</td><td class="p-2">${r.value}</td><td class="p-2 ${rc} font-semibold">${r.risk}</td>`;
                tbody.appendChild(tr);
            }
        }
        function updateAlertTable(alerts){
            let tbody=document.getElementById('alertTableBody'); tbody.innerHTML='';
            if(!alerts||alerts.length===0){ tbody.innerHTML='<tr><td colspan="5" class="text-center p-4">No hay alertas</td></tr>'; return; }
            for(let a of alerts){
                let rc=(a.risk==='Crítico')?'alert-row-critical':(a.risk==='Alto'?'alert-row-high':'');
                let tr=document.createElement('tr'); tr.className=rc;
                tr.innerHTML=`<td class="p-2">${a.timestamp}</td><td class="p-2">${a.variable}</td><td class="p-2">${a.value}</td><td class="p-2 font-semibold">${a.risk}</td><td class="p-2">${a.message}</td>`;
                tbody.appendChild(tr);
            }
        }
        function initCharts(){
            const optionsBase = { responsive: true, plugins: { legend: { position: 'top' }, tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.raw}` } } } };
            const ctx1 = document.getElementById('chart1').getContext('2d');
            chart1 = new Chart(ctx1, { type: 'bar', data: { labels: [], datasets: [
                { label: 'Temperatura (°C)', backgroundColor: '#e63946', data: [], borderRadius: 4 },
                { label: 'Presión (bar)', backgroundColor: '#1e6091', data: [], borderRadius: 4 },
                { label: 'Vibración (mm/s)', backgroundColor: '#f4a261', data: [], borderRadius: 4 }
            ]}, options: optionsBase });
            const ctx2 = document.getElementById('chart2').getContext('2d');
            chart2 = new Chart(ctx2, { type: 'bar', data: { labels: [], datasets: [
                { label: 'Caudal (L/s)', backgroundColor: '#2d6a4f', data: [], borderRadius: 4 },
                { label: 'Carga (kg)', backgroundColor: '#9c27b0', data: [], borderRadius: 4 },
                { label: 'Velocidad (m/s)', backgroundColor: '#ff6d00', data: [], borderRadius: 4 }
            ]}, options: optionsBase });
            const ctx3 = document.getElementById('chart3').getContext('2d');
            chart3 = new Chart(ctx3, { type: 'bar', data: { labels: [], datasets: [
                { label: 'Nivel tanque (%)', backgroundColor: '#0077b6', data: [], borderRadius: 4 },
                { label: 'Energía (kW)', backgroundColor: '#d62828', data: [], borderRadius: 4 }
            ]}, options: optionsBase });
            const ctx4 = document.getElementById('chart4').getContext('2d');
            chart4 = new Chart(ctx4, { type: 'bar', data: { labels: [], datasets: [
                { label: 'Voltaje (V)', backgroundColor: '#ffb703', data: [], borderRadius: 4 },
                { label: 'Corriente (A)', backgroundColor: '#fb8500', data: [], borderRadius: 4 }
            ]}, options: optionsBase });
        }
        function updateCharts(hist){
            let last20 = hist.slice(-20);
            let temp = last20.filter(r=>r.variable==='temperature').map(r=>r.value);
            let pres = last20.filter(r=>r.variable==='pressure').map(r=>r.value);
            let vib = last20.filter(r=>r.variable==='vibration').map(r=>r.value);
            let flow = last20.filter(r=>r.variable==='flow_rate').map(r=>r.value);
            let load = last20.filter(r=>r.variable==='load').map(r=>r.value);
            let speed = last20.filter(r=>r.variable==='speed').map(r=>r.value);
            let tank = last20.filter(r=>r.variable==='tank_level').map(r=>r.value);
            let energy = last20.filter(r=>r.variable==='energy').map(r=>r.value);
            let volt = last20.filter(r=>r.variable==='voltage').map(r=>r.value);
            let curr = last20.filter(r=>r.variable==='current').map(r=>r.value);
            let labels = temp.map((_,i)=>i+1);
            chart1.data.labels = labels; chart1.data.datasets[0].data = temp; chart1.data.datasets[1].data = pres; chart1.data.datasets[2].data = vib; chart1.update();
            chart2.data.labels = labels; chart2.data.datasets[0].data = flow; chart2.data.datasets[1].data = load; chart2.data.datasets[2].data = speed; chart2.update();
            chart3.data.labels = labels; chart3.data.datasets[0].data = tank; chart3.data.datasets[1].data = energy; chart3.update();
            chart4.data.labels = labels; chart4.data.datasets[0].data = volt; chart4.data.datasets[1].data = curr; chart4.update();
        }
        function updateStatsAndRecs(stats,recs,attempts){
            let statsDiv=document.getElementById('statsPanel');
            if(stats&&Object.keys(stats).length){
                let html='<div class="grid grid-cols-2 gap-2">';
                for(let [k,v] of Object.entries(stats)) html+=`<div><strong>${k.replace('_',' ').toUpperCase()}</strong><br>Prom: ${v.avg.toFixed(1)} | Min: ${v.min} | Max: ${v.max}</div>`;
                html+='</div>'; statsDiv.innerHTML=html;
            }else statsDiv.innerHTML='<p>No hay datos.</p>';
            let recDiv=document.getElementById('recommendationsPanel');
            if(recs&&recs.length) recDiv.innerHTML='<ul class="list-disc pl-5">'+recs.map(r=>`<li>${r}</li>`).join('')+'</ul>';
            else recDiv.innerHTML='<p>No hay recomendaciones.</p>';
            let attemptsDiv=document.getElementById('doorAttemptsInfo');
            if(typeof attempts==='number' && attempts>0){
                attemptsDiv.innerHTML=`<span class="font-semibold">Intentos de cierre de puertas:</span> ${attempts}`;
            } else {
                attemptsDiv.innerHTML='';
            }
        }
        function renderThresholdsPanel(th){
            let panel=document.getElementById('thresholdsPanel'); panel.innerHTML='';
            for(let [k,cfg] of Object.entries(th)){
                if(NO_RISK_VARS.includes(k)) continue;
                let div=document.createElement('div'); div.className='border p-2 rounded';
                if(cfg.direction==='range'){
                    div.innerHTML=`<label class="font-semibold block mb-1">${k.replace(/_/g,' ').toUpperCase()} (rango)</label><div class="grid grid-cols-2 gap-2 text-sm"><div>Mín: <input type="number" step="any" class="border rounded w-full p-1" data-var="${k}" data-level="low" value="${cfg.low}"></div><div>Máx: <input type="number" step="any" class="border rounded w-full p-1" data-var="${k}" data-level="high" value="${cfg.high}"></div></div><input type="hidden" data-var="${k}" data-level="direction" value="range">`;
                }else{
                    div.innerHTML=`<label class="font-semibold block mb-1">${k.replace(/_/g,' ').toUpperCase()}</label><div class="grid grid-cols-3 gap-2 text-sm"><div>Bajo: <input type="number" step="any" class="border rounded w-full p-1" data-var="${k}" data-level="low" value="${cfg.low}"></div><div>Medio: <input type="number" step="any" class="border rounded w-full p-1" data-var="${k}" data-level="medium" value="${cfg.medium}"></div><div>Alto: <input type="number" step="any" class="border rounded w-full p-1" data-var="${k}" data-level="high" value="${cfg.high}"></div></div><input type="hidden" data-var="${k}" data-level="direction" value="${cfg.direction}">`;
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
            if(res.status==='ok'){ document.getElementById('saveMessage').innerText='✓ Guardados'; setTimeout(()=>document.getElementById('saveMessage').innerText='',2000); currentThresholds=res.thresholds; }
        }
        async function toggleAlerts(){
            let btn=document.getElementById('toggleAlertsBtn');
            let currentlyEnabled=!btn.innerText.includes('Desactivar');
            let resp=await fetch('/toggle_alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!currentlyEnabled})});
            let data=await resp.json();
            if(data.status==='ok') btn.innerHTML=data.alert_enabled?'<i class="fas fa-bell"></i> Desactivar Alertas':'<i class="fas fa-bell-slash"></i> Activar Alertas';
        }
        async function clearHistory(){ if(confirm('¿Limpiar historial?')){ let resp=await fetch('/clear_history',{method:'POST'}); if(resp.ok) alert('Historial limpiado'); else alert('Error'); } }
        function populateManualSensorSelect(){
            let sel=document.getElementById('manualSensorSelect'); sel.innerHTML='';
            [...BOMBA_VARS,...ASCENSOR_VARS].forEach(v=>{let opt=document.createElement('option'); opt.value=v; opt.textContent=(BOMBA_VARS.includes(v)?'🛢️':'🛗')+' '+v.replace(/_/g,' ').toUpperCase(); sel.appendChild(opt);});
        }
        function updateSensorTypeIndicator(){
            let v=document.getElementById('manualSensorSelect').value;
            document.getElementById('sensorTypeIndicator').innerHTML=BOMBA_VARS.includes(v)?'<span class="text-blue-600"><i class="fas fa-oil-can"></i> Bomba/Eléctrico</span>':'<span class="text-purple-600"><i class="fas fa-arrow-up"></i> Ascensor/Motor</span>';
        }
        function updateManualRiskPreview(){
            let v=document.getElementById('manualSensorSelect').value;
            let raw=document.getElementById('manualValueInput').value;
            let span=document.getElementById('manualRiskPreview');
            if(raw===''){span.innerHTML='';return;}
            let val=raw;
            if(v==='door_status'){}
            else if(v==='motor_stuck') val=(raw==='true'||raw==='1');
            else{let n=parseFloat(raw); if(isNaN(n)){span.innerHTML='<span class="text-red-600">Inválido</span>';return;} val=n;}
            let ri=getRiskInfo(v,val);
            span.innerHTML=`Riesgo estimado: <span class="font-bold ${ri.bgClass} px-2 py-0.5 rounded">${ri.risk}</span>`;
        }
        async function sendManualValue(){
            let v=document.getElementById('manualSensorSelect').value;
            let raw=document.getElementById('manualValueInput').value;
            if(raw===''){document.getElementById('manualMessage').innerHTML='<span class="text-red-600">Ingrese un valor</span>';return;}
            let val=raw;
            if(v==='door_status'){val=raw.toLowerCase(); if(!['open','closed'].includes(val)){document.getElementById('manualMessage').innerHTML='<span class="text-red-600">door_status debe ser "open" o "closed"</span>';return;}}
            else if(v==='motor_stuck') val=(raw==='true'||raw==='1');
            else{let n=parseFloat(raw); if(isNaN(n)){document.getElementById('manualMessage').innerHTML='<span class="text-red-600">Valor numérico inválido</span>';return;} val=n;}
            try{
                let resp=await fetch('/manual_update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({variable:v,value:val})});
                let res=await resp.json();
                if(res.status==='ok'){document.getElementById('manualMessage').innerHTML=`<span class="text-green-600">✓ ${v} = ${res.value} (${res.risk})</span>`; setTimeout(()=>document.getElementById('manualMessage').innerHTML='',3000);}
                else{document.getElementById('manualMessage').innerHTML=`<span class="text-red-600">Error: ${res.message}</span>`;}
            }catch(e){document.getElementById('manualMessage').innerHTML='<span class="text-red-600">Error de conexión</span>';}
            document.getElementById('manualValueInput').focus(); document.getElementById('manualValueInput').select();
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
                    let a=document.createElement('a'); a.href=url; a.download=`reporte_${period}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.pdf`;
                    document.body.appendChild(a); a.click(); URL.revokeObjectURL(url); a.remove();
                }else{
                    let err=await resp.text();
                    try{ let e=JSON.parse(err); alert('Error: '+e.message); }catch(e){ alert('Error: '+err); }
                }
            }catch(e){ alert('Error de conexión'); }
            finally{ btn.disabled=false; btn.innerHTML='<i class="fas fa-file-pdf"></i> Generar PDF'; }
        }
        function updateSubscribersList(){
            let container=document.getElementById('subscribersList');
            if(!subscribers) return;
            let html='<table class="min-w-full text-xs"><thead><tr><th>Canal</th><th>Nivel</th><th>Contacto</th><th></th><th></th></tr></thead><tbody>';
            for(let ch of ['email','whatsapp','telegram']){
                for(let lv of ['Bajo','Medio','Alto','Crítico']){
                    subscribers[ch][lv].forEach(ct=>{
                        html+=`<tr><td>${ch}</td><td>${lv}</td><td>${ct}</td><td><button class="test-subscriber text-blue-600 mr-2" data-channel="${ch}" data-level="${lv}" data-contact="${ct}">Probar</button></td><td><button class="remove-subscriber text-red-600" data-channel="${ch}" data-level="${lv}" data-contact="${ct}">Eliminar</button></td></tr>`;
                    });
                }
            }
            html+='</tbody></table>';
            container.innerHTML=html;
            document.querySelectorAll('.remove-subscriber').forEach(btn=>{
                btn.addEventListener('click',async ()=>{
                    let ch=btn.dataset.channel, lv=btn.dataset.level, ct=btn.dataset.contact;
                    let resp=await fetch('/remove_subscriber',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel:ch,risk_level:lv,contact:ct})});
                    if(resp.ok){
                        let subsResp=await fetch('/get_subscribers');
                        subscribers=await subsResp.json();
                        updateSubscribersList();
                    }else alert('Error');
                });
            });
            document.querySelectorAll('.test-subscriber').forEach(btn=>{
                btn.addEventListener('click',async ()=>{
                    let ch=btn.dataset.channel, lv=btn.dataset.level, ct=btn.dataset.contact;
                    let resp=await fetch(`/test_alert/${ch}/${lv}/${ct}`);
                    let msg=await resp.text();
                    alert(msg);
                });
            });
        }
        document.getElementById('addSubscriberBtn').addEventListener('click',async()=>{
            let ch=document.getElementById('subChannel').value, lv=document.getElementById('subRiskLevel').value, ct=document.getElementById('subContact').value.trim();
            if(!ct) return;
            let resp=await fetch('/add_subscriber',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({channel:ch,risk_level:lv,contact:ct})});
            let data=await resp.json();
            if(data.status==='ok'){ subscribers=data.subscribers; updateSubscribersList(); document.getElementById('subContact').value=''; }
            else alert(data.message);
        });
        socket.on('connect',()=>console.log('Conectado'));
        socket.on('init_data',(data)=>{
            currentThresholds=data.thresholds; subscribers=data.subscribers;
            renderThresholdsPanel(currentThresholds); updateCards(data.current);
            updateHistoryTable(data.history); updateCharts(data.history); updateAlertTable(data.alert_log);
            updateStatsAndRecs(data.stats,data.recommendations,data.door_close_attempts);
            document.getElementById('toggleAlertsBtn').innerHTML=data.alert_enabled?'<i class="fas fa-bell"></i> Desactivar Alertas':'<i class="fas fa-bell-slash"></i> Activar Alertas';
            if(data.rationing) document.getElementById('rationingIndicator').classList.remove('hidden'); else document.getElementById('rationingIndicator').classList.add('hidden');
            document.getElementById('protectionStatus').innerText = data.protection_active ? 'ON' : 'OFF';
            document.getElementById('pumpStatus').innerText = data.pump_on ? 'ON' : 'OFF';
            document.getElementById('elevatorStatus').innerText = data.elevator_on ? 'ON' : 'OFF';
            document.getElementById('lastUpdate').innerText=new Date().toLocaleTimeString();
            populateManualSensorSelect(); updateSensorTypeIndicator(); updateSubscribersList();
            // Diagnóstico de credenciales
            const hasSMTP = !!(data.smtp_user);
            const hasTelegram = !!(data.telegram_token);
            const hasTwilio = !!(data.twilio_sid);
            if(!hasSMTP && !hasTelegram && !hasTwilio){
                document.getElementById('credsWarning').classList.remove('hidden');
                document.getElementById('credsMsg').innerText = 'No se han configurado credenciales para enviar alertas reales. Los mensajes solo se simularán en la consola. Para envíos reales, defina las variables de entorno SMTP_USER, SMTP_PASSWORD, TELEGRAM_BOT_TOKEN, etc.';
            }
        });
        socket.on('sensor_update',(data)=>{
            currentThresholds=data.thresholds;
            updateCards(data.current); updateHistoryTable(data.history); updateCharts(data.history);
            updateAlertTable(data.alert_log); updateStatsAndRecs(data.stats,data.recommendations,data.door_close_attempts);
            document.getElementById('lastUpdate').innerText=new Date().toLocaleTimeString();
            if(data.rationing) document.getElementById('rationingIndicator').classList.remove('hidden'); else document.getElementById('rationingIndicator').classList.add('hidden');
            document.getElementById('protectionStatus').innerText = data.protection_active ? 'ON' : 'OFF';
            document.getElementById('pumpStatus').innerText = data.pump_on ? 'ON' : 'OFF';
            document.getElementById('elevatorStatus').innerText = data.elevator_on ? 'ON' : 'OFF';
        });
        document.getElementById('saveThresholdsBtn').addEventListener('click',saveThresholds);
        document.getElementById('toggleAlertsBtn').addEventListener('click',toggleAlerts);
        document.getElementById('clearHistoryBtn').addEventListener('click',clearHistory);
        document.getElementById('manualValueInput').addEventListener('input',updateManualRiskPreview);
        document.getElementById('manualSensorSelect').addEventListener('change',()=>{updateManualRiskPreview(); updateSensorTypeIndicator();});
        document.getElementById('sendManualBtn').addEventListener('click',sendManualValue);
        document.getElementById('generateReportBtn').addEventListener('click',generateReport);
        initCharts();
    </script>
</body>
</html>
"""

# ----------------------------------------------------------------------
# Inicio del servidor
# ----------------------------------------------------------------------
if __name__ == '__main__':
    # Para diagnóstico en el frontend, pasamos información de credenciales
    socketio.start_background_task(generate_data_and_emit)
    webbrowser.open('http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)