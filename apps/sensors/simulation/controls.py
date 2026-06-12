import random
import time
import logging

from apps.sensors.simulation.constants import (
    DEFAULT_SENSOR_DATA, FLOOR_COUNT, T_AMBIENT,
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


def reset_critical_values(targets: set[str], sim: BuildingSimulator) -> None:
    if not targets:
        return
    sd = sim.sensor_data
    if "pump" in targets:
        sd["flow_rate"] = 25.0
        sd["pressure"] = 4.0
        sd["temperature"] = 50.0
        sd["vibration"] = 1.5
        sd["tank_level"] = 80.0
        sd["voltage"] = 220.0
        sd["current"] = 18.0
    if "elevator" in targets:
        sd["position"] = 0
        sd["speed"] = 0.0
        sd["load"] = 200
        sd["motor_stuck"] = False
        sd["door_status"] = "closed"
        sd["energy"] = 5.0
        sd["temperature"] = 50.0
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
        "pump": ("dry_run", "blocked_discharge", "pipe_burst", "cavitation", "overheat", "power_surge", "power_outage"),
        "elevator": ("motor_stuck", "door_blocked", "overspeed"),
    }
    if fault_type not in valid_faults[device]:
        raise InvalidFaultTypeError(device, fault_type)
    sim.sim_faults[device] = fault_type
    sim.fault_injected_at[device] = time.time()
    logger.info("Falla inyectada: edificio=%s, device=%s, tipo=%s", edificio_id, device, fault_type)
    return f"Falla '{fault_type}' inyectada en {device}"


from typing import Optional


def clear_fault(edificio_id: int, device: Optional[str] = None) -> str:
    sim = simulators.get(edificio_id)
    if not sim:
        raise SimulatorNotFoundError(edificio_id)
    if device:
        sim.sim_faults.pop(device, None)
        sim.fault_injected_at.pop(device, None)
        msg = f"Falla limpiada para {device}"
    else:
        sim.sim_faults.clear()
        sim.fault_injected_at.clear()
        msg = "Todas las fallas limpiadas"
    sd = sim.sensor_data
    if device in (None, "pump"):
        from apps.sensors.simulation.physics import _clamp
        sd["flow_rate"] = max(sd["flow_rate"], 15.0)
        sd["pressure"] = max(sd["pressure"], 3.0)
        sd["vibration"] = min(sd["vibration"], 5.0)
        sd["voltage"] = _clamp(sd["voltage"], 210, 230)
    if device in (None, "elevator"):
        sd["motor_stuck"] = False
        sd["speed"] = max(sd["speed"], 0.0)
        sd["load"] = min(sd["load"], 500)
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
    sim._elev_target_floor = random.randint(1, FLOOR_COUNT)
    sim._elev_direction = 1
    sim._elev_at_floor = True
    logger.info("Simulador reiniciado: edificio=%s", edificio_id)
    return "Simulador reiniciado al estado normal"
