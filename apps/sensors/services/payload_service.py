import time
from typing import Any
import logging
from dataclasses import dataclass
from typing import Callable

from apps.sensors.sensor_config import STATS_VARS, PUMP_VARS, ELEVATOR_VARS, SYSTEM_VARS, VAR_NAMES, RISK_CRITICO, RISK_NORMAL, BOOLEAN_VARS, PAYLOAD_HISTORY_SLICE, API_NOTIFICATION_LIMIT
from apps.sensors.simulation.constants import MAX_HISTORY_SIZE

logger = logging.getLogger(__name__)


def _noop_recommendations(sensor_data: dict, stats: dict) -> list:
    return []


@dataclass
class PayloadContext:
    sensor_data: dict
    protection_ends: dict
    history: list
    door_close_attempts: int
    pump_on: bool
    elevator_on: bool
    equipment_types: set
    rationing_threshold: float
    sim_paused: bool
    sim_speed: float
    generate_recommendations_fn: Callable = _noop_recommendations
    active_edificio_id: int = None
    django_connected: bool = False
    sim_faults: dict = None
    active_alerts: dict = None


def _compute_stats(history: list, max_entries: int = MAX_HISTORY_SIZE) -> dict[str, Any]:
    stats = {}
    recent = history[-max_entries:] if len(history) > max_entries else history
    for var in STATS_VARS:
        vals = [
            r["value"]
            for r in recent
            if r["variable"] == var and isinstance(r["value"], (int, float)) and not isinstance(r["value"], bool)
        ]
        if vals:
            stats[var] = {
                "avg": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }
    return stats


def build_live_payload(ctx: PayloadContext) -> dict[str, Any]:
    from apps.alerts.services.threshold_service import get_thresholds
    from apps.alerts.services.alert_service import get_alert_log
    stats = _compute_stats(ctx.history)
    relevant_vars = _build_relevant_vars(ctx.equipment_types)
    thresholds = get_thresholds(ctx.active_edificio_id)
    sensors = _build_sensors_list(ctx.sensor_data, relevant_vars, thresholds)
    recommendations = ctx.generate_recommendations_fn(ctx.sensor_data, stats)
    pump_status, elevator_status = _fetch_equipment_status(
        ctx.django_connected, ctx.active_edificio_id, ctx.sim_faults, ctx.active_alerts, ctx.protection_ends
    )
    protection_pump, protection_elevator = _compute_protection_info(ctx.protection_ends)
    now = time.time()
    return {
        "current": {k: v for k, v in ctx.sensor_data.items() if k in relevant_vars},
        "sensors": sensors,
        "history": [h for h in ctx.history[-PAYLOAD_HISTORY_SLICE:] if h.get("variable") in relevant_vars],
        "thresholds": thresholds,
        "alert_log": get_alert_log(ctx.active_edificio_id, API_NOTIFICATION_LIMIT),
        "stats": stats,
        "recommendations": recommendations,
        "rationing": ctx.sensor_data.get("flow_rate", 0) < ctx.rationing_threshold,
        "door_close_attempts": ctx.door_close_attempts,
        "protection_active": bool(ctx.protection_ends),
        "pump_on": ctx.pump_on,
        "elevator_on": ctx.elevator_on,
        "protection_remaining": int(max(0, max(ctx.protection_ends.values()) - now))
        if ctx.protection_ends
        else 0,
        "protection_targets": list(ctx.protection_ends.keys()),
        "equipment_types": list(ctx.equipment_types),
        "protection_pump": protection_pump,
        "protection_elevator": protection_elevator,
        "pump_status": pump_status,
        "elevator_status": elevator_status,
        "sim_paused": ctx.sim_paused,
        "sim_speed": ctx.sim_speed,
    }


def _build_relevant_vars(equipment_types: set) -> set[str]:
    relevant_vars = set()
    if "bomba" in equipment_types:
        relevant_vars.update(PUMP_VARS)
    if "elevador" in equipment_types:
        relevant_vars.update(ELEVATOR_VARS)
    relevant_vars.update(SYSTEM_VARS)
    return relevant_vars


def _build_sensors_list(sensor_data: dict, relevant_vars: set[str], thresholds: dict) -> list[dict[str, Any]]:
    from apps.core.services.risk_service import classify_risk
    sensors = []
    for var, value in sensor_data.items():
        if var not in relevant_vars:
            continue
        if var in BOOLEAN_VARS:
            risk, color = (RISK_CRITICO, "red") if value else (RISK_NORMAL, "green")
        else:
            risk, color = classify_risk(var, value, thresholds)
        sensors.append({
            "id": var,
            "nombre": VAR_NAMES.get(var, var),
            "riesgo": risk,
            "color": color,
        })
    return sensors


def _fetch_equipment_status(
    django_connected: bool,
    active_edificio_id: int,
    sim_faults: dict = None,
    active_alerts: dict = None,
    protection_ends: dict = None,
) -> tuple:
    pump_status = None
    elevator_status = None
    
    has_pump_fault = False
    if sim_faults and "pump" in sim_faults:
        has_pump_fault = True
    elif active_alerts:
        from apps.sensors.sensor_config import PUMP_VARS
        if any(var in PUMP_VARS for var in active_alerts):
            has_pump_fault = True
            
    if has_pump_fault:
        dynamic_pump = "falla"
    elif protection_ends and "pump" in protection_ends:
        dynamic_pump = "mantenimiento"
    else:
        dynamic_pump = "operativo"

    has_elev_fault = False
    if sim_faults and "elevator" in sim_faults:
        has_elev_fault = True
    elif active_alerts:
        from apps.sensors.sensor_config import ELEVATOR_VARS
        if any(var in ELEVATOR_VARS for var in active_alerts):
            has_elev_fault = True
            
    if has_elev_fault:
        dynamic_elev = "falla"
    elif protection_ends and "elevator" in protection_ends:
        dynamic_elev = "mantenimiento"
    else:
        dynamic_elev = "operativo"

    if django_connected and active_edificio_id:
        try:
            from apps.buildings.models import MonitoringEquipment
            for eq in MonitoringEquipment.objects.filter(building_id=active_edificio_id):
                if eq.equipment_type == "bomba":
                    if eq.status != dynamic_pump:
                        eq.status = dynamic_pump
                        eq.save(update_fields=["status"])
                    pump_status = dynamic_pump
                elif eq.equipment_type == "elevador":
                    if eq.status != dynamic_elev:
                        eq.status = dynamic_elev
                        eq.save(update_fields=["status"])
                    elevator_status = dynamic_elev
        except Exception as e:
            logger.warning("Error fetching and syncing equipment status: %s", e)
            pump_status = dynamic_pump
            elevator_status = dynamic_elev
    else:
        pump_status = dynamic_pump
        elevator_status = dynamic_elev
        
    return pump_status, elevator_status


def _compute_protection_info(protection_ends: dict) -> tuple:
    now = time.time()
    protection_pump = None
    protection_elevator = None
    if "pump" in protection_ends:
        remaining = int(max(0, protection_ends["pump"] - now))
        protection_pump = {
            "message": "protección activa por alerta...",
            "remaining": remaining,
        }
    if "elevator" in protection_ends:
        remaining = int(max(0, protection_ends["elevator"] - now))
        protection_elevator = {
            "message": "protección activa por alerta...",
            "remaining": remaining,
        }
    return protection_pump, protection_elevator
