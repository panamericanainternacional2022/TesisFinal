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
import logging
import json
from datetime import datetime, timedelta
from io import BytesIO
from collections import deque

from flask import Flask, render_template, request, jsonify, Response
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
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
DJANGO_CONNECTED = False
try:
    import django

    django.setup()
    from django.utils import timezone
    from front.models import Notificacion, EquipoMonitoreo, Edificio, Usuario, UsuarioEdificio

    DJANGO_CONNECTED = True
    logger.info("Django integrado correctamente en app27.py")
except Exception as e:
    logger.warning("No se pudo inicializar Django desde app27.py: %s", e)

# ----------------------------------------------------------------------
# Configuración centralizada de sensores (fuente única de verdad)
# ----------------------------------------------------------------------
from front.sensor_config import (
    VAR_NAMES,
    UNITS,
    DEVICE_NAMES_ES,
    RISK_NAMES_ES,
    STATS_VARS,
    PDF_STATS_VARS,
    PDF_BAR_VARS,
    PDF_BAR_LABELS,
    PUMP_VARS,
    ELEVATOR_VARS,
    NO_RISK_VARS,
)

# Apuntar dicts legacy a la fuente única de verdad
_VAR_ES = VAR_NAMES
_DEVICE_ES = DEVICE_NAMES_ES

# ----------------------------------------------------------------------
# Estado del simulador (importado desde simulation.py)
# ----------------------------------------------------------------------
from simulation import (
    RATIONING_THRESHOLD, MAX_HISTORY_SIZE, MAX_LOG_ENTRIES,
    PROTECTION_HOLD_SECONDS, LOG_SIM, SIMULTANEOUS_FAIL_PROB,
    DOOR_CLOSE_SUCCESS_PROB, DOOR_OPEN_PROB, MAX_DOOR_CLOSE_ATTEMPTS,
    DEFAULT_SENSOR_DATA, BuildingSimulator, simulators,
    sensor_data, pump_on, elevator_on, equipment_types, protection_ends, active_alerts,
    door_close_attempts, history, alert_log, pending_notifications,
    last_email_sent_time,
    reset_critical_values, check_motor_stuck, update_sensor_data,
)

from alerts import (
    get_building_emails, send_email_alert, send_alert,
    get_professional_action, check_rationing, generate_recommendations,
    enter_protection_mode, update_protection_state,
    persist_notification_in_django,
    _es_var, _es_device, get_unit, subscribers,
)

# ----------------------------------------------------------------------
# Payload y estructura de datos para streaming en vivo
# ----------------------------------------------------------------------


def titleize_name(text):
    return " ".join(word.capitalize() for word in text.replace("_", " ").split())


def build_live_payload():
    stats = {}
    for var in STATS_VARS:
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

    # Solo incluir variables de los tipos de equipo que existen en este edificio
    _relevant_vars = set()
    if "bomba" in equipment_types:
        _relevant_vars.update(PUMP_VARS)
    if "elevador" in equipment_types:
        _relevant_vars.update(ELEVATOR_VARS)
    # Siempre incluir variables de sistema (rationing, protección, etc.)
    _relevant_vars.update(["rationing", "auto_protection", "protection_pump", "protection_elevator"])

    sensors = []
    for var, value in sensor_data.items():
        if var not in _relevant_vars:
            continue
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
        "current": {k: v for k, v in sensor_data.items() if k in _relevant_vars},
        "sensors": sensors,
        "history": [h for h in history[-200:] if h.get("variable") in _relevant_vars],
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
        "equipment_types": list(equipment_types),
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

active_edificio_id = None

# subscribers, get_building_emails movidos a alerts.py

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
# NO_RISK_VARS importado desde sensor_config
thresholds = DEFAULT_THRESHOLDS.copy()
alert_enabled = True
PROTECTION_TOGGLE_INTERVAL = 8
SIMULATION_NORMAL_DURATION = 10
protection_active = False
last_protection_toggle = time.time()
protection_end = 0
protection_targets = set()


# ----------------------------------------------------------------------
# Funciones auxiliares
# ----------------------------------------------------------------------
# get_unit, generate_recommendations, send_email_alert, persist_notification_in_django,
# _es_device, _es_var, enter_protection_mode, update_protection_state,
# get_professional_action, send_alert, check_rationing -> alerts.py


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


