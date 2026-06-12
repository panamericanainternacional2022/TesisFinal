import random

from apps.sensors.simulation.constants import (
    PUMP_P0, PUMP_K, T_AMBIENT, FLOOR_COUNT, FLOOR_HEIGHT,
    CRUISING_SPEED, ACCELERATION, PASSENGER_WAIT_TICKS,
)
from apps.sensors.simulation.models import BuildingSimulator


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
    sim._pump_refill_timer += dt
    if sim._pump_refill_timer >= 15:
        sim._pump_refill_timer = 0
        sd["tank_level"] = _clamp(sd["tank_level"] + random.uniform(10, 25), 0, 100)


def _set_pump_idle(sd: dict, dt: float) -> None:
    sd["flow_rate"] = 0.0
    sd["pressure"] = 0.0
    sd["vibration"] = 0.0
    sd["current"] = 0.0
    sd["temperature"] = _clamp(sd["temperature"] - 0.5 * dt, T_AMBIENT, 130)
    sd["voltage"] = _clamp(sd["voltage"] + random.uniform(-1, 1) * dt, 180, 260)


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
    sd["flow_rate"] = round(_clamp(sd["flow_rate"], 0, 60), 1)
    sd["pressure"] = round(_clamp(sd["pressure"], 0, 12), 1)
    sd["temperature"] = round(_clamp(sd["temperature"], T_AMBIENT, 130), 1)
    sd["vibration"] = round(_clamp(sd["vibration"], 0, 15), 1)
    sd["voltage"] = round(sd["voltage"], 1)
    sd["current"] = round(_clamp(sd["current"], 0, 70), 1)


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
    sd["flow_rate"] = round(_clamp(flow, 0, 60), 1)
    sd["pressure"] = round(_clamp(pressure, 0, 12), 1)
    sd["temperature"] = round(_clamp(temp, T_AMBIENT, 130), 1)
    sd["vibration"] = round(_clamp(vib, 0, 15), 1)
    sd["tank_level"] = round(_clamp(tank, 0, 100), 1)
    sd["voltage"] = round(_clamp(volt, 180, 260), 1)
    sd["current"] = round(_clamp(curr, 0, 70), 1)


def _update_elevator(sim: BuildingSimulator) -> None:
    sd = sim.sensor_data
    dt = sim.sim_speed
    if not sim.elevator_on or "elevator" in sim.protection_ends:
        _set_elevator_idle(sim, sd)
        return
    if "elevator" in sim.sim_faults:
        _apply_elevator_fault(sim, sd, dt)
        return
    _run_elevator_fsm(sim, sd, dt)


def _set_elevator_idle(sim: BuildingSimulator, sd: dict) -> None:
    sd["speed"] = 0.0
    sd["position"] = round(sd["position"], 1)
    sd["load"] = 0
    sd["door_status"] = "closed"
    sd["energy"] = 0.0
    sd["motor_stuck"] = False
    sim.door_close_attempts = 0
    sim._elev_state = "IDLE"


