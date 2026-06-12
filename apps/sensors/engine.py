"""
Módulo del motor de simulación.
Contiene _run_sim_tick, generate_data_and_emit.
Ya no emite por SocketIO — el SSE drena los payloads.
"""

import time
import logging
import eventlet

from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS
from apps.sensors.simulation import (
    RATIONING_THRESHOLD, MAX_HISTORY_SIZE, LOG_SIM,
    BuildingSimulator, simulators,
    update_sensor_data,
)
from apps.reports.services.risk_service import classify_risk
from apps.alerts.alerts import (
    send_alert, get_professional_action, check_rationing, update_protection_state,
)

logger = logging.getLogger(__name__)


def _run_sim_tick(sim: BuildingSimulator):
    if sim.sim_paused:
        return

    update_protection_state(sim=sim)
    update_sensor_data(active_sim=sim)

    _alert_vars = set()
    if "bomba" in sim.equipment_types:
        _alert_vars.update(PUMP_VARS)
    if "elevador" in sim.equipment_types:
        _alert_vars.update(ELEVATOR_VARS)
        _alert_vars.add("motor_stuck")

    for var, value in sim.sensor_data.items():
        if var not in _alert_vars:
            continue
        if var == "motor_stuck":
            if value:
                action = get_professional_action(var, "Crítico", value)
                send_alert(var, value, "Crítico", action, sim=sim)
            else:
                sim.active_alerts.pop(var, None)
            continue
        risk, _ = classify_risk(var, value)
        if risk in ("Alto", "Crítico"):
            action = get_professional_action(var, risk, value)
            send_alert(var, value, risk, action, sim=sim)
        else:
            sim.active_alerts.pop(var, None)
    check_rationing(sim.sensor_data["flow_rate"], sim=sim)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    for var, value in sim.sensor_data.items():
        if var not in _alert_vars and var not in ("rationing", "auto_protection", "protection_pump", "protection_elevator"):
            continue
        risk, color = (
            classify_risk(var, value) if var != "motor_stuck"
            else ("Crítico" if value else "Bajo", "red" if value else "green")
        )
        sensor_type = "Bomba" if var in PUMP_VARS else "Elevador"
        new_readings.append({"timestamp": timestamp, "type": sensor_type, "variable": var, "value": value, "risk": risk, "color": color})
    sim.history.extend(new_readings)
    if len(sim.history) > MAX_HISTORY_SIZE:
        sim.history = sim.history[-MAX_HISTORY_SIZE:]


def generate_data_and_emit():
    """Loop principal de simulación. Corre en un green thread.
    El SSE drena los payloads desde cada sim.pending_notifications."""
    while True:
        eventlet.sleep(5)
        for sim in list(simulators.values()):
            try:
                _run_sim_tick(sim)
            except Exception:
                logger.exception("Error en tick de sim %s (%s)", sim.edificio_id, sim.nombre)
