import json
import time as time_module
import threading
from typing import Any, Dict, Optional

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required
from apps.core.services.http_response import json_error, json_ok
from apps.alerts.services.threshold_service import get_thresholds, update_threshold, ThresholdPersistenceError
from apps.alerts.services.alert_service import (
    send_email_alert,
    get_building_emails,
    build_standard_email_body,
)
from apps.sensors.sensor_config import RISK_INFO
from apps.sensors.sensor_config import VAR_NAMES, UNITS


@login_required
@require_http_methods(["GET"])
def view_get_thresholds(request: HttpRequest) -> JsonResponse:
    return JsonResponse(get_thresholds())


class ThresholdValidationError(ValueError):
    pass


def _validate_higher_direction(existing: Dict[str, Any], risk_lower: str, value: float) -> None:
    thresholds_ordered = {"low": 0, "medium": 0, "high": 0}
    for k in ("low", "medium", "high"):
        thresholds_ordered[k] = existing.get(k, 0)
    thresholds_ordered[risk_lower] = value

    if thresholds_ordered["low"] >= thresholds_ordered["medium"] and thresholds_ordered["medium"] != 0:
        raise ThresholdValidationError("The 'low' threshold must be lower than 'medium'.")
    if thresholds_ordered["medium"] >= thresholds_ordered["high"] and thresholds_ordered["high"] != 0:
        raise ThresholdValidationError("The 'medium' threshold must be lower than 'high'.")


def _validate_lower_direction(existing: Dict[str, Any], risk_lower: str, value: float) -> None:
    thresholds_ordered = {"low": 99999, "medium": 99999, "high": 99999}
    for k in ("low", "medium", "high"):
        thresholds_ordered[k] = existing.get(k, 99999)
    thresholds_ordered[risk_lower] = value

    if thresholds_ordered["low"] <= thresholds_ordered["medium"] and thresholds_ordered["medium"] != 99999:
        raise ThresholdValidationError("The 'low' threshold must be greater than 'medium' (descending direction).")
    if thresholds_ordered["medium"] <= thresholds_ordered["high"] and thresholds_ordered["high"] != 99999:
        raise ThresholdValidationError("The 'medium' threshold must be greater than 'high' (descending direction).")


def _validate_range_direction(existing: Dict[str, Any], risk_lower: str, value: float) -> None:
    if risk_lower == "low":
        high_val = existing.get("high", 240)
        if value >= high_val:
            raise ThresholdValidationError(f"The lower limit ({value}) must be lower than the upper limit ({high_val}).")
    elif risk_lower == "high":
        low_val = existing.get("low", 200)
        if value <= low_val:
            raise ThresholdValidationError(f"The upper limit ({value}) must be greater than the lower limit ({low_val}).")
    elif risk_lower in ("medium",):
        raise ThresholdValidationError("Range variables only allow 'low' and 'high' thresholds.")


def _validate_and_prepare_threshold(data: Dict[str, Any]) -> tuple:
    variable = data.get("variable")
    risk = data.get("risk")
    value_raw = data.get("value")

    if not variable or not risk or value_raw is None:
        raise ThresholdValidationError("Missing fields: variable, risk, value")

    try:
        value = float(value_raw)
    except (ValueError, TypeError):
        raise ThresholdValidationError("value must be numeric")

    risk_lower = risk.lower()
    if risk_lower not in ("low", "medium", "high"):
        raise ThresholdValidationError(f"Invalid risk: {risk}")

    if value < 0:
        raise ThresholdValidationError("Threshold value cannot be negative.")

    return variable, risk_lower, value


