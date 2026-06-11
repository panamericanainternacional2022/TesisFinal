"""
Módulo de simulación - Estado y lógica de generación de datos de sensores.
Modelo físico con relaciones causales entre variables.
"""

import random
import time
import logging
from collections import deque

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Constantes de simulación
# ----------------------------------------------------------------------
RATIONING_THRESHOLD = 8.0
MAX_HISTORY_SIZE = 500
MAX_LOG_ENTRIES = 100
PROTECTION_HOLD_SECONDS = 30
PROTECTION_TOGGLE_INTERVAL = 8
SIMULATION_NORMAL_DURATION = 10
LOG_SIM = True
SIMULTANEOUS_FAIL_PROB = 0.3
DOOR_CLOSE_SUCCESS_PROB = 0.25
DOOR_OPEN_PROB = 0.4
MAX_DOOR_CLOSE_ATTEMPTS = 2

# Constantes del modelo físico de bomba
PUMP_P0 = 7.0            # presión máxima (shut-off head) en bar
PUMP_K = 0.012           # coeficiente de pérdida: P = P0 - K * Q²
TANK_AREA = 2.5          # área del tanque en m² (para cálculo de nivel)
T_AMBIENT = 22.0         # temperatura ambiente en °C
TANK_CAPACITY = 100.0    # capacidad total del tanque en %

# Constantes del modelo de elevador
FLOOR_COUNT = 20
CRUISING_SPEED = 2.0     # m/s
ACCELERATION = 0.8        # m/s² por tick
FLOOR_HEIGHT = 3.5        # metros por piso
DOOR_CYCLE_TICKS = 3      # ticks que dura puerta abriendo/cerrando
PASSENGER_WAIT_TICKS = 8  # ticks esperando pasajeros

# Valores por defecto de sensores
DEFAULT_SENSOR_DATA = {
    "flow_rate": 15.0,
    "pressure": 4.0,
    "temperature": 50.0,
    "vibration": 2.0,
    "tank_level": 80.0,
    "position": 0,
    "speed": 0.0,
    "load": 200,
    "trip_count": 5000,
    "door_status": "closed",
    "energy": 5.0,
    "voltage": 220.0,
    "current": 20.0,
    "motor_stuck": False,
}


# ----------------------------------------------------------------------
# Simulador por edificio
# ----------------------------------------------------------------------
class BuildingSimulator:
    """Contenedor de estado independiente por edificio."""
    def __init__(self, edificio_id: int, nombre: str, equipment_types: set = None):
        self.edificio_id = edificio_id
        self.nombre      = nombre
        self.equipment_types = equipment_types or set()
        self.sensor_data = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
        self.has_pump     = "bomba" in self.equipment_types
        self.has_elevator = "elevador" in self.equipment_types
        self.pump_on     = self.has_pump
        self.elevator_on = self.has_elevator
        self.protection_ends: dict = {}
        self.active_alerts: dict = {}
        self.door_close_attempts: int = 0
        self.history: list = []
        self.pending_notifications: deque = deque()
        self.last_email_sent_time: float = 0.0
        self.alert_enabled: bool = True

        # --- Control del simulador ---
        self.sim_paused = False
        self.sim_speed = 1.0
        self.sim_faults: dict = {}        # variable -> tipo de falla

        # --- Estado del modelo de bomba ---
        self._pump_demand = 20.0           # demanda base (L/s)
        self._pump_refill_timer = 0
        self._pump_failure_timer = 0
        self._pump_failure_active = False
        self._pump_failure_var = None

        # --- Estado del modelo de elevador (FSM) ---
        self._elev_state = "IDLE"
        self._elev_timer = 0
        self._elev_target_floor = random.randint(1, FLOOR_COUNT)
        self._elev_direction = 1
        self._elev_at_floor = True
        self._elev_prev_position = 0

    def __repr__(self):
        return f"<BuildingSimulator edificio_id={self.edificio_id} nombre={self.nombre!r} eq_types={self.equipment_types}>"


# Diccionario global de simuladores: edificio_id -> BuildingSimulator
simulators: dict = {}

# Variables globales de estado que apuntan al simulador activo.
sensor_data      = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
pump_on          = False
elevator_on      = False
equipment_types  = set()
protection_ends  = {}
active_alerts    = {}
door_close_attempts = 0
history          = []
pending_notifications = deque()
last_email_sent_time  = 0.0

