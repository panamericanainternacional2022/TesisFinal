import random
import time

from apps.sensors.sensor_config import SENSOR_RANGES, PUMP_VARS
from apps.sensors.simulation.constants import (
    PUMP_P0, PUMP_K, T_AMBIENT,
)
from apps.sensors.simulation.models import BuildingSimulator

_FLOW_LOW, _FLOW_HIGH = SENSOR_RANGES["flow_rate"]
_PRES_LOW, _PRES_HIGH = SENSOR_RANGES["pressure"]
_TEMP_LOW, _TEMP_HIGH = SENSOR_RANGES["temperature"]
_VIB_LOW, _VIB_HIGH = SENSOR_RANGES["vibration"]
_TANK_LOW, _TANK_HIGH = SENSOR_RANGES["tank_level"]
_VOLT_LOW, _VOLT_HIGH = SENSOR_RANGES["voltage"]
_CURR_LOW, _CURR_HIGH = SENSOR_RANGES["current"]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _rand_walk(current: float, step: float, lo: float, hi: float) -> float:
    return _clamp(current + random.uniform(-step, step), lo, hi)


def _is_locked(sim: BuildingSimulator, var: str) -> bool:
    if hasattr(sim, "manual_overrides") and isinstance(sim.manual_overrides, dict):
        return time.time() < sim.manual_overrides.get(var, 0)
    return False


