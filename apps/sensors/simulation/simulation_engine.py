import random
import time
import logging

from apps.sensors.simulation.constants import (
    RANDOM_FAULT_PROB, FAULT_AUTO_CLEAR_SECONDS,
    SIMULTANEOUS_FAIL_PROB, LOG_SIM,
    CLEAR_FAULT_MIN_FLOW, CLEAR_FAULT_MIN_PRESSURE, CLEAR_FAULT_MAX_VIBRATION,
    CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH, CLEAR_FAULT_MAX_LOAD,
)
from apps.sensors.simulation.models import BuildingSimulator

logger = logging.getLogger(__name__)


def update_sensor_data(active_sim: BuildingSimulator) -> None:
    if active_sim.sim_paused:
        return
    _auto_clear_expired_faults(active_sim)
    if active_sim.has_pump:
        from apps.sensors.simulation.physics.pump import _update_pump
        _update_pump(active_sim)
    if active_sim.has_elevator:
        from apps.sensors.simulation.physics.elevator import _update_elevator
        _update_elevator(active_sim)
    _inject_random_faults(active_sim)


def _auto_clear_expired_faults(sim: BuildingSimulator) -> None:
    expired = _get_expired_faults(sim)
    for device in expired:
        _clear_expired_fault_device(sim, device)


def _get_expired_faults(sim: BuildingSimulator) -> list:
    now = time.time()
    return [
        device
        for device, injected_at in sim.fault_injected_at.items()
        if now - injected_at >= FAULT_AUTO_CLEAR_SECONDS
    ]


def _clear_expired_fault_device(sim: BuildingSimulator, device: str) -> None:
    sim.sim_faults.pop(device, None)
    sim.fault_injected_at.pop(device, None)
    if LOG_SIM:
        print(
            f"[SIM] {time.strftime('%H:%M:%S')} "
            f"AUTO-CLEAR: falla de {device} expirada tras {FAULT_AUTO_CLEAR_SECONDS}s"
        )
    sd = sim.sensor_data
    if device == "pump":
        from apps.sensors.simulation.physics.pump import _clamp
        sd["flow_rate"] = max(sd["flow_rate"], CLEAR_FAULT_MIN_FLOW)
        sd["pressure"] = max(sd["pressure"], CLEAR_FAULT_MIN_PRESSURE)
        sd["vibration"] = min(sd["vibration"], CLEAR_FAULT_MAX_VIBRATION)
        sd["voltage"] = _clamp(sd["voltage"], CLEAR_FAULT_VOLTAGE_LOW, CLEAR_FAULT_VOLTAGE_HIGH)
    elif device == "elevator":
        sd["motor_stuck"] = False
        sd["speed"] = max(sd["speed"], 0.0)
        sd["load"] = min(sd["load"], CLEAR_FAULT_MAX_LOAD)
        sd["door_status"] = "closed"
        sim.door_close_attempts = 0
        sim._elev_state = "IDLE"


def _inject_random_faults(sim: BuildingSimulator) -> None:
    if sim.sim_faults:
        return
    dt = sim.sim_speed
    pump_can_fault = (
        "pump" not in sim.protection_ends
        and sim.pump_on
        and random.random() < RANDOM_FAULT_PROB * dt
    )
    elev_can_fault = (
        "elevator" not in sim.protection_ends
        and sim.elevator_on
        and random.random() < RANDOM_FAULT_PROB * dt
    )
    pump_faulted = False
    elev_faulted = False
    if pump_can_fault:
        _inject_random_pump_fault(sim)
        pump_faulted = True
    if elev_can_fault:
        _inject_random_elevator_fault(sim)
        elev_faulted = True
    if pump_faulted and not elev_faulted:
        _maybe_simultaneous_elevator_fault(sim)
    elif elev_faulted and not pump_faulted:
        _maybe_simultaneous_pump_fault(sim)


def _maybe_simultaneous_elevator_fault(sim: BuildingSimulator) -> None:
    if (
        "elevator" not in sim.protection_ends
        and sim.elevator_on
        and random.random() < SIMULTANEOUS_FAIL_PROB
    ):
        _inject_random_elevator_fault(sim)


def _maybe_simultaneous_pump_fault(sim: BuildingSimulator) -> None:
    if (
        "pump" not in sim.protection_ends
        and sim.pump_on
        and random.random() < SIMULTANEOUS_FAIL_PROB
    ):
        _inject_random_pump_fault(sim)


def _inject_random_pump_fault(sim: BuildingSimulator) -> None:
    fault_type = random.choice(["cavitation", "overheat", "blocked_discharge"])
    sim.sim_faults["pump"] = fault_type
    sim.fault_injected_at["pump"] = time.time()
    logger.info("Falla aleatoria de bomba inyectada (vía sim_faults): %s", fault_type)
    if LOG_SIM:
        print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: pump {fault_type}")


def _inject_random_elevator_fault(sim: BuildingSimulator) -> None:
    fault_type = random.choice(["motor_stuck", "door_blocked", "overspeed"])
    sim.sim_faults["elevator"] = fault_type
    sim.fault_injected_at["elevator"] = time.time()
    logger.info("Falla aleatoria de elevador inyectada (vía sim_faults): %s", fault_type)
    if LOG_SIM:
        print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: elevator {fault_type}")
