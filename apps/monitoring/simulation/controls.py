import logging
import time as time_module

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required, admin_required
from apps.sensors.simulation.exceptions import SimulatorError
from .shared import get_simulator, get_first_simulator, json_error_response, json_success_response, parse_json_body


logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@login_required
@admin_required
def manual_update(request) -> JsonResponse:
    from apps.sensors.sensor_config import PUMP_VARS, RISK_CRITICO, RISK_ALTO, RISK_BAJO, BOOLEAN_VARS, ENUM_VARS
    from apps.sensors.simulation.constants import MAX_HISTORY_SIZE
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)

    variable = body.get("variable")
    value = body.get("value")
    building_id = body.get("edificio_id")

    sim = None
    if building_id:
        try:
            sim = get_simulator(building_id)
        except SimulatorError:
            pass
    if not sim:
        sim = get_first_simulator()
    if not sim:
        return json_error_response("No hay simuladores activos", 404)

    sensor_data = sim.sensor_data
    if variable not in sensor_data:
        return json_error_response("Variable no válida")

    if variable in ENUM_VARS:
        if variable == "door_status":
            if value not in ("open", "closed"):
                return json_error_response('door_status debe ser "open" o "closed"')
            sensor_data[variable] = value
    elif variable in BOOLEAN_VARS:
        sensor_data[variable] = bool(value)
    else:
        try:
            sensor_data[variable] = float(value)
        except (ValueError, TypeError):
            return json_error_response("Valor numérico inválido")

    from apps.core.services.risk_service import classify_risk

    if variable in BOOLEAN_VARS:
        risk = RISK_CRITICO if sensor_data[variable] else RISK_BAJO
    else:
        risk, _ = classify_risk(variable, sensor_data[variable])

    if risk in (RISK_ALTO, RISK_CRITICO) and sim.alert_enabled:
        from apps.alerts.services.alert_service import get_professional_action
        from apps.alerts.alerts.engine import send_alert

        action = get_professional_action(variable, risk, sensor_data[variable])
        send_alert(
            variable,
            sensor_data[variable],
            risk,
            f"Valor manual ({sensor_data[variable]}): {action}",
            sim=sim,
        )

    timestamp = time_module.strftime("%Y-%m-%d %H:%M:%S")
    sensor_type = "Bomba" if variable in PUMP_VARS else "Elevador"
    sim.history.append({
        "timestamp": timestamp,
        "type": sensor_type,
        "variable": f"{variable} (manual)",
        "value": sensor_data[variable],
        "risk": risk,
        "color": "red" if risk in (RISK_ALTO, RISK_CRITICO) else "green",
    })
    if len(sim.history) > MAX_HISTORY_SIZE:
        sim.history = sim.history[-MAX_HISTORY_SIZE:]

    return json_success_response({"variable": variable, "value": sensor_data[variable], "risk": risk})


@login_required
def sim_status(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    return JsonResponse({
        "edificio_id": sim.edificio_id,
        "nombre": sim.nombre,
        "paused": sim.sim_paused,
        "speed": sim.sim_speed,
        "pump_on": sim.pump_on,
        "elevator_on": sim.elevator_on,
        "has_pump": sim.has_pump,
        "has_elevator": sim.has_elevator,
        "faults": dict(sim.sim_faults),
        "protection_active": bool(sim.protection_ends),
        "protection_targets": list(sim.protection_ends.keys()),
        "alert_enabled": sim.alert_enabled,
    })


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_pause(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        paused = body.get("paused")
        if paused is not None:
            sim.sim_paused = bool(paused)
        else:
            sim.sim_paused = not sim.sim_paused
    except (SimulatorError, Exception):
        sim.sim_paused = not sim.sim_paused

    return json_success_response({"paused": sim.sim_paused})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_reset(request, building_id: int) -> JsonResponse:
    from apps.sensors.simulation.controls import reset_simulator

    try:
        message = reset_simulator(building_id)
        return json_success_response({"message": message})
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_inject_fault(request, building_id: int) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)

    device = body.get("device")
    fault_type = body.get("fault_type")
    if not device or not fault_type:
        return json_error_response("Faltan campos: device, fault_type")

    from apps.sensors.simulation.controls import inject_fault

    try:
        message = inject_fault(building_id, device, fault_type)
        return json_success_response({"message": message})
    except SimulatorError as e:
        return json_error_response(e.message)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_clear_fault(request, building_id: int) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)

    device = body.get("device")

    from apps.sensors.simulation.controls import clear_fault

    try:
        message = clear_fault(building_id, device)
        return json_success_response({"message": message})
    except SimulatorError as e:
        return json_error_response(e.message, e.status_code)


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_set_speed(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        speed = float(body.get("speed", 1.0))
    except (SimulatorError, ValueError, TypeError):
        return json_error_response("JSON inválido o speed no numérico")

    from apps.sensors.simulation.constants import MIN_SIM_SPEED, MAX_SIM_SPEED
    sim.sim_speed = max(MIN_SIM_SPEED, min(MAX_SIM_SPEED, speed))
    return json_success_response({"speed": sim.sim_speed})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_pump(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        pump_on = body.get("on")
        if pump_on is not None:
            sim.pump_on = bool(pump_on)
        else:
            sim.pump_on = not sim.pump_on
    except (SimulatorError, Exception):
        sim.pump_on = not sim.pump_on

    return json_success_response({"pump_on": sim.pump_on})


@require_http_methods(["POST"])
@login_required
@admin_required
def sim_toggle_elevator(request, building_id: int) -> JsonResponse:
    sim = get_simulator(building_id)
    if sim is None:
        return json_error_response("No hay simulador activo para este edificio", 404)

    try:
        body = parse_json_body(request)
        elevator_on = body.get("on")
        if elevator_on is not None:
            sim.elevator_on = bool(elevator_on)
        else:
            sim.elevator_on = not sim.elevator_on
    except (SimulatorError, Exception):
        sim.elevator_on = not sim.elevator_on

    return json_success_response({"elevator_on": sim.elevator_on})
