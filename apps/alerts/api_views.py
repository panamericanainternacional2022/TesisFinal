import json
import time as time_module
import threading
import logging

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required
from apps.core.services.http_response import json_error, json_ok
from apps.alerts.services.threshold_service import get_thresholds, bulk_update, ThresholdPersistenceError
from apps.alerts.services.alert_service import (
    send_email_alert,
    get_building_emails,
)
from apps.alerts.services.email_sender import build_report_email_html, send_email_raw

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def view_get_thresholds(request: HttpRequest) -> JsonResponse:
    return JsonResponse(get_thresholds())


VALID_DIRECTIONS = frozenset({"higher", "lower", "range"})


@require_http_methods(["POST"])
def view_update_thresholds(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    if not isinstance(data, dict):
        return json_error("Body must be a JSON object")

    errors: dict[str, str] = {}

    for variable, config in data.items():
        if not isinstance(config, dict):
            errors[variable] = "Invalid config format"
            continue

        direction = config.get("direction")
        if direction not in VALID_DIRECTIONS:
            errors[variable] = f"Invalid direction: {direction}"
            continue

        try:
            config["low"] = float(config.get("low", 0))
            if direction == "range":
                if "high" not in config:
                    errors[variable] = "Missing 'high' for range direction"
                    continue
                config["high"] = float(config["high"])
            else:
                config["medium"] = float(config.get("medium", 0))
                config["high"] = float(config.get("high", 0))
        except (ValueError, TypeError) as e:
            errors[variable] = f"Non-numeric threshold value: config={config}"
            logger.warning("Threshold non-numeric for %s: %s — config=%s", variable, e, config)
            continue

        if direction == "range":
            if config["low"] >= config["high"]:
                errors[variable] = f"Low limit ({config['low']}) must be lower than high limit ({config['high']})"
                logger.warning("Threshold range fail for %s: low=%s high=%s", variable, config['low'], config['high'])
                continue
        elif direction == "higher":
            if not (config["low"] < config["medium"] < config["high"]):
                errors[variable] = f"Thresholds must be ascending: low={config['low']} < medium={config['medium']} < high={config['high']}"
                logger.warning("Threshold higher fail for %s: low=%s med=%s high=%s", variable, config['low'], config['medium'], config['high'])
                continue
        elif direction == "lower":
            if not (config["low"] > config["medium"] > config["high"]):
                errors[variable] = "Thresholds must be descending: low > medium > high"
                continue

    if errors:
        return json_error(f"Validation errors: {errors}")

    try:
        bulk_update(data)
    except ThresholdPersistenceError as e:
        return json_error(str(e), status=500)

    return json_ok({"thresholds": get_thresholds()})


@require_http_methods(["POST"])
def view_clear_alerts(request: HttpRequest) -> JsonResponse:
    request.session["alerts_cleared_at"] = time_module.time()

    # Limpiar el bloqueo anti-duplicados de cada simulador para que las alertas
    # vuelvan a generarse tras borrar las notificaciones de la BD.
    try:
        from apps.sensors.simulation.globals import simulators
        for sim in simulators.values():
            sim.active_alerts.clear()
            sim.last_email_sent_time = 0.0
    except Exception as exc:
        logger.warning("No se pudo limpiar active_alerts de los simuladores: %s", exc)

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
    edificio = getattr(sim, "nombre", "") or ""
    subject = f"Reporte de monitoreo: {edificio} — {timestamp}" if edificio else f"Reporte de monitoreo — {timestamp}"
    body = build_report_email_html(edificio=edificio)
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

    subject, html_body = _build_report_email_body(sim)

    pdf_bytes = None
    pdf_name = "reporte.pdf"
    try:
        from apps.reports.views.building_report import generate_building_report_bytes
        pdf_bytes, pdf_name = generate_building_report_bytes(sim.edificio_id)
    except Exception as e:
        logger.warning("Could not generate building report PDF: %s", e)

    threading.Thread(
        target=send_email_raw,
        kwargs={
            "to_addrs": [email],
            "subject": subject,
            "html_body": html_body,
            "attachment_pdf": pdf_bytes,
            "attachment_name": pdf_name,
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

    subject, html_body = _build_report_email_body(sim)

    pdf_bytes = None
    pdf_name = "reporte.pdf"
    target_id = eid or sim.edificio_id
    try:
        from apps.reports.views.building_report import generate_building_report_bytes
        pdf_bytes, pdf_name = generate_building_report_bytes(target_id)
    except Exception as e:
        logger.warning("Could not generate building report PDF: %s", e)

    for email in emails:
        threading.Thread(
            target=send_email_raw,
            kwargs={
                "to_addrs": [email],
                "subject": subject,
                "html_body": html_body,
                "attachment_pdf": pdf_bytes,
                "attachment_name": pdf_name,
            },
            daemon=True,
        ).start()
    return json_ok({"message": f"Reporte enviado a {len(emails)} suscriptores"})