# get_unit, generate_recommendations, send_email_alert,
# persist_notification_in_django, _es_device, _es_var,
# enter_protection_mode, update_protection_state,
# get_professional_action, send_alert, check_rationing
# --> movidos a alerts.py


def _run_sim_tick(sim: BuildingSimulator):
    """Ejecuta un ciclo de simulación completo para un edificio.

    Intercambia los globales de Python para que apunten al estado
    del simulador dado, ejecuta las funciones existentes sin modificarlas,
    y restaura los escalares mutados de vuelta al objeto sim.
    Los dicts (sensor_data, protection_ends, active_alerts) son mutados
    in-place por las funciones, por lo que no necesitan copia de vuelta.
    """
    global sensor_data, pump_on, elevator_on, equipment_types, protection_ends, active_alerts
    global door_close_attempts, history, alert_log, pending_notifications
    global last_email_sent_time, active_edificio_id

    # Guardar active_edificio_id original
    _saved_active = active_edificio_id

    # Apuntar globales al estado de este simulador
    active_edificio_id       = sim.edificio_id
    sensor_data              = sim.sensor_data
    pump_on                  = sim.pump_on
    elevator_on              = sim.elevator_on
    equipment_types          = sim.equipment_types
    protection_ends          = sim.protection_ends
    active_alerts            = sim.active_alerts
    door_close_attempts      = sim.door_close_attempts
    history                  = sim.history
    alert_log                = sim.alert_log
    pending_notifications    = sim.pending_notifications
    last_email_sent_time     = sim.last_email_sent_time

    # Sincronizar también los globales del módulo simulation.py
    # (update_sensor_data, reset_critical_values y check_motor_stuck
    #  están en simulation.py y usan sus propios globales)
    import simulation as _sim_mod
    _sim_mod.sensor_data           = sim.sensor_data
    _sim_mod.pump_on               = sim.pump_on
    _sim_mod.elevator_on           = sim.elevator_on
    _sim_mod.equipment_types       = sim.equipment_types
    _sim_mod.protection_ends       = sim.protection_ends
    _sim_mod.active_alerts         = sim.active_alerts
    _sim_mod.door_close_attempts   = sim.door_close_attempts
    _sim_mod.history               = sim.history
    _sim_mod.alert_log             = sim.alert_log
    _sim_mod.pending_notifications = sim.pending_notifications
    _sim_mod.last_email_sent_time  = sim.last_email_sent_time

    # Ejecutar lógica de simulación (usan los globales)
    update_protection_state()
    update_sensor_data()

    # Solo evaluar variables de los tipos de equipo que existen en este edificio
    _alert_vars = set()
    if "bomba" in equipment_types:
        _alert_vars.update(PUMP_VARS)
    if "elevador" in equipment_types:
        _alert_vars.update(ELEVATOR_VARS)
    _alert_vars.add("motor_stuck")  # siempre evaluar

    # Verificar alertas y persistir en DB
    for var, value in sensor_data.items():
        if var not in _alert_vars:
            continue
        if var == "motor_stuck":
            if value:
                action = get_professional_action(var, "Crítico", value)
                send_alert(var, value, "Crítico", action)
            else:
                active_alerts.pop(var, None)
            continue
        risk, _ = classify_risk(var, value)
        if risk in ("Alto", "Crítico"):
            action = get_professional_action(var, risk, value)
            send_alert(var, value, risk, action)
        elif risk in ("Bajo", "Medio"):
            # Guardar en historial sin disparar protección ni email
            action = get_professional_action(var, risk, value)
            send_alert(var, value, risk, action)
        else:
            active_alerts.pop(var, None)
    check_rationing(sensor_data["flow_rate"])

    # Agregar lecturas al historial del simulador (solo vars relevantes al edificio)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    for var, value in sensor_data.items():
        if var not in _alert_vars and var not in ("rationing", "auto_protection", "protection_pump", "protection_elevator"):
            continue
        risk, color = (
            classify_risk(var, value) if var != "motor_stuck"
            else ("Crítico" if value else "Bajo", "red" if value else "green")
        )
        sensor_type = "Bomba" if var in PUMP_VARS else "Ascensor"
        new_readings.append({"timestamp": timestamp, "type": sensor_type, "variable": var, "value": value, "risk": risk, "color": color})
    history.extend(new_readings)
    if len(history) > MAX_HISTORY_SIZE:
        sim.history = history[-MAX_HISTORY_SIZE:]
        history = sim.history

    # Copiar de vuelta los escalares que pudieron cambiar
    sim.pump_on               = pump_on
    sim.elevator_on           = elevator_on
    sim.door_close_attempts   = _sim_mod.door_close_attempts  # update_sensor_data modificó simulation.door_close_attempts
    sim.last_email_sent_time  = last_email_sent_time

    # Restaurar active_edificio_id al valor original
    active_edificio_id = _saved_active