def _apply_elevator_fault(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    fault_type = sim.sim_faults.get("elevator")
    _ELEV_FAULT_HANDLERS = {
        "motor_stuck": _apply_motor_stuck,
        "door_blocked": _apply_door_blocked,
        "overspeed": _apply_overspeed,
    }
    handler = _ELEV_FAULT_HANDLERS.get(fault_type)
    if handler:
        handler(sim, sd, dt)


def _apply_motor_stuck(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sd["speed"] = 0.0
    sd["motor_stuck"] = True
    sd["load"] = _clamp(sd["load"] + 5 * dt, 0, 1200)
    sd["door_status"] = "closed"
    sd["energy"] = _clamp(sd["energy"] + 0.5 * dt, 0, 20)
    sd["temperature"] = _clamp(sd["temperature"] + 0.5 * dt, T_AMBIENT, 130)


def _apply_door_blocked(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sd["door_status"] = "open"
    sim.door_close_attempts += 1
    sd["motor_stuck"] = False
    sd["speed"] = 0.0
    sd["energy"] = _clamp(sd["energy"] - 0.1 * dt, 0, 20)


def _apply_overspeed(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sd["speed"] = _clamp(sd["speed"] + 0.5 * dt, 0, 6)
    sd["position"] = _clamp(
        sd["position"] + sd["speed"] * dt * 0.5, 0, FLOOR_COUNT * FLOOR_HEIGHT,
    )
    sd["door_status"] = "closed"
    sd["motor_stuck"] = False
    sd["load"] = _clamp(sd["load"] + random.uniform(-10, 10) * dt, 0, 1200)
    sd["energy"] = sd["load"] * sd["speed"] * 0.004 + random.uniform(0.2, 0.5) * dt


def _run_elevator_fsm(sim: BuildingSimulator, sd: dict, dt: float) -> None:
    sim._elev_timer += dt
    prev_pos = sd["position"]
    pos = sd["position"]
    spd = sd["speed"]
    load = sd["load"]
    door = sd["door_status"]
    state = sim._elev_state
    target = sim._elev_target_floor * FLOOR_HEIGHT
    direction = sim._elev_direction
    _ELEV_STATE_HANDLERS = {
        "IDLE": _handle_elev_idle,
        "DOOR_OPENING": _handle_elev_door_opening,
        "DOORS_OPEN": _handle_elev_doors_open,
        "DOOR_CLOSING": _handle_elev_door_closing,
        "ACCELERATING": _handle_elev_accelerating,
        "MOVING": _handle_elev_moving,
        "DECELERATING": _handle_elev_decelerating,
    }
    handler = _ELEV_STATE_HANDLERS.get(state)
    if handler:
        handler(sim, sd, dt, spd, pos, load, door, target, direction)
    pos = sd["position"]
    spd = sd["speed"]
    _run_elevator_post_fsm(sim, sd, dt, prev_pos, pos, spd, load, door)


def _handle_elev_idle(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "closed"
    if sim._elev_timer >= random.uniform(2, 5):
        sim._elev_timer = 0
        sim._elev_target_floor = random.randint(0, FLOOR_COUNT)
        floor_num = round(pos / FLOOR_HEIGHT)
        while sim._elev_target_floor == floor_num:
            sim._elev_target_floor = random.randint(0, FLOOR_COUNT)
        sim._elev_direction = 1 if sim._elev_target_floor > floor_num else -1
        sim._elev_state = "DOOR_OPENING"
    sd["speed"] = spd
    sd["door_status"] = door


def _handle_elev_door_opening(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "opening"
    if sim._elev_timer >= 1:
        sim._elev_timer = 0
        load = _clamp(load + random.randint(-50, 150), 0, 1200)
        sim._elev_state = "DOORS_OPEN"
    sd["speed"] = spd
    sd["door_status"] = door
    sd["load"] = round(load)


def _handle_elev_doors_open(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "open"
    if sim._elev_timer >= PASSENGER_WAIT_TICKS / max(sim.sim_speed, 0.1):
        sim._elev_timer = 0
        load = _clamp(load + random.randint(-100, 100), 0, 1200)
        sim._elev_state = "DOOR_CLOSING"
    sd["speed"] = spd
    sd["door_status"] = door
    sd["load"] = round(load)


def _handle_elev_door_closing(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = 0.0
    door = "closing"
    if sim._elev_timer >= 1:
        sim._elev_timer = 0
        sim._elev_state = "ACCELERATING"
        sim._elev_at_floor = False
    sd["speed"] = spd
    sd["door_status"] = door


def _handle_elev_accelerating(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = _clamp(spd + ACCELERATION * dt, 0, CRUISING_SPEED)
    door = "closed"
    pos += spd * direction * 0.5 * dt
    if spd >= CRUISING_SPEED * 0.9:
        sim._elev_state = "MOVING"
    sd["speed"] = spd
    sd["door_status"] = door
    sd["position"] = round(pos, 1)


def _handle_elev_moving(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = CRUISING_SPEED + random.uniform(-0.1, 0.1) * dt
    door = "closed"
    pos += spd * direction * 0.5 * dt
    if direction > 0 and pos >= target - 1.5:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
    elif direction < 0 and pos <= target + 1.5:
        sim._elev_state = "DECELERATING"
        sim._elev_timer = 0
    sd["speed"] = spd
    sd["door_status"] = door
    sd["position"] = round(pos, 1)


def _handle_elev_decelerating(
    sim: BuildingSimulator, sd: dict, dt: float,
    spd: float, pos: float, load: float, door: str,
    target: float, direction: int,
) -> None:
    spd = _clamp(spd - ACCELERATION * dt, 0, CRUISING_SPEED)
    door = "closed"
    pos += spd * direction * 0.5 * dt
    if spd <= 0.05:
        spd = 0.0
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
        sim._elev_timer = 0
        sim._elev_state = "IDLE"
        sim._elev_at_floor = True
    sd["speed"] = spd
    sd["door_status"] = door
    sd["position"] = round(pos, 1)


def _run_elevator_post_fsm(
    sim: BuildingSimulator, sd: dict, dt: float,
    prev_pos: float, pos: float, spd: float,
    load: float, door: str,
) -> None:
    pos = _clamp(pos, 0, FLOOR_COUNT * FLOOR_HEIGHT)
    current_state = sim._elev_state
    if current_state in ("IDLE", "DOOR_OPENING", "DOORS_OPEN", "DOOR_CLOSING"):
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
    if spd != 0:
        sim.door_close_attempts = 0
    if current_state == "DOOR_CLOSING" and sim._elev_timer >= 1:
        if random.random() < 0.15 * dt:
            sim.door_close_attempts += 1
    if prev_pos < FLOOR_HEIGHT and pos >= FLOOR_HEIGHT and sim._elev_direction > 0:
        sd["trip_count"] += 1
    energy = _compute_elevator_energy(load, spd, current_state, sim)
    stuck = _check_motor_stuck(spd, load, sd.get("temperature", 50.0))
    sd["position"] = round(pos, 1)
    sd["speed"] = round(spd, 1)
    sd["load"] = round(load)
    sd["door_status"] = door
    sd["energy"] = round(_clamp(energy, 0, 20), 1)
    sd["motor_stuck"] = stuck
    sim._elev_prev_position = prev_pos


def _compute_elevator_energy(
    load: float, spd: float, state: str, sim: BuildingSimulator,
) -> float:
    energy = (load / 500) * spd * 2 + 0.5
    if "elevator" in sim.protection_ends:
        energy = _clamp(energy, 0, 20)
    return energy


def _check_motor_stuck(speed: float, load: float, temperature: float) -> bool:
    return speed == 0 and (load > 700 or temperature > 90)
