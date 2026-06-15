import json
import time as time_module
import threading
import logging
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

logger = logging.getLogger(__name__)


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
    try:
        eid = int(edificio_id) if edificio_id is not None else None
    except (ValueError, TypeError):
        eid = None
    if eid and eid in simulators:
        sim = simulators[eid]
        sim.alert_enabled = bool(enabled)
        return json_ok({"alert_enabled": sim.alert_enabled})
    else:
        for sim in simulators.values():
            sim.alert_enabled = bool(enabled)
        return json_ok({"alert_enabled": bool(enabled)})


def _build_report_email_body(sim) -> tuple[str, str]:
    timestamp = time_module.strftime("%d/%m/%Y %H:%M:%S")
    subject = f"[INES] Reporte de monitoreo - {timestamp}"

    body = build_standard_email_body(
        titulo="Reporte de monitoreo",
        contexto="Se adjunta el reporte PDF con el estado actual de los sensores del edificio.",
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

    from apps.sensors.simulation.globals import simulators
    sim = next(iter(simulators.values()), None)
    if not sim:
        return json_error("No hay un simulador activo. Inicie la simulación primero.", 503)

    subject, body = _build_report_email_body(sim)

    pdf_bytes = None
    pdf_name = None
    try:
        from apps.reports.views.building_report import generate_building_report_bytes
        pdf_bytes, pdf_name = generate_building_report_bytes(sim.edificio_id)
    except Exception as e:
        logger.warning("Could not generate building report PDF: %s", e)

    kwargs = {
        "risk_level": RISK_INFO,
        "subject": subject,
        "body": body,
        "recipients": [email],
    }
    if pdf_bytes is not None:
        kwargs["attachment_pdf"] = pdf_bytes
        kwargs["attachment_name"] = pdf_name

    threading.Thread(
        target=send_email_alert,
        kwargs=kwargs,
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

    from apps.sensors.simulation.globals import simulators
    try:
        eid = int(edificio_id) if edificio_id is not None else None
    except (ValueError, TypeError):
        eid = None
    sim = simulators.get(eid) if eid else next(iter(simulators.values()), None)
    if not sim:
        return json_error("No hay un simulador activo. Inicie la simulación primero.", 503)

    emails = get_building_emails(eid or sim.edificio_id)
    if not emails:
        return json_error("No subscribers for this building")

    subject, body = _build_report_email_body(sim)

    pdf_bytes = None
    pdf_name = None
    target_id = eid or sim.edificio_id
    try:
        from apps.reports.views.building_report import generate_building_report_bytes
        pdf_bytes, pdf_name = generate_building_report_bytes(target_id)
    except Exception as e:
        logger.warning("Could not generate building report PDF: %s", e)

    base_kwargs = {
        "risk_level": RISK_INFO,
        "subject": subject,
        "body": body,
    }
    if pdf_bytes is not None:
        base_kwargs["attachment_pdf"] = pdf_bytes
        base_kwargs["attachment_name"] = pdf_name

    for email in emails:
        threading.Thread(
            target=send_email_alert,
            kwargs={**base_kwargs, "recipients": [email]},
            daemon=True,
        ).start()
    return json_ok({"message": f"Reporte enviado a {len(emails)} suscriptores"})