def _sync_globals_to_sim(sim: BuildingSimulator):
    """Apunta todos los globales de estado al simulador activo.
    Llamar cada vez que active_edificio_id cambie o al final del loop.
    """
    global sensor_data, pump_on, elevator_on, equipment_types, protection_ends, active_alerts
    global door_close_attempts, history, alert_log, pending_notifications, last_email_sent_time
    sensor_data           = sim.sensor_data
    pump_on               = sim.pump_on
    elevator_on           = sim.elevator_on
    equipment_types       = sim.equipment_types
    protection_ends       = sim.protection_ends
    active_alerts         = sim.active_alerts
    door_close_attempts   = sim.door_close_attempts
    history               = sim.history
    alert_log             = sim.alert_log
    pending_notifications = sim.pending_notifications
    last_email_sent_time  = sim.last_email_sent_time
    # Sincronizar también simulation.py
    import simulation as _sim_mod
    _sim_mod.sensor_data           = sim.sensor_data
    _sim_mod.pump_on               = sim.pump_on
    _sim_mod.elevator_on           = sim.elevator_on
    _sim_mod.equipment_types       = sim.equipment_types
    _sim_mod.protection_ends       = sim.protection_ends
    _sim_mod.active_alerts         = sim.active_alerts
    _sim_mod.door_close_attempts   = sim.door_close_attempts
    _sim_mod.history               = sim.history
    _sim_mod.alert_log             = sim.alert_log
    _sim_mod.pending_notifications = sim.pending_notifications
    _sim_mod.last_email_sent_time  = sim.last_email_sent_time


def generate_data_and_emit():
    while True:
        eventlet.sleep(5)

        # Tickear TODOS los simuladores (independientemente del edificio visible)
        for sim in list(simulators.values()):
            _run_sim_tick(sim)

        # Restaurar globales al simulador activo para que build_live_payload()
        # y las rutas Flask vean los datos del edificio seleccionado
        active_sim = simulators.get(active_edificio_id)
        if active_sim:
            _sync_globals_to_sim(active_sim)

        payload = build_live_payload()
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} LOOP [{active_edificio_id}]: "
                f"pump_on={pump_on} elevator_on={elevator_on} protection_ends={protection_ends} "
                f"edificios_activos={list(simulators.keys())}"
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


