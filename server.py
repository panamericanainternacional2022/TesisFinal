#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ruff: noqa: E402
"""
Punto de entrada único del sistema PCLogo.
Reemplaza entry.py + routes.py (Flask) y manage.py runserver.
Ejecutar: python server.py

Arquitectura unificada: Django + eventlet WSGI en un solo proceso.
- Servidor HTTP: eventlet.wsgi.server con Django WSGIHandler
- Simulación: green thread en background
- SSE: StreamingHttpResponse desde Django (time.sleep → eventlet)
"""

import eventlet
eventlet.monkey_patch()
import eventlet.wsgi
try:
    import eventlet.support.psycopg2_patcher
    eventlet.support.psycopg2_patcher.make_psycopg_green()
except ImportError:
    pass

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Cargar .env ANTES de django.setup() ──────────────────────────
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, val = line.strip().split("=", 1)
                os.environ[key.strip()] = val.strip().strip("'\"")
    logger.info(".env cargado antes de Django setup")

# ─── Django setup ─────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

# ─── Crear simuladores desde la BD ────────────────────────────────
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.engine import generate_data_and_emit
from apps.buildings.models import MonitoringEquipment

equipos = MonitoringEquipment.objects.select_related("building").all()
for eq in equipos:
    if not eq.building:
        continue
    eid = eq.building.id
    enombre = eq.building.name or f"Edificio #{eid}"
    if eid not in simulators:
        simulators[eid] = BuildingSimulator(eid, enombre)
    simulators[eid].equipment_types.add(eq.equipment_type)
    simulators[eid].has_pump = "bomba" in simulators[eid].equipment_types
    simulators[eid].has_elevator = "elevador" in simulators[eid].equipment_types
    simulators[eid].pump_on = simulators[eid].has_pump
    simulators[eid].elevator_on = simulators[eid].has_elevator
    logger.info("Simulador creado: edificio=%s tipo=%s", eid, eq.equipment_type)

if not simulators:
    from apps.buildings.models import Building as BuildingModel
    dummy_edificio, _ = BuildingModel.objects.get_or_create(
        rif="J-00000000-0",
        defaults={"name": "Edificio Simulado", "address": "Dirección simulada"},
    )
    MonitoringEquipment.objects.get_or_create(
        building=dummy_edificio, equipment_type=MonitoringEquipment.TYPE_PUMP,
        defaults={"name": f"Bomba de agua - {dummy_edificio.name}"},
    )
    MonitoringEquipment.objects.get_or_create(
        building=dummy_edificio, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
        defaults={"name": f"Elevador - {dummy_edificio.name}"},
    )
    _dummy = BuildingSimulator(1, "Edificio Simulado", equipment_types={"bomba", "elevador"})
    simulators[1] = _dummy
    logger.warning("No hay equipos en BD. Simulador dummy creado con edificio en BD.")

logger.info("Simuladores activos: %s", list(simulators.keys()))

# ─── Sincronizar variables globales legacy con el primer simulador ─
import apps.sensors.simulation.globals as _sim_globals
_first = next(iter(simulators.values()), None)
if _first:
    _sim_globals.sensor_data.update(_first.sensor_data)
    _sim_globals.pump_on = _first.pump_on
    _sim_globals.elevator_on = _first.elevator_on
    _sim_globals.equipment_types.clear()
    _sim_globals.equipment_types.update(_first.equipment_types)
    _sim_globals.protection_ends.update(_first.protection_ends)
    _sim_globals.active_alerts.update(_first.active_alerts)
    _sim_globals.door_close_attempts = _first.door_close_attempts
    _sim_globals.sim_paused = _first.sim_paused
    _sim_globals.sim_speed = _first.sim_speed
    logger.info("Variables globales legacy sincronizadas con simulador #%s", _first.edificio_id)

# ─── Verificar SMTP ───────────────────────────────────────────────
_smtp_user = os.environ.get("SMTP_USER", "")
_smtp_password = os.environ.get("SMTP_PASSWORD", "")
_smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
_smtp_port = int(os.environ.get("SMTP_PORT", 587))
if _smtp_user and _smtp_password:
    try:
        import smtplib
        _test_server = smtplib.SMTP(_smtp_server, _smtp_port, timeout=10)
        _test_server.starttls()
        _test_server.login(_smtp_user, _smtp_password)
        _test_server.quit()
        logger.info("Conexión SMTP verificada correctamente")
    except Exception as e:
        logger.warning("No se pudo conectar con SMTP (%s:%s): %s. Los correos no se enviarán.", _smtp_server, _smtp_port, e)
else:
    logger.warning("SMTP no configurado. Los correos no se enviarán.")

# ─── Iniciar loop de simulación ───────────────────────────────────
eventlet.spawn(generate_data_and_emit)
logger.info("Loop de simulación iniciado")

# ─── Servir Django con eventlet WSGI ──────────────────────────────
from django.core.handlers.wsgi import WSGIHandler
from django.contrib.staticfiles.handlers import StaticFilesHandler

application = StaticFilesHandler(WSGIHandler())
host = os.environ.get("SIM_HOST", "0.0.0.0")
port = int(os.environ.get("SIM_PORT", 8000))

logger.info("Servidor PCLogo unificado en http://%s:%s", host, port)
eventlet.wsgi.server(eventlet.listen((host, port)), application)
