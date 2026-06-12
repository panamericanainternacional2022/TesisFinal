import os
from typing import Any, Optional

from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.sensor_config import DEVICE_NAMES_ES, VAR_NAMES

SMTP_SERVER: str = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER: str = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")

COOLDOWN_SECONDS: int = 300


def translate_device_to_spanish(device: str) -> str:
    return DEVICE_NAMES_ES.get(device, device)


def translate_variable_to_spanish(variable: str) -> str:
    return VAR_NAMES.get(variable, variable.replace("_", " ").title())


def get_attribute(sim: Optional[BuildingSimulator], attr: str) -> Any:
    if sim is not None:
        return getattr(sim, attr)
    from apps.sensors.simulation import globals as _sim_globals
    return getattr(_sim_globals, attr)


def set_attribute(sim: Optional[BuildingSimulator], attr: str, value: Any) -> None:
    if sim is not None:
        setattr(sim, attr, value)
    else:
        from apps.sensors.simulation import globals as _sim_globals
        setattr(_sim_globals, attr, value)
