"""
Módulo de simulación - Estado y lógica de generación de datos de sensores.
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
PROTECTION_HOLD_SECONDS = 8
PROTECTION_TOGGLE_INTERVAL = 8
SIMULATION_NORMAL_DURATION = 10
LOG_SIM = True
SIMULTANEOUS_FAIL_PROB = 0.3
DOOR_CLOSE_SUCCESS_PROB = 0.25
DOOR_OPEN_PROB = 0.4
MAX_DOOR_CLOSE_ATTEMPTS = 2

# Valores por defecto de sensores para inicializar cada simulador
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
# Simulador por edificio: cada BuildingSimulator tiene su propio estado
# independiente de sensores, bomba, ascensor, protecciones y alertas.
# El patrón "state-swap" permite reutilizar las funciones globales
# existentes sin modificarlas: antes de cada tick se redirigen los
# globales al simulador correcto y se restauran al terminar.
# ----------------------------------------------------------------------
class BuildingSimulator:
    """Contenedor de estado independiente por edificio."""
    def __init__(self, edificio_id: int, nombre: str, equipment_types: set = None):
        self.edificio_id = edificio_id
        self.nombre      = nombre
        self.equipment_types = equipment_types or {"bomba"}
        self.sensor_data = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
        self.has_pump     = "bomba" in self.equipment_types
        self.has_elevator = "elevador" in self.equipment_types
        self.pump_on     = self.has_pump
        self.elevator_on = self.has_elevator
        self.protection_ends: dict = {}
        self.active_alerts: dict = {}
        self.door_close_attempts: int = 0
        self.history: list = []
        self.alert_log: list = []
        self.pending_notifications: deque = deque()
        self.last_email_sent_time: float = 0.0

    def __repr__(self):
        return f"<BuildingSimulator edificio_id={self.edificio_id} nombre={self.nombre!r} eq_types={self.equipment_types}>"


# Diccionario global de simuladores: edificio_id -> BuildingSimulator
simulators: dict = {}

# Variables globales de estado que apuntan al simulador activo.
sensor_data      = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
pump_on          = True
elevator_on      = True
equipment_types  = {"bomba"}
protection_ends  = {}
active_alerts    = {}
door_close_attempts = 0
history          = []
alert_log        = []
pending_notifications = deque()
last_email_sent_time  = 0.0


# ----------------------------------------------------------------------
# Funciones de simulación
# ----------------------------------------------------------------------
def reset_critical_values(targets):
    """Resetear valores críticos asociados a los dispositivos deshabilitados."""
    global sensor_data
    if not targets:
        return
    if "pump" in targets:
        sensor_data["flow_rate"] = 25.0
        sensor_data["pressure"] = 4.0
        sensor_data["temperature"] = 50.0
        sensor_data["vibration"] = 1.5
        sensor_data["tank_level"] = 80.0
        sensor_data["voltage"] = 220.0
        sensor_data["current"] = 18.0
    if "elevator" in targets:
        sensor_data["position"] = 0
        sensor_data["speed"] = 0.0
        sensor_data["load"] = 200
        sensor_data["motor_stuck"] = False
        sensor_data["door_status"] = "closed"
        sensor_data["energy"] = 5.0
        sensor_data["temperature"] = 50.0
        global door_close_attempts
        door_close_attempts = 0


def check_motor_stuck(speed, load, temperature):
    return speed == 0 and (load > 700 or temperature > 90)


def update_sensor_data():
    global sensor_data
    if "pump" not in protection_ends and pump_on and random.random() < 0.001:
        sensor_data["flow_rate"] = 0.0
        sensor_data["pressure"] = 0.0
        sensor_data["vibration"] = 12.0
        sensor_data["temperature"] = 85.0
        sensor_data["current"] = 40.0
        logger.info("Inyectada falla aleatoria: pump")
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: pump falla -> protection_ends={protection_ends}"
            )
        if (
            "elevator" not in protection_ends
            and elevator_on
            and random.random() < SIMULTANEOUS_FAIL_PROB
        ):
            sensor_data["speed"] = 0.0
            sensor_data["load"] = 950
            sensor_data["motor_stuck"] = True
            sensor_data["door_status"] = "closed"
            sensor_data["energy"] = 12.0
            sensor_data["temperature"] = 95.0
            logger.info("Inyectada falla simultánea: elevator")
            if LOG_SIM:
                print(
                    f"[SIM] {time.strftime('%H:%M:%S')} INYECCION-SIMULT: elevator falla -> protection_ends={protection_ends}"
                )
    if "elevator" not in protection_ends and elevator_on and random.random() < 0.001:
        sensor_data["speed"] = 0.0
        sensor_data["load"] = 950
        sensor_data["motor_stuck"] = True
        sensor_data["door_status"] = "closed"
        sensor_data["energy"] = 12.0
        sensor_data["temperature"] = 95.0
        logger.info("Inyectada falla aleatoria: elevator")
        if LOG_SIM:
            print(
                f"[SIM] {time.strftime('%H:%M:%S')} INYECCION: elevator falla -> protection_ends={protection_ends}"
            )
        if (
            "pump" not in protection_ends
            and pump_on
            and random.random() < SIMULTANEOUS_FAIL_PROB
        ):
            sensor_data["flow_rate"] = 0.0
            sensor_data["pressure"] = 0.0
            sensor_data["vibration"] = 12.0
            sensor_data["temperature"] = 85.0
            sensor_data["current"] = 40.0
            logger.info("Inyectada falla simultánea: pump")
            if LOG_SIM:
                print(
                    f"[SIM] {time.strftime('%H:%M:%S')} INYECCION-SIMULT: pump falla -> protection_ends={protection_ends}"
                )
    pump_protected = "pump" in protection_ends or not pump_on
    elevator_protected = "elevator" in protection_ends or not elevator_on
    if not pump_on:
        sensor_data["flow_rate"] = 0.0
        sensor_data["pressure"] = 0.0
        sensor_data["vibration"] = 0.0
        sensor_data["current"] = 0.0
        sensor_data["temperature"] = 20.0
        sensor_data["voltage"] = 220.0
    else:
        if "pump" in protection_ends:
            sensor_data["flow_rate"] = round(max(0, min(60, sensor_data["flow_rate"])), 1)
            sensor_data["pressure"] = round(max(0, min(12, sensor_data["pressure"])), 1)
            sensor_data["temperature"] = round(
                max(20, min(130, sensor_data["temperature"])), 1
            )
            sensor_data["vibration"] = round(max(0, min(15, sensor_data["vibration"])), 1)
            sensor_data["tank_level"] = round(
                max(0, min(100, sensor_data["tank_level"])), 1
            )
            sensor_data["voltage"] = round(max(180, min(260, sensor_data["voltage"])), 1)
            sensor_data["current"] = round(max(0, min(70, sensor_data["current"])), 1)
        else:
            fd = sensor_data["flow_rate"] + random.uniform(-1.5, 1.5)
            if random.random() < 0.05:
                fd += random.uniform(5, 15)
            sensor_data["flow_rate"] = round(max(0, min(60, fd)), 1)

            p = (
                sensor_data["pressure"]
                + random.uniform(-0.3, 0.3)
                + (sensor_data["flow_rate"] - 20) * 0.02
            )
            sensor_data["pressure"] = round(max(0, min(12, p)), 1)

            t = (
                sensor_data["temperature"]
                + random.uniform(-0.5, 1.0)
                + max(0, (sensor_data["pressure"] - 5) * 0.2)
            )
            if random.random() < 0.03:
                t += random.uniform(5, 20)
            sensor_data["temperature"] = round(max(20, min(130, t)), 1)

            v = (
                sensor_data["vibration"]
                + random.uniform(-0.3, 0.5)
                + (sensor_data["flow_rate"] / 30)
                + (max(0, sensor_data["temperature"] - 70) / 20)
            )
            sensor_data["vibration"] = round(max(0, min(15, v)), 1)

            lvl = sensor_data["tank_level"] - sensor_data["flow_rate"] * 0.1
            if random.random() < 0.1:
                lvl += random.uniform(5, 15)
            sensor_data["tank_level"] = round(max(0, min(100, lvl)), 1)

            volt = sensor_data["voltage"] + random.uniform(-3, 3)
            if random.random() < 0.02:
                volt += random.uniform(-20, 20)
            sensor_data["voltage"] = round(max(180, min(260, volt)), 1)

            curr = sensor_data["current"]
            curr = round(
                max(
                    0,
                    min(
                        70,
                        curr + random.uniform(-1, 1) + (sensor_data["load"] / 100) * 0.1
                    ),
                ),
                1,
            )
            sensor_data["current"] = curr

    if not elevator_on:
        sensor_data["speed"] = 0.0
        sensor_data["position"] = 0.0
        sensor_data["load"] = 0
        sensor_data["door_status"] = "closed"
        sensor_data["energy"] = 0.0
        sensor_data["motor_stuck"] = False
        global door_close_attempts
        door_close_attempts = 0
    else:
        prev_pos = sensor_data["position"]
        prev_door = sensor_data["door_status"]
        pos = prev_pos
        spd = sensor_data["speed"]
        if random.random() < 0.3:
            spd = random.choice([0, random.uniform(0.5, 2.5)])
        pos += spd * 2
        if pos > 20:
            pos, spd = 20, 0
        if pos < 0:
            pos, spd = 0, 0
        at_floor = abs(pos - round(pos)) < 0.05
        if spd != 0:
            sensor_data["door_status"] = "closed"
            door_close_attempts = 0
        else:
            if not at_floor:
                sensor_data["door_status"] = "closed"
                door_close_attempts = 0
            else:
                if prev_door == "open":
                    if door_close_attempts < MAX_DOOR_CLOSE_ATTEMPTS:
                        if random.random() < DOOR_CLOSE_SUCCESS_PROB:
                            sensor_data["door_status"] = "closed"
                        else:
                            sensor_data["door_status"] = "open"
                        door_close_attempts += 1
                        if LOG_SIM:
                            print(
                                f"[SIM] {time.strftime('%H:%M:%S')} DOORS_EVENT: increment attempts -> {door_close_attempts}"
                            )
                    else:
                        sensor_data["door_status"] = "open"
                elif door_close_attempts >= MAX_DOOR_CLOSE_ATTEMPTS:
                    sensor_data["door_status"] = "open"
                else:
                    if random.random() < DOOR_OPEN_PROB:
                        sensor_data["door_status"] = "open"
                    else:
                        sensor_data["door_status"] = "closed"
        sensor_data["load"] = round(
            max(
                0,
                min(
                    1200,
                    sensor_data["load"]
                    + (random.randint(-100, 150) if random.random() < 0.2 else 0),
                ),
            )
        )
        if random.random() < 0.1:
            sensor_data["trip_count"] += 1
        if abs(pos - prev_pos) > 0.1 or spd != 0:
            if door_close_attempts != 0 and LOG_SIM:
                print(
                    f"[SIM] {time.strftime('%H:%M:%S')} DOORS_EVENT: reset attempts (pos change or movement) -> was {door_close_attempts}"
                )
            door_close_attempts = 0
        sensor_data["position"] = round(pos, 1)
        sensor_data["speed"] = round(spd, 1)
        if "elevator" in protection_ends:
            sensor_data["energy"] = round(max(0, min(20, sensor_data["energy"])), 1)
        else:
            energy = (sensor_data["load"] / 500) * spd * 2 + random.uniform(0.5, 2)
            sensor_data["energy"] = round(max(0, min(20, energy)), 1)
        stuck = check_motor_stuck(
            sensor_data["speed"], sensor_data["load"], sensor_data["temperature"]
        )
        sensor_data["motor_stuck"] = stuck
