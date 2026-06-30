from __future__ import annotations

import os
from typing import Any, Optional, TYPE_CHECKING

from apps.sensors.sensor_config import COOLDOWN_SECONDS

if TYPE_CHECKING:
    from apps.sensors.simulation.models import BuildingSimulator

SMTP_SERVER: str = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER: str = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD: str = os.environ.get("SMTP_PASSWORD", "")


def translate_device_to_spanish(device: str) -> str:
    from apps.sensors.sensor_config import DEVICE_NAMES_ES
    return DEVICE_NAMES_ES.get(device, device).capitalize()


def translate_variable_to_spanish(variable: str) -> str:
    from apps.sensors.sensor_config import VAR_NAMES
    return VAR_NAMES.get(variable, variable.replace("_", " ").title())


def get_attribute(sim: Optional['BuildingSimulator'], attr: str) -> Any:
    if sim is not None:
        return getattr(sim, attr)
    from apps.sensors.simulation import globals as _sim_globals
    return getattr(_sim_globals, attr)


def set_attribute(sim: Optional['BuildingSimulator'], attr: str, value: Any) -> None:
    if sim is not None:
        setattr(sim, attr, value)
    else:
        from apps.sensors.simulation import globals as _sim_globals
        setattr(_sim_globals, attr, value)
