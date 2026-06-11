import logging

from front.sensor_config import STATS_VARS, PUMP_VARS, ELEVATOR_VARS
from front.services.risk_service import classify_risk
from front.services.threshold_service import get_thresholds

logger = logging.getLogger(__name__)


def titleize_name(text):
    return " ".join(word.capitalize() for word in text.replace("_", " ").split())


def build_live_payload(
    sensor_data, protection_ends, history, alert_log,
    door_close_attempts, pump_on, elevator_on, equipment_types,
    RATIONING_THRESHOLD, sim_paused, sim_speed,
    generate_recommendations_fn=None, alert_enabled=True,
    active_edificio_id=None, DJANGO_CONNECTED=False,
):
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

    thresholds = get_thresholds()

    sensors = []
    for var, value in sensor_data.items():
        if var not in _relevant_vars:
            continue
        if var == "motor_stuck":
            risk, color = ("Crítico", "red") if value else ("Bajo", "green")
        else:
            risk, color = classify_risk(var, value, thresholds)
        sensors.append(
            {
                "id": var,
                "nombre": titleize_name(var),
                "riesgo": risk,
                "color": color,
            }
        )

    recommendations = []
    if generate_recommendations_fn:
        recommendations = generate_recommendations_fn(sensor_data, stats)

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

    import time
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
        "rationing": sensor_data.get("flow_rate", 0) < RATIONING_THRESHOLD,
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
        "sim_paused": sim_paused,
        "sim_speed": sim_speed,
    }
