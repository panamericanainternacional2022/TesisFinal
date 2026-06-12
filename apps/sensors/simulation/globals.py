from collections import deque

from apps.sensors.simulation.constants import DEFAULT_SENSOR_DATA
from apps.sensors.simulation.models import BuildingSimulator


simulators: dict[int, BuildingSimulator] = {}

sensor_data: dict = {k: v for k, v in DEFAULT_SENSOR_DATA.items()}
pump_on: bool = False
elevator_on: bool = False
equipment_types: set = set()
protection_ends: dict = {}
active_alerts: dict = {}
door_close_attempts: int = 0
history: list = []
pending_notifications: deque = deque()
last_email_sent_time: float = 0.0
sim_paused: bool = False
sim_speed: float = 1.0
