import random

from apps.sensors.simulation.constants import (
    T_AMBIENT, FLOOR_COUNT, FLOOR_HEIGHT,
    CRUISING_SPEED, ACCELERATION, PASSENGER_WAIT_TICKS,
)
from apps.sensors.simulation.models import BuildingSimulator


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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
