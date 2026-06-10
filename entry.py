#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Punto de entrada del sistema PCLogo.
Inicializa Django, carga .env, crea la app Flask/SocketIO y arranca el loop.
Ejecutar: python entry.py
"""

import os
import sys
import logging

from flask import Flask
from flask_socketio import SocketIO
import eventlet

# Parchado de eventlet para compatibilidad con Socket.IO y peticiones concurrentes
eventlet.monkey_patch()


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
    logger.info("Django integrado correctamente en entry.py")
except Exception as e:
    logger.warning("No se pudo inicializar Django desde entry.py: %s", e)

# ----------------------------------------------------------------------
# Estado del simulador (importado desde simulation.py)
# Expuesto en el namespace de entry para que engine.py pueda sincronizarlo.
# ----------------------------------------------------------------------
from simulation import (
    BuildingSimulator, simulators,
    sensor_data, pump_on, elevator_on, equipment_types, protection_ends, active_alerts,
    door_close_attempts, history, alert_log, pending_notifications,
    last_email_sent_time, sim_paused, sim_speed,
)

# ----------------------------------------------------------------------
# Cargar credenciales desde .env ANTES de importar módulos que las lean
# ----------------------------------------------------------------------
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    os.environ[key.strip()] = val.strip().strip("'\"")

active_edificio_id = None
alert_enabled = True

# ----------------------------------------------------------------------
# Servidor Flask
# ----------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "clave-segura"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ----------------------------------------------------------------------
# Inicio del servidor
# ----------------------------------------------------------------------
if __name__ == "__main__":
    from routes import register_routes
    from engine import _sync_globals_to_sim, generate_data_and_emit

    register_routes(app, socketio)

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
