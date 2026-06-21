import random
from collections import deque

from apps.sensors.simulation.constants import FLOOR_COUNT, DEFAULT_SENSOR_DATA


class BuildingSimulator:
    def __init__(self, edificio_id: int, nombre: str, equipment_types: set = None, floors: int = 20):
        self.edificio_id: int = edificio_id
        self.nombre: str = nombre
        self.equipment_types: set = equipment_types or set()
        self.floors: int = floors
        self.sensor_data: dict = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
        self.has_pump: bool = "bomba" in self.equipment_types
        self.has_elevator: bool = "elevador" in self.equipment_types
        self.pump_on: bool = self.has_pump
        self.elevator_on: bool = self.has_elevator
        self.protection_ends: dict = {}
        self.active_alerts: dict = {}
        self.door_close_attempts: int = 0
        self.history: list = []
        self.pending_notifications: deque = deque()
        self.last_email_sent_time: float = 0.0
        self.alert_enabled: bool = True

        self.sim_paused: bool = False
        self.sim_speed: float = 1.0
        self.sim_faults: dict = {}
        self.fault_injected_at: dict = {}

        self._pump_demand: float = 20.0
        self._pump_refill_timer: float = 0
        self._pump_failure_timer: float = 0
        self._pump_failure_active: bool = False
        self._pump_failure_var = None

        self._elev_state: str = "IDLE"
        self._elev_timer: float = 0
        self._elev_target_floor: int = random.randint(1, floors)
        self._elev_direction: int = 1
        self._elev_at_floor: bool = True
        self._elev_prev_position: float = 0
        self._elev_position_meters: float = float(self.sensor_data.get("position", 0.0) * 3.5)

    def __repr__(self) -> str:
        return (
            f"<BuildingSimulator edificio_id={self.edificio_id} "
            f"nombre={self.nombre!r} eq_types={self.equipment_types}>"
        )
