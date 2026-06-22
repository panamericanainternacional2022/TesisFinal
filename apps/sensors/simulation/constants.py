from apps.sensors.sensor_config import RATIONING_THRESHOLD  # noqa: F401
MAX_HISTORY_SIZE: int = 500
MAX_LOG_ENTRIES: int = 100
PROTECTION_HOLD_SECONDS: int = 30
PROTECTION_TOGGLE_INTERVAL: int = 8
SIMULATION_NORMAL_DURATION: int = 10
LOG_SIM: bool = True
SIMULTANEOUS_FAIL_PROB: float = 0.3
DOOR_CLOSE_SUCCESS_PROB: float = 0.25
DOOR_OPEN_PROB: float = 0.4
MAX_DOOR_CLOSE_ATTEMPTS: int = 2
FAULT_AUTO_CLEAR_SECONDS: int = 120
RANDOM_FAULT_PROB: float = 0.003

PUMP_P0: float = 7.0
PUMP_K: float = 0.012
TANK_AREA: float = 2.5
T_AMBIENT: float = 22.0
TANK_CAPACITY: float = 100.0

FLOOR_COUNT: int = 20
CRUISING_SPEED: float = 2.0
ACCELERATION: float = 0.8
FLOOR_HEIGHT: float = 3.5
DOOR_CYCLE_TICKS: int = 3
PASSENGER_WAIT_TICKS: int = 8

DEFAULT_SENSOR_DATA: dict = {
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

# ─── Límites de velocidad de simulación ────────────────────────────────
MIN_SIM_SPEED: float = 0.1
MAX_SIM_SPEED: float = 10.0

# ─── Parámetros de simulación de bombas ────────────────────────────────
REFILL_TIMER_TICKS: int = 15          # Intervalo entre recargas de tanque

# ─── Umbrales de detección de fallas en elevador ───────────────────────
ELEVATOR_LOAD_ALERT: float = 700.0
ELEVATOR_TEMP_ALERT: float = 90.0

# ─── Valores de recuperación post-falla para clear_fault ───────────────
CLEAR_FAULT_MIN_FLOW: float = 15.0
CLEAR_FAULT_MIN_PRESSURE: float = 3.0
CLEAR_FAULT_MAX_VIBRATION: float = 5.0
CLEAR_FAULT_VOLTAGE_LOW: float = 210.0
CLEAR_FAULT_VOLTAGE_HIGH: float = 230.0
CLEAR_FAULT_MAX_LOAD: float = 500.0

# Valores seguros post-falla (usados en reset_critical_values).
# Son deliberadamente distintos de DEFAULT_SENSOR_DATA para restaurar un
# estado operativo conservador después de limpiar una falla.
SAFE_RESET_VALUES: dict = {
    "flow_rate": 25.0,
    "pressure": 4.0,
    "temperature": 50.0,
    "vibration": 1.5,
    "tank_level": 80.0,
    "position": 0,
    "speed": 0.0,
    "load": 200,
    "motor_stuck": False,
    "door_status": "closed",
    "energy": 5.0,
    "voltage": 220.0,
    "current": 18.0,
}
