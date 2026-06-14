import time
import logging

import eventlet

from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS, RISK_CRITICO, RISK_ALTO, RISK_BAJO
from apps.sensors.simulation.constants import (
    MAX_HISTORY_SIZE,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.simulation_engine import update_sensor_data


logger = logging.getLogger(__name__)


def _run_sim_tick(sim: BuildingSimulator) -> None:
    if sim.sim_paused:
        return
    from apps.alerts.alerts.protection import update_protection_state
    update_protection_state(sim=sim)
    update_sensor_data(active_sim=sim)
    alert_vars = _get_alert_vars(sim)
    _process_sensor_alerts(sim, alert_vars)
    _build_history_records(sim, alert_vars)


def _get_alert_vars(sim: BuildingSimulator) -> set[str]:
    alert_vars = set()
    if "bomba" in sim.equipment_types:
        alert_vars.update(PUMP_VARS)
    if "elevador" in sim.equipment_types:
        alert_vars.update(ELEVATOR_VARS)
        alert_vars.add("motor_stuck")
    return alert_vars


def _process_sensor_alerts(sim: BuildingSimulator, alert_vars: set[str]) -> None:
    from apps.core.services.risk_service import classify_risk
    for var, value in sim.sensor_data.items():
        if var not in alert_vars:
            continue
        if var == "motor_stuck":
            _handle_motor_stuck_alert(sim, var, value)
            continue
        from apps.alerts.alerts.engine import send_alert
        from apps.alerts.services.alert_service import get_professional_action
        risk, _ = classify_risk(var, value)
        if risk in (RISK_ALTO, RISK_CRITICO):
            action = get_professional_action(var, risk, value)
            send_alert(var, value, risk, action, sim=sim)
        else:
            sim.active_alerts.pop(var, None)
    from apps.alerts.alerts.engine import check_rationing
    check_rationing(sim.sensor_data["flow_rate"], sim=sim)


def _handle_motor_stuck_alert(
    sim: BuildingSimulator, var: str, value: object,
) -> None:
    if value:
        from apps.alerts.alerts.engine import send_alert
        from apps.alerts.services.alert_service import get_professional_action
        action = get_professional_action(var, RISK_CRITICO, value)
        send_alert(var, value, RISK_CRITICO, action, sim=sim)
    else:
        sim.active_alerts.pop(var, None)


def _build_history_records(sim: BuildingSimulator, alert_vars: set[str]) -> None:
    from apps.core.services.risk_service import classify_risk
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    for var, value in sim.sensor_data.items():
        if var not in alert_vars and var not in (
            "rationing", "auto_protection", "protection_pump", "protection_elevator",
        ):
            continue
        risk, color = (
            classify_risk(var, value) if var != "motor_stuck"
            else (RISK_CRITICO if value else RISK_BAJO, "red" if value else "green")
        )
        sensor_type = "Bomba" if var in PUMP_VARS else "Elevador"
        new_readings.append({
            "timestamp": timestamp,
            "type": sensor_type,
            "variable": var,
            "value": value,
            "risk": risk,
            "color": color,
        })
    sim.history.extend(new_readings)
    if len(sim.history) > MAX_HISTORY_SIZE:
        sim.history = sim.history[-MAX_HISTORY_SIZE:]


def generate_data_and_emit() -> None:
    _consecutive_failures: dict[int, int] = {}
    _max_consecutive_failures = 5
    while True:
        eventlet.sleep(5)
        for sim in list(simulators.values()):
            try:
                _run_sim_tick(sim)
                _consecutive_failures.pop(sim.edificio_id, None)
            except Exception:
                fails = _consecutive_failures.get(sim.edificio_id, 0) + 1
                _consecutive_failures[sim.edificio_id] = fails
                logger.exception(
                    "Error en tick de sim %s (%s) — fallo consecutivo #%s",
                    sim.edificio_id, sim.nombre, fails,
                )
                if fails >= _max_consecutive_failures:
                    logger.error(
                        "Removiendo simulador %s (%s) tras %s fallos consecutivos",
                        sim.edificio_id, sim.nombre, fails,
                    )
                    del simulators[sim.edificio_id]
                    _consecutive_failures.pop(sim.edificio_id, None)