# Variables de estado del control del simulador (globales, se sincronizan igual)
sim_paused = False
sim_speed = 1.0


# ----------------------------------------------------------------------
# Funciones de ayuda
# ----------------------------------------------------------------------
def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _rand_walk(current, step, lo, hi):
    return _clamp(current + random.uniform(-step, step), lo, hi)


# ----------------------------------------------------------------------
# Modelo físico de BOMBA
# ----------------------------------------------------------------------
def _update_pump(sim: BuildingSimulator):
    sd = sim.sensor_data
    dt = sim.sim_speed

    sim._pump_refill_timer += dt
    if sim._pump_refill_timer >= 15:
        sim._pump_refill_timer = 0
        sd["tank_level"] = _clamp(sd["tank_level"] + random.uniform(10, 25), 0, 100)

    has_fault = "pump" in sim.sim_faults
    fault_type = sim.sim_faults.get("pump")

    if not sim.pump_on or "pump" in sim.protection_ends:
        sd["flow_rate"] = 0.0
        sd["pressure"] = 0.0
        sd["vibration"] = 0.0
        sd["current"] = 0.0
        sd["temperature"] = _clamp(sd["temperature"] - 0.5 * dt, T_AMBIENT, 130)
        sd["voltage"] = _clamp(sd["voltage"] + random.uniform(-1, 1) * dt, 180, 260)
        return

    if has_fault:
        if fault_type == "dry_run":
            sd["flow_rate"] = _clamp(sd["flow_rate"] - 1.5 * dt, 0, 5)
            sd["pressure"] = _clamp(sd["pressure"] - 0.3 * dt, 0, 2)
            sd["temperature"] = _clamp(sd["temperature"] + 1.5 * dt, 0, 130)
            sd["vibration"] = _clamp(sd["vibration"] + 0.5 * dt, 0, 15)
            sd["tank_level"] = _clamp(sd["tank_level"] - 0.5 * dt, 0, 100)

        elif fault_type == "blocked_discharge":
            sd["flow_rate"] = _clamp(sd["flow_rate"] - 2.0 * dt, 0, 3)
            sd["pressure"] = _clamp(sd["pressure"] + 1.0 * dt, 0, 12)
            sd["vibration"] = _clamp(sd["vibration"] + 0.8 * dt, 0, 15)
            sd["temperature"] = _clamp(sd["temperature"] + 0.8 * dt, 0, 130)
            sd["tank_level"] = _clamp(sd["tank_level"] + 0.1 * dt, 0, 100)

        elif fault_type == "pipe_burst":
            sd["flow_rate"] = _clamp(sd["flow_rate"] + 3.0 * dt, 0, 60)
            sd["pressure"] = _clamp(sd["pressure"] - 0.8 * dt, 0, 2)
            sd["vibration"] = _clamp(sd["vibration"] + 0.6 * dt, 0, 15)
            sd["tank_level"] = _clamp(sd["tank_level"] - 2.0 * dt, 0, 100)

        elif fault_type == "cavitation":
            sd["flow_rate"] = _clamp(sd["flow_rate"] + random.uniform(-5, 5) * dt, 0, 60)
            sd["vibration"] = _clamp(sd["vibration"] + random.uniform(0.5, 2.0) * dt, 0, 15)
            sd["pressure"] = _clamp(sd["pressure"] + random.uniform(-0.5, 0.5) * dt, 0, 12)

        elif fault_type == "overheat":
            sd["temperature"] = _clamp(sd["temperature"] + 2.0 * dt, 0, 130)
            sd["vibration"] = _clamp(sd["vibration"] + 0.3 * dt, 0, 15)

        elif fault_type == "power_surge":
            sd["voltage"] = _clamp(sd["voltage"] + 30 * dt, 0, 350)
            sd["current"] = _clamp(sd["current"] + 10 * dt, 0, 70)

        elif fault_type == "power_outage":
            sd["voltage"] = _clamp(sd["voltage"] - 50 * dt, 0, 10)
            sd["current"] = 0.0
            sd["flow_rate"] = 0.0
            sd["pressure"] = 0.0
            return

        sd["flow_rate"] = round(_clamp(sd["flow_rate"], 0, 60), 1)
        sd["pressure"] = round(_clamp(sd["pressure"], 0, 12), 1)
        sd["temperature"] = round(_clamp(sd["temperature"], T_AMBIENT, 130), 1)
        sd["vibration"] = round(_clamp(sd["vibration"], 0, 15), 1)
        sd["voltage"] = round(sd["voltage"], 1)
        sd["current"] = round(_clamp(sd["current"], 0, 70), 1)
        return

    # --- Operación normal de la bomba ---
    sim._pump_demand = _rand_walk(sim._pump_demand, 0.5 * dt, 8, 25)
    if random.random() < 0.02 * dt:
        sim._pump_demand = _clamp(sim._pump_demand + random.uniform(8, 15), 8, 35)

    flow = sim._pump_demand
    pressure = max(0.5, PUMP_P0 - PUMP_K * flow ** 2)
    pressure += random.uniform(-0.2, 0.2) * dt

    temp = sd["temperature"]
    temp += (flow * pressure * 0.01 - 0.3) * dt
    temp += random.uniform(-0.3, 0.3) * dt
    if sd["tank_level"] < 10:
        temp += 0.5 * dt

    vib = 0.5 + flow / 25 + max(0, temp - 65) / 40
    vib += random.uniform(-0.2, 0.3) * dt

    tank = sd["tank_level"] - flow * 0.08 * dt
    if random.random() < 0.02 * dt:
        tank += random.uniform(5, 15)

    volt = 220.0 + random.uniform(-2, 2) * dt
    curr = flow * pressure / (volt * 0.75) + random.uniform(-0.5, 0.5) * dt

    sd["flow_rate"] = round(_clamp(flow, 0, 60), 1)
    sd["pressure"] = round(_clamp(pressure, 0, 12), 1)
    sd["temperature"] = round(_clamp(temp, T_AMBIENT, 130), 1)
    sd["vibration"] = round(_clamp(vib, 0, 15), 1)
    sd["tank_level"] = round(_clamp(tank, 0, 100), 1)
    sd["voltage"] = round(_clamp(volt, 180, 260), 1)
    sd["current"] = round(_clamp(curr, 0, 70), 1)