@require_http_methods(["POST"])
def view_update_thresholds(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    try:
        variable, risk_lower, value = _validate_and_prepare_threshold(data)
    except ThresholdValidationError as e:
        return json_error(str(e))

    existing = get_thresholds().get(variable, {"direction": "higher", "low": 0, "medium": 0, "high": 0})
    direction = existing.get("direction", "higher")

    try:
        if direction == "range":
            _validate_range_direction(existing, risk_lower, value)
        elif direction == "higher":
            _validate_higher_direction(existing, risk_lower, value)
        elif direction == "lower":
            _validate_lower_direction(existing, risk_lower, value)

        existing[risk_lower] = value
        update_threshold(variable, existing)
    except ThresholdValidationError as e:
        return json_error(str(e))
    except ThresholdPersistenceError as e:
        return json_error(str(e), status=500)

    return json_ok({"thresholds": get_thresholds()})


@require_http_methods(["POST"])
def view_clear_alerts(request: HttpRequest) -> JsonResponse:
    request.session["alerts_cleared_at"] = time_module.time()
    return json_ok()


@require_http_methods(["POST"])
def view_toggle_alerts(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    edificio_id = data.get("edificio_id")
    enabled = data.get("enabled")
    if enabled is None:
        return json_error("Missing field 'enabled'")

    from apps.sensors.simulation.globals import simulators
    if edificio_id and edificio_id in simulators:
        sim = simulators[edificio_id]
        sim.alert_enabled = bool(enabled)
        return json_ok({"alert_enabled": sim.alert_enabled})
    else:
        for sim in simulators.values():
            sim.alert_enabled = bool(enabled)
        return json_ok({"alert_enabled": bool(enabled)})


def _build_report_email_body(risk_level: str, sim) -> tuple[str, str]:
    timestamp = time_module.strftime("%d/%m/%Y %H:%M:%S")
    subject = f"[INES] Reporte de monitoreo - {timestamp}"

    detalles: dict[str, str] = {
        "Fecha y hora": timestamp,
        "Nivel de riesgo": risk_level,
    }
    edificio_nombre = getattr(sim, "nombre", None) or getattr(sim, "edificio_id", "")
    if edificio_nombre:
        detalles["Edificio"] = str(edificio_nombre)

    for var in list(VAR_NAMES.keys()):
        val = sim.sensor_data.get(var)
        if val is not None:
            nombre = VAR_NAMES.get(var, var)
            unidad = UNITS.get(var, "")
            detalles[nombre] = f"{val} {unidad}".strip()

    body = build_standard_email_body(
        titulo="Reporte de monitoreo",
        contexto="Lecturas actuales de los sensores del sistema de monitoreo.",
        detalles=detalles,
    )
    return subject, body


@require_http_methods(["POST"])
def send_test_email(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    email = data.get("email", "")
    if not email:
        return json_error("Missing field 'email'")

    risk_level = data.get("risk_level", RISK_INFO)

    from apps.sensors.simulation.globals import simulators
    sim = next(iter(simulators.values()), None)
    if not sim:
        return json_error("Simulator not found", 404)

    subject, body = _build_report_email_body(risk_level, sim)

    threading.Thread(
        target=send_email_alert,
        kwargs={
            "risk_level": risk_level,
            "subject": subject,
            "body": body,
            "recipients": [email],
        },
        daemon=True,
    ).start()
    return json_ok({"message": f"Reporte enviado a {email}"})


@require_http_methods(["POST"])
def send_all_subscribers(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    edificio_id = data.get("edificio_id")
    risk_level = data.get("risk_level", RISK_INFO)

    from apps.sensors.simulation.globals import simulators
    sim = simulators.get(edificio_id) if edificio_id else next(iter(simulators.values()), None)
    if not sim:
        return json_error("Simulator not found", 404)

    emails = get_building_emails(edificio_id or sim.edificio_id)
    if not emails:
        return json_error("No subscribers for this building")

    subject, body = _build_report_email_body(risk_level, sim)

    for email in emails:
        threading.Thread(
            target=send_email_alert,
            kwargs={
                "risk_level": risk_level,
                "subject": subject,
                "body": body,
                "recipients": [email],
            },
            daemon=True,
        ).start()
    return json_ok({"message": f"Reporte enviado a {len(emails)} suscriptores"})
