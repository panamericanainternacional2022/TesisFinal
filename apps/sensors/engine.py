import time
import logging

import eventlet

from apps.sensors.sensor_config import (
    PUMP_VARS, ELEVATOR_VARS, SYSTEM_VARS, ALERT_VARS,
    RISK_CRITICO, RISK_ALTO, RISK_BAJO, BOOLEAN_VARS, ENUM_VARS,
    ENUM_RISK_VALUES,
    SIM_TICK_INTERVAL,
)
from apps.sensors.simulation.constants import (
    MAX_HISTORY_SIZE,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.simulation_engine import update_sensor_data


logger = logging.getLogger(__name__)

# Máximo de ticks a omitir en backoff exponencial (≈ 30 × SIM_TICK_INTERVAL s).
# El simulador NUNCA se elimina; solo pausa ticks y reintenta automáticamente.
_MAX_BACKOFF_TICKS: int = 30


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
    return alert_vars


def _process_sensor_alerts(sim: BuildingSimulator, alert_vars: set[str]) -> None:
    from apps.core.services.risk_service import classify_risk
    from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS
    from apps.alerts.services.threshold_service import get_thresholds

    # Cargar umbrales del edificio una sola vez por tick
    thresholds = get_thresholds(sim.edificio_id)

    # Determinar qué dispositivos están en modo protección activa.
    # Cuando un dispositivo está en protección, sus sensores bajan a 0.0
    # (via _set_pump_idle / _set_elevator_idle). No se debe generar una
    # nueva alerta por esos ceros — el dispositivo ya está aislado.
    pump_protected = "pump" in sim.protection_ends or not sim.pump_on
    elev_protected = "elevator" in sim.protection_ends or not sim.elevator_on

    for var, value in sim.sensor_data.items():
        if var not in alert_vars:
            continue

        # Suprimir alertas de sensores cuyo dispositivo ya está en protección
        if pump_protected and var in PUMP_VARS:
            sim.active_alerts.pop(var, None)
            continue
        if elev_protected and var in ELEVATOR_VARS:
            sim.active_alerts.pop(var, None)
            continue

        if var in BOOLEAN_VARS:
            _handle_motor_stuck_alert(sim, var, value)
            continue
        if var in ENUM_VARS:
            _handle_enum_alert(sim, var, value)
            continue
        from apps.alerts.alerts.engine import send_alert
        from apps.alerts.services.alert_service import get_professional_action
        risk, _ = classify_risk(var, value, thresholds)
        if risk in (RISK_ALTO, RISK_CRITICO):
            action = get_professional_action(var, risk, value)
            send_alert(var, value, risk, action, sim=sim)
        else:
            sim.active_alerts.pop(var, None)
    from apps.alerts.alerts.engine import check_rationing
    # Solo verificar racionamiento si la bomba no está en protección
    if not pump_protected:
        check_rationing(sim.sensor_data["flow_rate"], sim=sim)
    else:
        sim.active_alerts.pop("rationing", None)



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


def _handle_enum_alert(
    sim: BuildingSimulator, var: str, value: object,
) -> None:
    from apps.alerts.alerts.engine import send_alert
    from apps.alerts.services.alert_service import get_professional_action
    from apps.sensors.sensor_config import ENUM_RISK_VALUES
    from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS

    risky_values = ENUM_RISK_VALUES.get(var, set())
    str_val = str(value).lower() if value is not None else ""
    if str_val in risky_values:
        if var == "door_status" and sim.door_close_attempts < MAX_DOOR_CLOSE_ATTEMPTS:
            sim.active_alerts.pop(var, None)
            return
        risk = RISK_CRITICO
        action = get_professional_action(var, risk, value)
        send_alert(var, value, risk, action, sim=sim)
    else:
        sim.active_alerts.pop(var, None)


def _build_history_records(sim: BuildingSimulator, alert_vars: set[str]) -> None:
    from apps.core.services.risk_service import classify_risk
    from apps.alerts.services.threshold_service import get_thresholds

    # Reutilizar los umbrales del edificio para clasificar historial
    thresholds = get_thresholds(sim.edificio_id)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    all_tracked_vars = set(alert_vars) | set(SYSTEM_VARS)
    for var, value in sim.sensor_data.items():
        if var not in all_tracked_vars:
            continue
        risk, color = (
            classify_risk(var, value, thresholds) if var not in BOOLEAN_VARS
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
    """Loop principal del engine. Procesa todos los simuladores activos cada tick.

    En lugar de eliminar un simulador tras fallos consecutivos, aplica backoff
    exponencial (saltar 2^N ticks, máx. _MAX_BACKOFF_TICKS) y reintenta
    automáticamente. El dict ``simulators`` nunca pierde entradas por errores.
    """
    _consecutive_failures: dict[int, int] = {}
    _backoff_remaining: dict[int, int] = {}   # ticks restantes de pausa por edificio

    while True:
        eventlet.sleep(SIM_TICK_INTERVAL)
        for sim in list(simulators.values()):
            eid = sim.edificio_id

            # ── Backoff: contar regresivo y saltar este tick ────────────
            if _backoff_remaining.get(eid, 0) > 0:
                _backoff_remaining[eid] -= 1
                continue

            try:
                _run_sim_tick(sim)
                # Tick exitoso: limpiar estado de fallos
                _consecutive_failures.pop(eid, None)
                _backoff_remaining.pop(eid, None)
            except Exception:
                fails = _consecutive_failures.get(eid, 0) + 1
                _consecutive_failures[eid] = fails
                logger.exception(
                    "Error en tick de sim %s (%s) — fallo consecutivo #%s",
                    eid, sim.nombre, fails,
                )
                # Backoff exponencial: 2^N ticks (cap = _MAX_BACKOFF_TICKS)
                # El simulador NO se elimina; reintentará automáticamente.
                backoff = min(2 ** fails, _MAX_BACKOFF_TICKS)
                _backoff_remaining[eid] = backoff
                logger.warning(
                    "Simulador %s (%s) en backoff por %s ticks — reintentará automáticamente",
                    eid, sim.nombre, backoff,
                )