def _pdf_safe(text):
    """Normaliza el texto para compatibilidad con la fuente Helvetica de fpdf2
    (latin-1). Elimina tildes y caracteres fuera del rango latin-1."""
    import unicodedata
    return unicodedata.normalize('NFKD', str(text)).encode('latin-1', 'ignore').decode('latin-1')


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
    stats = {}
    for var in PDF_STATS_VARS:
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
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 12, "Reporte de Monitoreo Automatizado", ln=1, align="L")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(95, 95, 95)
    pdf.cell(0, 8, "SISTEMA DE TELEMETRIA Y CONTROL", ln=1, align="L")
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
    present_vars = []
    labels = []
    avgs = []
    for v in PDF_BAR_VARS:
        if v in stats and isinstance(stats[v]["avg"], float):
            present_vars.append(v)
            labels.append(PDF_BAR_LABELS.get(v, v))
            avgs.append(stats[v]["avg"])
    if avgs:
        max_avg = max(avgs)
        x0 = 15
        y0 = pdf.get_y()
        bar_width = 16
        spacing = 4
        max_bar_height = 50
        pdf.set_font("Helvetica", "", 7)
        for i, (var_name, lab, val) in enumerate(zip(present_vars, labels, avgs)):
            x = x0 + i * (bar_width + spacing)
            if x + bar_width > 200:
                break
            height = (val / max_avg) * max_bar_height if max_avg > 0 else 10
            
            # Clasificar riesgo del promedio para determinar el color de la barra
            risk, color_name = classify_risk(var_name, val)
            if color_name == "green":
                fill_color = (22, 101, 52)
            elif color_name == "yellow":
                fill_color = (146, 64, 14)
            elif color_name == "orange":
                fill_color = (194, 65, 12)
            elif color_name == "red":
                fill_color = (153, 27, 27)
            else:
                fill_color = (30, 41, 59)
                
            pdf.set_fill_color(*fill_color)
            pdf.set_draw_color(10, 10, 10)
            pdf.rect(x, y0 + max_bar_height - height, bar_width, height, "FD")
            
            # Valor encima de la barra (usar color de la barra para legibilidad)
            pdf.set_text_color(*fill_color)
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
        pdf.cell(80, 8, _pdf_safe(f"  {_es_var(var)}"), 1, 0, "L")
        pdf.cell(50, 8, _pdf_safe(f"  {val_str}"), 1, 0, "L")
        
        # Celda tipo Badge para riesgo con borde negro
        pdf.set_fill_color(*fill)
        pdf.set_text_color(*text_c)
        pdf.set_draw_color(10, 10, 10)
        pdf.cell(60, 8, _pdf_safe(risk), 1, 1, "C", True)
    pdf.ln(8)
    
    # Forzar salto de página si queda poco espacio
    if pdf.get_y() > 220:
        pdf.add_page()
        
    # Estadísticas
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(0, 8, _pdf_safe(f"ESTADISTICAS DE VARIABLES ({period_name.upper()})"), ln=1)
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
    for var in PDF_STATS_VARS:
        s = stats[var]
        pdf.cell(55, 6, _pdf_safe(f"  {_es_var(var)}"), 1)
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
            val_raw = a.get("value")
            if val_raw is None:
                val_str_pdf = "-"
            elif isinstance(val_raw, bool):
                val_str_pdf = "Si" if val_raw else "No"
            else:
                unit = get_unit(a.get("variable", ""))
                val_str_pdf = f"{val_raw} {unit}".strip() if unit else str(val_raw)
            pdf.cell(50, 6, f"  {a['timestamp']}", 1)
            pdf.cell(50, 6, _pdf_safe(f"  {_es_var(a['variable'])}"), 1)
            pdf.cell(40, 6, _pdf_safe(val_str_pdf), 1, 0, "C")
            pdf.cell(50, 6, _pdf_safe(a["risk"]), 1, 1, "C")
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
    return render_template("monitoreo_dashboard.html",
        no_risk_vars=NO_RISK_VARS,
        bomba_vars=PUMP_VARS,
        ascensor_vars=ELEVATOR_VARS,
        var_names=VAR_NAMES,
        units=UNITS)


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


@app.route("/toggle_alerts", methods=["POST"])
def toggle_alerts():
    """Activa o desactiva la generación de alertas en el simulador Flask.
    El JS de la página de notificaciones llama a este endpoint al mismo tiempo
    que actualiza el estado en la sesión de Django.
    Body JSON esperado: {"enabled": true|false}
    """
    global alert_enabled
    try:
        data = request.get_json(force=True, silent=True) or {}
        alert_enabled = bool(data.get("enabled", True))
        logger.info("alert_enabled cambiado a: %s", alert_enabled)
        return jsonify({"status": "ok", "alert_enabled": alert_enabled})
    except Exception as e:
        logger.error("Error en /toggle_alerts: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/set_active_building/<int:edificio_id>", methods=["POST"])
def api_set_active_building(edificio_id):
    global active_edificio_id
    active_edificio_id = edificio_id
    logger.info(f"Edificio activo cambiado a: {active_edificio_id}")
    # Sincronizar globales al nuevo simulador activo de inmediato
    # para que las rutas Flask reflejen el edificio correcto
    new_sim = simulators.get(edificio_id)
    if new_sim:
        _sync_globals_to_sim(new_sim)
        logger.info(f"Globales sincronizados al simulador: {new_sim}")
    else:
        logger.warning(f"No existe simulador para edificio_id={edificio_id}. Se creará en el próximo ciclo si existe en la BD.")
    return jsonify({"status": "ok", "active_edificio_id": active_edificio_id, "simuladores": list(simulators.keys())})


