"""
Configuración del sistema de monitoreo.
Contiene los umbrales de riesgo y configuración general.
No confundir con front/sensor_config.py (nombres y unidades de sensores).
"""

DEFAULT_THRESHOLDS = {
    "flow_rate": {"direction": "higher", "low": 20, "medium": 35, "high": 45},
    "pressure": {"direction": "higher", "low": 5, "medium": 7, "high": 9},
    "temperature": {"direction": "higher", "low": 70, "medium": 85, "high": 100},
    "vibration": {"direction": "higher", "low": 4, "medium": 7, "high": 10},
    "tank_level": {"direction": "lower", "low": 30, "medium": 15, "high": 5},
    "speed": {"direction": "higher", "low": 1.5, "medium": 2.5, "high": 3.5},
    "load": {"direction": "higher", "low": 400, "medium": 700, "high": 900},
    "trip_count": {"direction": "higher", "low": 10000, "medium": 20000, "high": 30000},
    "energy": {"direction": "higher", "low": 8, "medium": 12, "high": 15},
    "voltage": {"direction": "range", "low": 200, "high": 240},
    "current": {"direction": "higher", "low": 30, "medium": 40, "high": 50},
}

thresholds = DEFAULT_THRESHOLDS.copy()
