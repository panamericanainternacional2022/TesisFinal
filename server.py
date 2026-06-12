#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
from apps.sensors.simulation import BuildingSimulator, simulators
from apps.sensors.engine import generate_data_and_emit
from apps.buildings.models import EquipoMonitoreo

equipos = EquipoMonitoreo.objects.select_related("id_edificio").all()
for eq in equipos:
    if not eq.id_edificio:
        continue
    eid = eq.id_edificio.id_edificio
    enombre = eq.id_edificio.nb_edificio or f"Edificio #{eid}"
    if eid not in simulators:
        simulators[eid] = BuildingSimulator(eid, enombre)
    simulators[eid].equipment_types.add(eq.tipo)
    simulators[eid].has_pump = "bomba" in simulators[eid].equipment_types
    simulators[eid].has_elevator = "elevador" in simulators[eid].equipment_types
    simulators[eid].pump_on = simulators[eid].has_pump
    simulators[eid].elevator_on = simulators[eid].has_elevator
    logger.info("Simulador creado: edificio=%s tipo=%s", eid, eq.tipo)

if not simulators:
    from apps.buildings.models import Edificio as EdifModel
    dummy_edificio, _ = EdifModel.objects.get_or_create(
        rif="J-00000000-0",
        defaults={"nb_edificio": "Edificio Simulado", "direccion": "Dirección simulada"},
    )
    EquipoMonitoreo.objects.get_or_create(
        id_edificio=dummy_edificio, tipo=EquipoMonitoreo.TIPO_BOMBA,
        defaults={"nb_equipo": f"Bomba de agua - {dummy_edificio.nb_edificio}"},
    )
    EquipoMonitoreo.objects.get_or_create(
        id_edificio=dummy_edificio, tipo=EquipoMonitoreo.TIPO_ELEVADOR,
        defaults={"nb_equipo": f"Elevador - {dummy_edificio.nb_edificio}"},
    )
    _dummy = BuildingSimulator(1, "Edificio Simulado", equipment_types={"bomba", "elevador"})
    simulators[1] = _dummy
    logger.warning("No hay equipos en BD. Simulador dummy creado con edificio en BD.")

logger.info("Simuladores activos: %s", list(simulators.keys()))

# ─── Sincronizar variables globales legacy con el primer simulador ─
import apps.sensors.simulation as _sim_mod
_first = next(iter(simulators.values()), None)
if _first:
    _sim_mod.sensor_data.update(_first.sensor_data)
    _sim_mod.pump_on = _first.pump_on
    _sim_mod.elevator_on = _first.elevator_on
    _sim_mod.equipment_types.clear()
    _sim_mod.equipment_types.update(_first.equipment_types)
    _sim_mod.protection_ends.update(_first.protection_ends)
    _sim_mod.active_alerts.update(_first.active_alerts)
    _sim_mod.door_close_attempts = _first.door_close_attempts
    _sim_mod.sim_paused = _first.sim_paused
    _sim_mod.sim_speed = _first.sim_speed
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

application = WSGIHandler()
host = os.environ.get("SIM_HOST", "0.0.0.0")
port = int(os.environ.get("SIM_PORT", 8000))

logger.info("Servidor PCLogo unificado en http://%s:%s", host, port)
eventlet.wsgi.server(eventlet.listen((host, port)), application)
