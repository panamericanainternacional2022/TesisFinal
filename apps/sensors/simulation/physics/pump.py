import random

from apps.sensors.sensor_config import SENSOR_RANGES
from apps.sensors.simulation.constants import (
    PUMP_P0, PUMP_K, T_AMBIENT,
)
from apps.sensors.simulation.models import BuildingSimulator

# Desempaquetar rangos de bomba
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


def _update_pump(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed
    _update_pump_refill(sim, sd, dt)
    if not sim.pump_on or "pump" in sim.protection_ends:
        _set_pump_idle(sd, dt)
        return
    if "pump" in sim.sim_faults:
        _apply_pump_fault(sim, sd, dt)
        return
    _run_pump_normal(sim, sd, dt)


def _update_pump_refill(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    from apps.sensors.simulation.constants import REFILL_TIMER_TICKS
    sim._pump_refill_timer += dt
    if sim._pump_refill_timer >= REFILL_TIMER_TICKS:
        sim._pump_refill_timer = 0
        sd["tank_level"] = _clamp(sd["tank_level"] + random.uniform(10, 25), 0, 100)


def _set_pump_idle(sd: dict, dt: float) -> None:
    sd["flow_rate"] = 0.0
    sd["pressure"] = 0.0
    sd["vibration"] = 0.0
    sd["current"] = 0.0
    sd["temperature"] = _clamp(sd["temperature"] - 0.5 * dt, _TEMP_LOW, _TEMP_HIGH)
    sd["voltage"] = _clamp(sd["voltage"] + random.uniform(-1, 1) * dt, _VOLT_LOW, _VOLT_HIGH)


def _apply_pump_fault(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    fault_type = sim.sim_faults.get("pump")
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
        handler(sd, dt)
    if fault_type != "power_outage":
        _clamp_pump_values(sd)


def _apply_dry_run(sd: dict, dt: float) -> None:
    sd["flow_rate"] = _clamp(sd["flow_rate"] - 1.5 * dt, 0, 5)
    sd["pressure"] = _clamp(sd["pressure"] - 0.3 * dt, 0, 2)
    sd["temperature"] = _clamp(sd["temperature"] + 1.5 * dt, 0, 130)
    sd["vibration"] = _clamp(sd["vibration"] + 0.5 * dt, 0, 15)
    sd["tank_level"] = _clamp(sd["tank_level"] - 0.5 * dt, 0, 100)


def _apply_blocked_discharge(sd: dict, dt: float) -> None:
    sd["flow_rate"] = _clamp(sd["flow_rate"] - 2.0 * dt, 0, 3)
    sd["pressure"] = _clamp(sd["pressure"] + 1.0 * dt, 0, 12)
    sd["vibration"] = _clamp(sd["vibration"] + 0.8 * dt, 0, 15)
    sd["temperature"] = _clamp(sd["temperature"] + 0.8 * dt, 0, 130)
    sd["tank_level"] = _clamp(sd["tank_level"] + 0.1 * dt, 0, 100)


def _apply_pipe_burst(sd: dict, dt: float) -> None:
    sd["flow_rate"] = _clamp(sd["flow_rate"] + 3.0 * dt, 0, 60)
    sd["pressure"] = _clamp(sd["pressure"] - 0.8 * dt, 0, 2)
    sd["vibration"] = _clamp(sd["vibration"] + 0.6 * dt, 0, 15)
    sd["tank_level"] = _clamp(sd["tank_level"] - 2.0 * dt, 0, 100)


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


def _clamp_pump_values(sd: dict) -> None:
    sd["flow_rate"] = round(_clamp(sd["flow_rate"], _FLOW_LOW, _FLOW_HIGH), 1)
    sd["pressure"] = round(_clamp(sd["pressure"], _PRES_LOW, _PRES_HIGH), 1)
    sd["temperature"] = round(_clamp(sd["temperature"], _TEMP_LOW, _TEMP_HIGH), 1)
    sd["vibration"] = round(_clamp(sd["vibration"], _VIB_LOW, _VIB_HIGH), 1)
    sd["voltage"] = round(sd["voltage"], 1)
    sd["current"] = round(_clamp(sd["current"], _CURR_LOW, _CURR_HIGH), 1)


def _run_pump_normal(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._pump_demand = _rand_walk(sim._pump_demand, 0.5 * dt, 8, 25)
    if random.random() < 0.02 * dt:
        sim._pump_demand = _clamp(sim._pump_demand + random.uniform(8, 15), 8, 35)
    flow = sim._pump_demand
    pressure = max(0.5, PUMP_P0 - PUMP_K * flow ** 2) + random.uniform(-0.2, 0.2) * dt
    temp = _compute_pump_temperature(sd, flow, pressure, dt)
    vib = 0.5 + flow / 25 + max(0, sd["temperature"] - 65) / 40
    vib += random.uniform(-0.2, 0.3) * dt
    tank = _compute_pump_tank_level(sd, flow, dt)
    volt = 220.0 + random.uniform(-2, 2) * dt
    curr = flow * pressure / (volt * 0.75) + random.uniform(-0.5, 0.5) * dt
    _write_pump_outputs(sd, flow, pressure, temp, vib, tank, volt, curr)


def _compute_pump_temperature(sd: dict, flow: float, pressure: float, dt: float) -> float:
    temp = sd["temperature"]
    temp += (flow * pressure * 0.01 - 0.3) * dt
    temp += random.uniform(-0.3, 0.3) * dt
    if sd["tank_level"] < 10:
        temp += 0.5 * dt
    return temp


def _compute_pump_tank_level(sd: dict, flow: float, dt: float) -> float:
    tank = sd["tank_level"] - flow * 0.08 * dt
    if random.random() < 0.02 * dt:
        tank += random.uniform(5, 15)
    return tank


def _write_pump_outputs(
    sd: dict, flow: float, pressure: float, temp: float,
    vib: float, tank: float, volt: float, curr: float,
) -> None:
    sd["flow_rate"] = round(_clamp(flow, _FLOW_LOW, _FLOW_HIGH), 1)
    sd["pressure"] = round(_clamp(pressure, _PRES_LOW, _PRES_HIGH), 1)
    sd["temperature"] = round(_clamp(temp, _TEMP_LOW, _TEMP_HIGH), 1)
    sd["vibration"] = round(_clamp(vib, _VIB_LOW, _VIB_HIGH), 1)
    sd["tank_level"] = round(_clamp(tank, _TANK_LOW, _TANK_HIGH), 1)
    sd["voltage"] = round(_clamp(volt, _VOLT_LOW, _VOLT_HIGH), 1)
    sd["current"] = round(_clamp(curr, _CURR_LOW, _CURR_HIGH), 1)