def _update_pump(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed
    _update_pump_refill(sim, sd, dt)
    if not sim.pump_on or "pump" in sim.protection_ends:
        _set_pump_idle(sim, sd, dt)
        return
    if "pump" in sim.sim_faults:
        _apply_pump_fault(sim, sd, dt)
        return
    _run_pump_normal(sim, sd, dt)


def _update_pump_refill(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    if sim.sim_faults.get("pump") == "dry_run":
        return
    from apps.sensors.simulation.constants import REFILL_TIMER_TICKS
    sim._pump_refill_timer += dt
    if sim._pump_refill_timer >= REFILL_TIMER_TICKS:
        sim._pump_refill_timer = 0
        if not _is_locked(sim, "tank_level"):
            sd["tank_level"] = round(_clamp(sd["tank_level"] + random.uniform(10, 25), 0, 100), 1)


def _set_pump_idle(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    if not _is_locked(sim, "flow_rate"):
        sd["flow_rate"] = 0.0
    if not _is_locked(sim, "pressure"):
        sd["pressure"] = 0.0
    if not _is_locked(sim, "vibration"):
        sd["vibration"] = 0.0
    if not _is_locked(sim, "current"):
        sd["current"] = 0.0
    if not _is_locked(sim, "temperature"):
        sd["temperature"] = round(_clamp(sd["temperature"] - 0.5 * dt, _TEMP_LOW, _TEMP_HIGH), 1)
    if not _is_locked(sim, "voltage"):
        volt = sd["voltage"]
        volt_diff = 220.0 - volt
        sd["voltage"] = round(_clamp(volt + volt_diff * 0.05 * dt + random.uniform(-0.5, 0.5) * dt, _VOLT_LOW, _VOLT_HIGH), 1)


def _apply_pump_fault(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    fault_type = sim.sim_faults.get("pump")
    
    temp_sd = sd.copy()
    
    _PUMP_FAULT_HANDLERS = {
        "dry_run": _apply_dry_run,
        "blocked_discharge": _apply_blocked_discharge,
        "pipe_burst": _apply_pipe_burst,
        "cavitation": _apply_cavitation,
        "overheat": _apply_overheat,
        "power_surge": _apply_power_surge,
        "power_outage": _apply_power_outage,
    }
    handler = _PUMP_FAULT_HANDLERS.get(fault_type)
    if handler:
        handler(temp_sd, dt)
        
    for k in PUMP_VARS:
        if not _is_locked(sim, k):
            sd[k] = temp_sd[k]
            
    if fault_type != "power_outage":
        _clamp_pump_values(sd)


def _apply_dry_run(sd: dict, dt: float) -> None:
    sd["flow_rate"] = _clamp(sd["flow_rate"] - 1.5 * dt, 0, 5)
    sd["pressure"] = _clamp(sd["pressure"] - 0.3 * dt, 0, 2)
    sd["temperature"] = _clamp(sd["temperature"] + 1.5 * dt, 0, 130)
    sd["vibration"] = _clamp(sd["vibration"] + 0.5 * dt, 0, 15)
    sd["tank_level"] = _clamp(sd["tank_level"] - 15.0 * dt, 0, 10)


def _apply_blocked_discharge(sd: dict, dt: float) -> None:
    sd["flow_rate"] = _clamp(sd["flow_rate"] - 2.0 * dt, 0, 3)
    sd["pressure"] = _clamp(sd["pressure"] + 1.5 * dt, 0, 12)
    sd["vibration"] = _clamp(sd["vibration"] + 0.8 * dt, 0, 15)
    sd["temperature"] = _clamp(sd["temperature"] + 0.8 * dt, 0, 130)
    sd["tank_level"] = _clamp(sd["tank_level"] + 0.1 * dt, 0, 100)


def _apply_pipe_burst(sd: dict, dt: float) -> None:
    sd["flow_rate"] = _clamp(sd["flow_rate"] + 3.0 * dt, 0, 60)
    sd["pressure"] = _clamp(sd["pressure"] - 0.8 * dt, 0, 2)
    sd["vibration"] = _clamp(sd["vibration"] + 0.6 * dt, 0, 15)
    sd["tank_level"] = _clamp(sd["tank_level"] - 5.0 * dt, 0, 100)


def _apply_cavitation(sd: dict, dt: float) -> None:
    sd["flow_rate"] = _clamp(sd["flow_rate"] + random.uniform(-5, 5) * dt, 0, 60)
    sd["vibration"] = _clamp(sd["vibration"] + random.uniform(0.5, 2.0) * dt, 0, 15)
    sd["pressure"] = _clamp(sd["pressure"] + random.uniform(-0.5, 0.5) * dt, 0, 12)


def _apply_overheat(sd: dict, dt: float) -> None:
    sd["temperature"] = _clamp(sd["temperature"] + 2.0 * dt, 0, 130)
    sd["vibration"] = _clamp(sd["vibration"] + 0.3 * dt, 0, 15)


def _apply_power_surge(sd: dict, dt: float) -> None:
    sd["voltage"] = _clamp(sd["voltage"] + 30 * dt, 0, 350)
    sd["current"] = _clamp(sd["current"] + 10 * dt, 0, 70)


def _apply_power_outage(sd: dict, dt: float) -> None:
    sd["voltage"] = _clamp(sd["voltage"] - 50 * dt, 0, 10)
    sd["current"] = 0.0
    sd["flow_rate"] = 0.0
    sd["pressure"] = 0.0
    sd["vibration"] = 0.0
    sd["temperature"] = _clamp(sd["temperature"] - 0.5 * dt, T_AMBIENT, _TEMP_HIGH)


def _clamp_pump_values(sd: dict) -> None:
    sd["flow_rate"] = round(_clamp(sd["flow_rate"], _FLOW_LOW, _FLOW_HIGH), 1)
    sd["pressure"] = round(_clamp(sd["pressure"], _PRES_LOW, _PRES_HIGH), 1)
    sd["temperature"] = round(_clamp(sd["temperature"], _TEMP_LOW, _TEMP_HIGH), 1)
    sd["vibration"] = round(_clamp(sd["vibration"], _VIB_LOW, _VIB_HIGH), 1)
    sd["voltage"] = round(sd["voltage"], 1)
    sd["current"] = round(_clamp(sd["current"], _CURR_LOW, _CURR_HIGH), 1)


def _run_pump_normal(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    if not _is_locked(sim, "voltage"):
        volt = sd["voltage"] + (220.0 - sd["voltage"]) * 0.05 * dt + random.uniform(-0.5, 0.5) * dt
        sd["voltage"] = round(_clamp(volt, _VOLT_LOW, _VOLT_HIGH), 1)
    
    volt = sd["voltage"]
    
    if volt < 50.0:
        if not _is_locked(sim, "flow_rate"):
            sd["flow_rate"] = round(_clamp(sd["flow_rate"] - 5.0 * dt, 0.0, _FLOW_HIGH), 1)
        if not _is_locked(sim, "pressure"):
            sd["pressure"] = round(_clamp(sd["pressure"] - 2.0 * dt, 0.0, _PRES_HIGH), 1)
        if not _is_locked(sim, "vibration"):
            sd["vibration"] = round(_clamp(sd["vibration"] - 2.0 * dt, 0.0, _VIB_HIGH), 1)
        if not _is_locked(sim, "current"):
            sd["current"] = 0.0
        if not _is_locked(sim, "temperature"):
            sd["temperature"] = round(_clamp(sd["temperature"] + (T_AMBIENT - sd["temperature"]) * 0.02 * dt, _TEMP_LOW, _TEMP_HIGH), 1)
        return

    if not _is_locked(sim, "tank_level"):
        tank = sd["tank_level"] - sd["flow_rate"] * 0.08 * dt
        if random.random() < 0.02 * dt:
            tank += random.uniform(5, 15)
        sd["tank_level"] = round(_clamp(tank, _TANK_LOW, _TANK_HIGH), 1)

    tank = sd["tank_level"]

    if tank < 10.0:
        if not _is_locked(sim, "flow_rate"):
            sd["flow_rate"] = round(_clamp(sd["flow_rate"] - 3.0 * dt, 0.0, 2.0), 1)
        if not _is_locked(sim, "pressure"):
            sd["pressure"] = round(_clamp(sd["pressure"] - 0.8 * dt, 0.0, 1.0), 1)
        if not _is_locked(sim, "vibration"):
            sd["vibration"] = round(_clamp(sd["vibration"] + 1.2 * dt, 0.5, 15.0), 1)
        if not _is_locked(sim, "temperature"):
            sd["temperature"] = round(_clamp(sd["temperature"] + 2.0 * dt, _TEMP_LOW, 120.0), 1)
        if not _is_locked(sim, "current"):
            sd["current"] = round(_clamp(sd["current"] - 2.0 * dt, 0.0, 8.0), 1)
        return

    if _is_locked(sim, "flow_rate"):
        flow = sd["flow_rate"]
        sim._pump_demand = _clamp(flow, 8.0, 35.0)
    else:
        sim._pump_demand = _rand_walk(sim._pump_demand, 0.5 * dt, 8.0, 25.0)
        if random.random() < 0.02 * dt:
            sim._pump_demand = _clamp(sim._pump_demand + random.uniform(8.0, 15.0), 8.0, 35.0)
        flow = sim._pump_demand

    pressure = max(0.5, PUMP_P0 - PUMP_K * flow ** 2) + random.uniform(-0.1, 0.1) * dt
    
    temp = sd["temperature"] + (flow * pressure * 0.01 - 0.3) * dt + random.uniform(-0.3, 0.3) * dt
    
    vib = 0.5 + flow / 25.0 + max(0.0, temp - 65.0) / 40.0 + random.uniform(-0.2, 0.3) * dt
    
    curr = flow * pressure / (volt * 0.75) + random.uniform(-0.5, 0.5) * dt

    if not _is_locked(sim, "flow_rate"):
        sd["flow_rate"] = round(_clamp(flow, _FLOW_LOW, _FLOW_HIGH), 1)
    if not _is_locked(sim, "pressure"):
        sd["pressure"] = round(_clamp(pressure, _PRES_LOW, _PRES_HIGH), 1)
    if not _is_locked(sim, "temperature"):
        sd["temperature"] = round(_clamp(temp, _TEMP_LOW, _TEMP_HIGH), 1)
    if not _is_locked(sim, "vibration"):
        sd["vibration"] = round(_clamp(vib, _VIB_LOW, _VIB_HIGH), 1)
    if not _is_locked(sim, "current"):
        sd["current"] = round(_clamp(curr, _CURR_LOW, _CURR_HIGH), 1)