# ----------------------------------------------------------------------
# Modelo de ELEVADOR (máquina de estados finitos)
# ----------------------------------------------------------------------
def _update_elevator(sim: BuildingSimulator):
    sd = sim.sensor_data
    dt = sim.sim_speed

    if not sim.elevator_on or "elevator" in sim.protection_ends:
        sd["speed"] = 0.0
        sd["position"] = round(sd["position"], 1)
        sd["load"] = 0
        sd["door_status"] = "closed"
        sd["energy"] = 0.0
        sd["motor_stuck"] = False
        sim.door_close_attempts = 0
        sim._elev_state = "IDLE"
        return

    has_fault = "elevator" in sim.sim_faults
    fault_type = sim.sim_faults.get("elevator")

    if has_fault and fault_type == "motor_stuck":
        sd["speed"] = 0.0
        sd["motor_stuck"] = True
        sd["load"] = _clamp(sd["load"] + 5 * dt, 0, 1200)
        sd["door_status"] = "closed"
        sd["energy"] = _clamp(sd["energy"] + 0.5 * dt, 0, 20)
        sd["temperature"] = _clamp(sd["temperature"] + 0.5 * dt, T_AMBIENT, 130)
        return

    if has_fault and fault_type == "door_blocked":
        sd["door_status"] = "open"
        sim.door_close_attempts += 1
        sd["motor_stuck"] = False
        sd["speed"] = 0.0
        sd["energy"] = _clamp(sd["energy"] - 0.1 * dt, 0, 20)
        return

    if has_fault and fault_type == "overspeed":
        sd["speed"] = _clamp(sd["speed"] + 0.5 * dt, 0, 6)
        sd["position"] = _clamp(sd["position"] + sd["speed"] * dt * 0.5, 0, FLOOR_COUNT * FLOOR_HEIGHT)
        sd["door_status"] = "closed"
        sd["motor_stuck"] = False
        sd["load"] = _clamp(sd["load"] + random.uniform(-10, 10) * dt, 0, 1200)
        sd["energy"] = sd["load"] * sd["speed"] * 0.004 + random.uniform(0.2, 0.5) * dt
        return

    # --- Operación normal del elevador (FSM) ---
    sim._elev_timer += dt
    prev_pos = sd["position"]
    pos = sd["position"]
    spd = sd["speed"]
    load = sd["load"]
    door = sd["door_status"]

    state = sim._elev_state
    target = sim._elev_target_floor * FLOOR_HEIGHT
    direction = sim._elev_direction

    at_floor = abs(pos - round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT) < 0.15
    floor_num = round(pos / FLOOR_HEIGHT)

    if state == "IDLE":
        spd = 0.0
        door = "closed"
        if sim._elev_timer >= random.uniform(2, 5):
            sim._elev_timer = 0
            sim._elev_target_floor = random.randint(0, FLOOR_COUNT)
            while sim._elev_target_floor == floor_num:
                sim._elev_target_floor = random.randint(0, FLOOR_COUNT)
            sim._elev_direction = 1 if sim._elev_target_floor > floor_num else -1
            sim._elev_state = "DOOR_OPENING"

    elif state == "DOOR_OPENING":
        spd = 0.0
        door = "opening"
        if sim._elev_timer >= 1:
            sim._elev_timer = 0
            load = _clamp(load + random.randint(-50, 150), 0, 1200)
            sim._elev_state = "DOORS_OPEN"

    elif state == "DOORS_OPEN":
        spd = 0.0
        door = "open"
        if sim._elev_timer >= PASSENGER_WAIT_TICKS / max(sim.sim_speed, 0.1):
            sim._elev_timer = 0
            load = _clamp(load + random.randint(-100, 100), 0, 1200)
            sim._elev_state = "DOOR_CLOSING"

    elif state == "DOOR_CLOSING":
        spd = 0.0
        door = "closing"
        if sim._elev_timer >= 1:
            sim._elev_timer = 0
            sim._elev_state = "ACCELERATING"
            sim._elev_at_floor = False

    elif state == "ACCELERATING":
        spd = _clamp(spd + ACCELERATION * dt, 0, CRUISING_SPEED)
        door = "closed"
        pos += spd * direction * 0.5 * dt
        if spd >= CRUISING_SPEED * 0.9:
            sim._elev_state = "MOVING"

    elif state == "MOVING":
        spd = CRUISING_SPEED + random.uniform(-0.1, 0.1) * dt
        door = "closed"
        pos += spd * direction * 0.5 * dt
        if direction > 0 and pos >= target - 1.5:
            sim._elev_state = "DECELERATING"
            sim._elev_timer = 0
        elif direction < 0 and pos <= target + 1.5:
            sim._elev_state = "DECELERATING"
            sim._elev_timer = 0

    elif state == "DECELERATING":
        spd = _clamp(spd - ACCELERATION * dt, 0, CRUISING_SPEED)
        door = "closed"
        pos += spd * direction * 0.5 * dt
        if spd <= 0.05:
            spd = 0.0
            pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT
            sim._elev_timer = 0
            sim._elev_state = "IDLE"
            sim._elev_at_floor = True

    pos = _clamp(pos, 0, FLOOR_COUNT * FLOOR_HEIGHT)

    if state in ("IDLE", "DOOR_OPENING", "DOORS_OPEN", "DOOR_CLOSING"):
        pos = round(pos / FLOOR_HEIGHT) * FLOOR_HEIGHT

    if spd != 0:
        sim.door_close_attempts = 0

    if state == "DOOR_CLOSING" and sim._elev_timer >= 1:
        if random.random() < 0.15 * dt:
            sim.door_close_attempts += 1

    if prev_pos < FLOOR_HEIGHT and pos >= FLOOR_HEIGHT and direction > 0:
        sd["trip_count"] += 1

    energy = (load / 500) * spd * 2 + 0.5
    if "elevator" in sim.protection_ends:
        energy = _clamp(energy, 0, 20)

    stuck = check_motor_stuck(spd, load, sd.get("temperature", 50.0))

    sd["position"] = round(pos, 1)
    sd["speed"] = round(spd, 1)
    sd["load"] = round(load)
    sd["door_status"] = door
    sd["energy"] = round(_clamp(energy, 0, 20), 1)
    sd["motor_stuck"] = stuck

    sim._elev_prev_position = prev_pos


