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

# ─── Django setup ─────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

# ─── Cargar .env antes de módulos que lean variables ──────────────
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, val = line.strip().split("=", 1)
                os.environ[key.strip()] = val.strip().strip("'\"")
    logger.info(".env cargado")

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
    _dummy = BuildingSimulator(1, "Edificio Simulado", equipment_types={"bomba", "elevador"})
    simulators[1] = _dummy
    logger.warning("No hay equipos en BD. Simulador dummy creado.")

logger.info("Simuladores activos: %s", list(simulators.keys()))

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
