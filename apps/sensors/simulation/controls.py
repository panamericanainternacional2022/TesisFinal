import random
import time
import logging
from typing import Optional

from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS, PUMP_FAULT_KEYS, ELEVATOR_FAULT_KEYS, FAULT_NAMES_ES
from apps.sensors.simulation.constants import (
    DEFAULT_SENSOR_DATA, FLOOR_COUNT, SAFE_RESET_VALUES,
    CLEAR_FAULT_MIN_FLOW, CLEAR_FAULT_MIN_PRESSURE, CLEAR_FAULT_MAX_VIBRATION,
    CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH, CLEAR_FAULT_MAX_LOAD,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.exceptions import (
    SimulatorNotFoundError,
    InvalidDeviceError,
    DeviceNotInBuildingError,
    InvalidFaultTypeError,
)

logger = logging.getLogger(__name__)

PUMP_RESET_KEYS = [v for v in PUMP_VARS if v in SAFE_RESET_VALUES]
ELEVATOR_RESET_KEYS = [v for v in ELEVATOR_VARS if v in SAFE_RESET_VALUES] + ["temperature"]


def reset_critical_values(targets: set[str], sim: BuildingSimulator) -> None:
    if not targets:
        return
    sd = sim.sensor_data
    if "pump" in targets:
        for k in PUMP_RESET_KEYS:
            if k in SAFE_RESET_VALUES:
                sd[k] = SAFE_RESET_VALUES[k]
    if "elevator" in targets:
        for k in ELEVATOR_RESET_KEYS:
            if k in SAFE_RESET_VALUES:
                sd[k] = SAFE_RESET_VALUES[k]
    sim.door_close_attempts = 0


def inject_fault(edificio_id: int, device: str, fault_type: str) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)
    if device not in ("pump", "elevator"):
        raise InvalidDeviceError(device)
    if (device == "pump" and not sim.has_pump) or (device == "elevator" and not sim.has_elevator):
        raise DeviceNotInBuildingError(device)
    valid_faults = {
        "pump": PUMP_FAULT_KEYS,
        "elevator": ELEVATOR_FAULT_KEYS,
    }
    if fault_type not in valid_faults[device]:
        raise InvalidFaultTypeError(device, fault_type)
    sim.sim_faults[device] = fault_type
    sim.fault_injected_at[device] = time.time()
    logger.info("Falla inyectada: edificio=%s, device=%s, tipo=%s", edificio_id, device, fault_type)
    _DEVICE_ES = {"pump": "Bomba", "elevator": "Elevador"}
    nombre_falla = FAULT_NAMES_ES.get(fault_type, fault_type)
    nombre_dispositivo = _DEVICE_ES.get(device, device)
    return f"Falla '{nombre_falla}' inyectada en {nombre_dispositivo}"

def clear_fault(edificio_id: int, device: Optional[str] = None) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)
    _DEVICE_ES = {"pump": "Bomba", "elevator": "Elevador"}
    if device:
        sim.sim_faults.pop(device, None)
        sim.fault_injected_at.pop(device, None)
        nombre_dispositivo = _DEVICE_ES.get(device, device)
        msg = f"Falla limpiada para {nombre_dispositivo}"
    else:
        sim.sim_faults.clear()
        sim.fault_injected_at.clear()
        msg = "Todas las fallas limpiadas"
    sd = sim.sensor_data
    if device in (None, "pump"):
        from apps.sensors.simulation.physics.pump import _clamp
        sd["flow_rate"] = max(sd["flow_rate"], CLEAR_FAULT_MIN_FLOW)
        sd["pressure"] = max(sd["pressure"], CLEAR_FAULT_MIN_PRESSURE)
        sd["vibration"] = min(sd["vibration"], CLEAR_FAULT_MAX_VIBRATION)
        sd["voltage"] = _clamp(sd["voltage"], CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH)
    if device in (None, "elevator"):
        sd["motor_stuck"] = False
        sd["speed"] = max(sd["speed"], 0.0)
        sd["load"] = min(sd["load"], CLEAR_FAULT_MAX_LOAD)
        sd["door_status"] = "closed"
        sim.door_close_attempts = 0
        sim._elev_state = "IDLE"
    logger.info(msg)
    return msg


def reset_simulator(edificio_id: int) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)
    sim.sensor_data = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
    sim.pump_on = sim.has_pump
    sim.elevator_on = sim.has_elevator
    sim.protection_ends.clear()
    sim.active_alerts.clear()
    sim.door_close_attempts = 0
    sim.history.clear()
    sim.pending_notifications.clear()
    sim.sim_faults.clear()
    sim.fault_injected_at.clear()
    sim.sim_paused = False
    sim.sim_speed = 1.0
    sim._pump_demand = 15.0
    sim._pump_refill_timer = 0
    sim._elev_state = "IDLE"
    sim._elev_timer = 0
    sim._elev_target_floor = random.randint(1, sim.floors)
    sim._elev_direction = 1
    sim._elev_at_floor = True
    sim._elev_position_meters = 0.0
    logger.info("Simulador reiniciado: edificio=%s", edificio_id)
    return "Simulador reiniciado al estado normal"