# ----------------------------------------------------------------------
# Funciones de simulación (API pública)
# ----------------------------------------------------------------------
def reset_critical_values(targets, sim=None):
    """Resetear valores críticos asociados a los dispositivos deshabilitados."""
    if sim is None:
        sim = next(iter(simulators.values()), None)
    if sim is None or not targets:
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


def check_motor_stuck(speed, load, temperature):
    return speed == 0 and (load > 700 or temperature > 90)


def update_sensor_data(active_sim=None):
    """Actualiza los datos de sensores usando modelos físicos.
    Se ejecuta por cada tick de simulación desde _run_sim_tick.
    """
    if active_sim is None:
        active_sim = next(iter(simulators.values()), None)
    if active_sim is None:
        return

    dt = active_sim.sim_speed
    if active_sim.sim_paused:
        return

    if active_sim.has_pump:
        _update_pump(active_sim)
    if active_sim.has_elevator:
        _update_elevator(active_sim)

    if not active_sim.sim_faults:
        if "pump" not in active_sim.protection_ends and active_sim.pump_on and random.random() < 0.001 * dt:
            _inject_random_pump_fault(active_sim)
        if "elevator" not in active_sim.protection_ends and active_sim.elevator_on and random.random() < 0.001 * dt:
            _inject_random_elevator_fault(active_sim)