@app.route("/api/edificios", methods=["GET"])
def api_edificios():
    if not DJANGO_CONNECTED:
        return jsonify([{"id": 1, "nombre": "Edificio Simulado (Sin DB)"}])
    try:
        edificios = Edificio.objects.all().order_by("nb_edificio")
        return jsonify([{
            "id": e.id_edificio,
            "nombre": e.nb_edificio or f"Edificio #{e.id_edificio}",
            "equipos": [{"tipo": eq.tipo, "nombre": eq.nb_equipo} for eq in e.equipomonitoreo_set.all()],
        } for e in edificios])
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
            args=(risk_level, "Reporte de Edificio ", message, pdf_io, "reporte.pdf", [email]),
            daemon=True
        ).start()
    except Exception as e:
        logger.error(f"Error generando o enviando PDF a {email}: {e}")
        threading.Thread(
            target=send_email_alert,
            args=(risk_level, "Reporte de Edificio ", message + f"\n\n(No se pudo adjuntar el reporte: {e})", None, "reporte.pdf", [email]),
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
            args=(risk_level, "Reporte de Edificio (Masivo) ", message, pdf_io, "reporte.pdf", emails),
            daemon=True
        ).start()
    except Exception as e:
        logger.error(f"Error generando o enviando PDF masivo: {e}")
        threading.Thread(
            target=send_email_alert,
            args=(risk_level, "Reporte de Edificio (Masivo) ", message + f"\n\n(No se pudo adjuntar el reporte: {e})", None, "reporte.pdf", emails),
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
    sensor_type = "Bomba" if variable in PUMP_VARS else "Ascensor"
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
    for var in STATS_VARS:
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



@socketio.on("connect")
def handle_connect():
    payload = build_live_payload()
    emit("init_data", payload)


# ----------------------------------------------------------------------
# Plantilla HTML completa (con gráficos de barras y diagnóstico)
# ----------------------------------------------------------------------
HTML_TEMPLATE = """
"""
# ----------------------------------------------------------------------
# Inicio del servidor
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # --------------------------------------------------------------
    # Crear un BuildingSimulator por cada EquipoMonitoreo en la BD.
    # Si no hay conexión Django, se crea un simulador dummy.
    # --------------------------------------------------------------
    if DJANGO_CONNECTED:
        try:
            _equipos = EquipoMonitoreo.objects.select_related("id_edificio").all()
            for _eq in _equipos:
                if _eq.id_edificio:
                    _eid  = _eq.id_edificio.id_edificio
                    _enombre = _eq.id_edificio.nb_edificio or f"Edificio #{_eid}"
                    if _eid not in simulators:
                        simulators[_eid] = BuildingSimulator(_eid, _enombre)
                        logger.info(f"Simulador creado: {simulators[_eid]}")
                    # Acumular tipos de equipo para este edificio
                    simulators[_eid].equipment_types.add(_eq.tipo)
                    simulators[_eid].has_pump = "bomba" in simulators[_eid].equipment_types
                    simulators[_eid].has_elevator = "elevador" in simulators[_eid].equipment_types
                    simulators[_eid].pump_on = simulators[_eid].has_pump
                    simulators[_eid].elevator_on = simulators[_eid].has_elevator
            if simulators:
                # Establecer active_edificio_id al primer edificio en orden
                active_edificio_id = min(simulators.keys())
                _sync_globals_to_sim(simulators[active_edificio_id])
                logger.info(f"Edificio activo inicial: {active_edificio_id} | Todos los simuladores: {list(simulators.keys())}")
            else:
                logger.warning("No se encontraron EquipoMonitoreo en la BD. Se usará simulador dummy.")
        except Exception as _e:
            logger.warning(f"No se pudieron crear simuladores desde la BD: {_e}")

    # Sin BD: crear simulador dummy para no romper el loop de desarrollo
    if not simulators and not DJANGO_CONNECTED:
        _dummy = BuildingSimulator(1, "Edificio Simulado", equipment_types={"bomba", "elevador"})
        simulators[1] = _dummy
        active_edificio_id = 1
        _sync_globals_to_sim(_dummy)
        logger.info("Simulador dummy creado (sin conexión a BD).")
    elif not simulators:
        logger.warning("No hay EquipoMonitoreo en la BD. El loop de simulación está inactivo.")

    # Lanzar el loop de simulación en background
    socketio.start_background_task(generate_data_and_emit)
    # webbrowser.open("http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
