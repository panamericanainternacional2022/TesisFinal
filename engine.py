"""
Módulo del motor de simulación.
Contiene _run_sim_tick, _sync_globals_to_sim y generate_data_and_emit.
"""

import time
import logging
import eventlet

from front.sensor_config import PUMP_VARS, ELEVATOR_VARS
from simulation import (
    RATIONING_THRESHOLD, MAX_HISTORY_SIZE, LOG_SIM,
    BuildingSimulator, simulators,
    sensor_data, pump_on, elevator_on, equipment_types, protection_ends, active_alerts,
    door_close_attempts, history, alert_log, pending_notifications,
    last_email_sent_time,
    update_sensor_data, check_motor_stuck,
)
from risk import classify_risk
from alerts import (
    send_alert, get_professional_action, check_rationing, update_protection_state,
)
import simulation as _sim_mod
import app27

logger = logging.getLogger(__name__)


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
    global last_email_sent_time

    _saved_active = app27.active_edificio_id

    app27.active_edificio_id = sim.edificio_id
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

    app27.sensor_data              = sim.sensor_data
    app27.pump_on                  = sim.pump_on
    app27.elevator_on              = sim.elevator_on
    app27.equipment_types          = sim.equipment_types
    app27.protection_ends          = sim.protection_ends
    app27.active_alerts            = sim.active_alerts
    app27.door_close_attempts      = sim.door_close_attempts
    app27.history                  = sim.history
    app27.alert_log                = sim.alert_log
    app27.pending_notifications    = sim.pending_notifications
    app27.last_email_sent_time     = sim.last_email_sent_time

    update_protection_state()
    update_sensor_data()

    _alert_vars = set()
    if "bomba" in equipment_types:
        _alert_vars.update(PUMP_VARS)
    if "elevador" in equipment_types:
        _alert_vars.update(ELEVATOR_VARS)
        _alert_vars.add("motor_stuck")

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
            action = get_professional_action(var, risk, value)
            send_alert(var, value, risk, action)
        else:
            active_alerts.pop(var, None)
    check_rationing(sensor_data["flow_rate"])

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    for var, value in sensor_data.items():
        if var not in _alert_vars and var not in ("rationing", "auto_protection", "protection_pump", "protection_elevator"):
            continue
        risk, color = (
            classify_risk(var, value) if var != "motor_stuck"
            else ("Crítico" if value else "Bajo", "red" if value else "green")
        )
        sensor_type = "Bomba" if var in PUMP_VARS else "Elevador"
        new_readings.append({"timestamp": timestamp, "type": sensor_type, "variable": var, "value": value, "risk": risk, "color": color})
    history.extend(new_readings)
    if len(history) > MAX_HISTORY_SIZE:
        sim.history = history[-MAX_HISTORY_SIZE:]
        history = sim.history

    sim.pump_on               = pump_on
    sim.elevator_on           = elevator_on
    sim.door_close_attempts   = _sim_mod.door_close_attempts
    sim.last_email_sent_time  = last_email_sent_time

    app27.active_edificio_id = _saved_active


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

    app27.sensor_data              = sim.sensor_data
    app27.pump_on                  = sim.pump_on
    app27.elevator_on              = sim.elevator_on
    app27.equipment_types          = sim.equipment_types
    app27.protection_ends          = sim.protection_ends
    app27.active_alerts            = sim.active_alerts
    app27.door_close_attempts      = sim.door_close_attempts
    app27.history                  = sim.history
    app27.alert_log                = sim.alert_log
    app27.pending_notifications    = sim.pending_notifications
    app27.last_email_sent_time     = sim.last_email_sent_time


def generate_data_and_emit():
    from payload import build_live_payload

    global equipment_types
    while True:
        eventlet.sleep(5)

        for sim in list(simulators.values()):
            _run_sim_tick(sim)

        active_sim = simulators.get(app27.active_edificio_id)
        if active_sim:
            _sync_globals_to_sim(active_sim)
        else:
            equipment_types = set()
            app27.equipment_types = set()

        payload = build_live_payload()
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} LOOP [{app27.active_edificio_id}]: "
                f"pump_on={pump_on} elevator_on={elevator_on} protection_ends={protection_ends} "
                f"edificios_activos={list(simulators.keys())}"
            )
        app27.socketio.emit("sensor_update", payload)