def _inject_random_pump_fault(sim):
    fault_type = random.choice(["cavitation", "overheat", "blocked_discharge"])
    sim.sim_faults["pump"] = fault_type
    logger.info("Falla aleatoria de bomba inyectada (vía sim_faults): %s", fault_type)
    if LOG_SIM:
        print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: pump {fault_type}")

    if "elevator" not in sim.protection_ends and sim.elevator_on and random.random() < SIMULTANEOUS_FAIL_PROB:
        _inject_random_elevator_fault(sim)


def _inject_random_elevator_fault(sim):
    sim.sim_faults["elevator"] = "motor_stuck"
    logger.info("Falla aleatoria de elevador inyectada (vía sim_faults): motor_stuck")
    if LOG_SIM:
        print(f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: elevator motor_stuck")

    if "pump" not in sim.protection_ends and sim.pump_on and random.random() < SIMULTANEOUS_FAIL_PROB:
        _inject_random_pump_fault(sim)


# ----------------------------------------------------------------------
# Control del simulador (API para rutas)
# ----------------------------------------------------------------------
def inject_fault(edificio_id: int, device: str, fault_type: str):
    """Inyecta una falla específica en un dispositivo de un edificio."""
    sim = simulators.get(edificio_id)
    if not sim:
        return False, "Edificio no encontrado"
    if device not in ("pump", "elevator"):
        return False, "Dispositivo debe ser 'pump' o 'elevator'"
    if (device == "pump" and not sim.has_pump) or (device == "elevator" and not sim.has_elevator):
        return False, f"El edificio no tiene {device}"

    valid_faults = {
        "pump": ("dry_run", "blocked_discharge", "pipe_burst", "cavitation", "overheat", "power_surge", "power_outage"),
        "elevator": ("motor_stuck", "door_blocked", "overspeed"),
    }
    if fault_type not in valid_faults[device]:
        return False, f"Falla inválida para {device}: {fault_type}"

    sim.sim_faults[device] = fault_type
    logger.info(f"Falla inyectada: edificio={edificio_id}, device={device}, tipo={fault_type}")
    return True, f"Falla '{fault_type}' inyectada en {device}"


def clear_fault(edificio_id: int, device: str = None):
    """Limpia fallas de un dispositivo o todas."""
    sim = simulators.get(edificio_id)
    if not sim:
        return False, "Edificio no encontrado"
    if device:
        sim.sim_faults.pop(device, None)
        msg = f"Falla limpiada para {device}"
    else:
        sim.sim_faults.clear()
        msg = "Todas las fallas limpiadas"

    # Restaurar valores gradualmente si estaba en falla
    sd = sim.sensor_data
    if device in (None, "pump"):
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
    return True, msg


def reset_simulator(edificio_id: int):
    """Reinicia el simulador de un edificio al estado normal."""
    sim = simulators.get(edificio_id)
    if not sim:
        return False, "Edificio no encontrado"
    sim.sensor_data = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
    sim.pump_on = sim.has_pump
    sim.elevator_on = sim.has_elevator
    sim.protection_ends.clear()
    sim.active_alerts.clear()
    sim.door_close_attempts = 0
    sim.history.clear()
    sim.pending_notifications.clear()
    sim.sim_faults.clear()
    sim.sim_paused = False
    sim.sim_speed = 1.0
    sim._pump_demand = 15.0
    sim._pump_refill_timer = 0
    sim._elev_state = "IDLE"
    sim._elev_timer = 0
    sim._elev_target_floor = random.randint(1, FLOOR_COUNT)
    sim._elev_direction = 1
    sim._elev_at_floor = True
    logger.info(f"Simulador reiniciado: edificio={edificio_id}")
    return True, "Simulador reiniciado al estado normal"
