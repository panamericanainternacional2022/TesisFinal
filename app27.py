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
import logging
import json

from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
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
    logger.info("Django integrado correctamente en app27.py")
except Exception as e:
    logger.warning("No se pudo inicializar Django desde app27.py: %s", e)

# ----------------------------------------------------------------------
# Configuración centralizada de sensores (fuente única de verdad)
# ----------------------------------------------------------------------
from front.sensor_config import (
    VAR_NAMES,
    UNITS,
    STATS_VARS,
    PUMP_VARS,
    ELEVATOR_VARS,
    NO_RISK_VARS,
)

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

from alerts import (
    get_building_emails, send_email_alert, send_alert,
    get_professional_action, check_rationing, generate_recommendations,
    enter_protection_mode, update_protection_state,
    persist_notification_in_django,
    _es_var, _es_device, get_unit, subscribers,
)

from pdf_report import generate_pdf_report

from payload import build_live_payload, titleize_name
from engine import _run_sim_tick, _sync_globals_to_sim, generate_data_and_emit

active_edificio_id = None

from risk import classify_risk
from settings import thresholds

alert_enabled = True

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
        elevador_vars=ELEVATOR_VARS,
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
    global active_edificio_id, equipment_types, pump_on, elevator_on
    active_edificio_id = edificio_id
    logger.info(f"Edificio activo cambiado a: {active_edificio_id}")
    # Sincronizar globales al nuevo simulador activo de inmediato
    # para que las rutas Flask reflejen el edificio correcto
    new_sim = simulators.get(edificio_id)
    if new_sim:
        _sync_globals_to_sim(new_sim)
        logger.info(f"Globales sincronizados al simulador: {new_sim}")
    else:
        # Si el edificio no tiene equipos, limpiar equipment_types para
        # que build_live_payload() responda sin datos de sensores
        logger.warning(f"No existe simulador para edificio_id={edificio_id} (sin equipos). Limpiando equipment_types.")
        equipment_types = set()
        pump_on = False
        elevator_on = False
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
    sensor_type = "Bomba" if variable in PUMP_VARS else "Elevador"
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
