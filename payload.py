"""
Módulo de construcción del payload en vivo para streaming SSE/WebSocket.
Contiene titleize_name y build_live_payload.
"""

import time
import logging

from front.sensor_config import STATS_VARS, PUMP_VARS, ELEVATOR_VARS
from risk import classify_risk

logger = logging.getLogger(__name__)


def titleize_name(text):
    return " ".join(word.capitalize() for word in text.replace("_", " ").split())


def build_live_payload():
    from simulation import (
        sensor_data, protection_ends, history, alert_log,
        door_close_attempts, pump_on, elevator_on, equipment_types,
        RATIONING_THRESHOLD,
    )
    from alerts import generate_recommendations
    from thresholds import thresholds
    from entry import alert_enabled, active_edificio_id, DJANGO_CONNECTED

    stats = {}
    for var in STATS_VARS:
        vals = [
            r["value"]
            for r in history
            if r["variable"] == var and isinstance(r["value"], (int, float))
        ]
        if vals:
            stats[var] = {
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }

    _relevant_vars = set()
    if "bomba" in equipment_types:
        _relevant_vars.update(PUMP_VARS)
    if "elevador" in equipment_types:
        _relevant_vars.update(ELEVATOR_VARS)
    _relevant_vars.update(["rationing", "auto_protection", "protection_pump", "protection_elevator"])

    sensors = []
    for var, value in sensor_data.items():
        if var not in _relevant_vars:
            continue
        if var == "motor_stuck":
            risk, color = ("Crítico", "red") if value else ("Bajo", "green")
        else:
            risk, color = classify_risk(var, value)
        sensors.append(
            {
                "id": var,
                "nombre": titleize_name(var),
                "riesgo": risk,
                "color": color,
            }
        )

    recommendations = generate_recommendations(sensor_data, stats)

    _pump_status = None
    _elevator_status = None
    if DJANGO_CONNECTED and active_edificio_id:
        try:
            from front.models import EquipoMonitoreo
            for eq in EquipoMonitoreo.objects.filter(id_edificio_id=active_edificio_id):
                if eq.tipo == "bomba":
                    _pump_status = eq.status
                elif eq.tipo == "elevador":
                    _elevator_status = eq.status
        except Exception as e:
            logger.warning("Error fetching equipment status: %s", e)

    now = time.time()
    _protection_pump = None
    _protection_elevator = None
    if "pump" in protection_ends:
        remaining = int(max(0, protection_ends["pump"] - now))
        _protection_pump = {
            "message": "protección activa por alerta...",
            "remaining": remaining,
        }
    if "elevator" in protection_ends:
        remaining = int(max(0, protection_ends["elevator"] - now))
        _protection_elevator = {
            "message": "protección activa por alerta...",
            "remaining": remaining,
        }

    return {
        "current": {k: v for k, v in sensor_data.items() if k in _relevant_vars},
        "sensors": sensors,
        "history": [h for h in history[-200:] if h.get("variable") in _relevant_vars],
        "thresholds": thresholds,
        "alert_enabled": alert_enabled,
        "alert_log": alert_log[:50],
        "stats": stats,
        "recommendations": recommendations,
        "rationing": sensor_data["flow_rate"] < RATIONING_THRESHOLD,
        "door_close_attempts": door_close_attempts,
        "protection_active": bool(protection_ends),
        "pump_on": pump_on,
        "elevator_on": elevator_on,
        "protection_remaining": int(max(0, max(protection_ends.values()) - now))
        if protection_ends
        else 0,
        "protection_targets": list(protection_ends.keys()),
        "equipment_types": list(equipment_types),
        "protection_pump": _protection_pump,
        "protection_elevator": _protection_elevator,
        "pump_status": _pump_status,
        "elevator_status": _elevator_status,
    }
