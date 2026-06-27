import json
import time as time_module
import threading
import logging

from django.http import JsonResponse, HttpRequest
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.users.models import Usuario
from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.alerts.services.threshold_service import get_thresholds, bulk_update, ThresholdPersistenceError
from apps.alerts.services.alert_service import (
    send_email_alert,
    get_building_emails,
)
from apps.alerts.services.email_sender import build_report_email_html, send_email_raw

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def view_notification_count(request: HttpRequest) -> JsonResponse:


    import datetime as dt_mod
    from apps.alerts.views.shared import _build_notification_query, exclude_severity_levels
    from apps.sensors.sensor_config import RISK_INFO, RISK_BAJO, RISK_MEDIO

    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return JsonResponse({"count": 0})

    rol = request.session.get("usuario_rol", "US")
    notifications, _ = _build_notification_query(usuario_id, rol)

    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        cleared_dt = dt_mod.datetime.fromtimestamp(alerts_cleared_at, tz=dt_mod.timezone.utc)
        notifications = notifications.filter(date__gt=cleared_dt)

    notifications = exclude_severity_levels(notifications, [RISK_INFO, RISK_BAJO, RISK_MEDIO])
    return JsonResponse({"count": notifications.distinct().count()})


@login_required
@require_http_methods(["GET"])
def view_get_thresholds(request: HttpRequest) -> JsonResponse:
    try:
        building_id = int(request.GET.get("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido", status=400)
    return JsonResponse(get_thresholds(building_id))


VALID_DIRECTIONS = frozenset({"higher", "lower", "range"})


@require_http_methods(["POST"])
@login_required
@admin_required
def view_update_thresholds(request: HttpRequest) -> JsonResponse:
    try:
        raw = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    if not isinstance(raw, dict):
        return json_error("Body must be a JSON object")

    try:
        building_id = int(raw.pop("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido")

    data = raw

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

        from apps.alerts.services.sensor_limit_service import get_sensor_limits
        sensor_limits = get_sensor_limits(building_id)
        limits = sensor_limits.get(variable)
        if limits:
            min_bound, max_bound = limits
            low_val = config["low"]
            high_val = config["high"]
            if direction == "range":
                if low_val < min_bound or high_val > max_bound:
                    errors[variable] = f"Los umbrales [{low_val}, {high_val}] deben estar dentro de los límites físicos del sensor [{min_bound}, {max_bound}]"
                    continue
            elif direction == "higher":
                if low_val < min_bound or high_val > max_bound:
                    errors[variable] = f"Los umbrales deben estar dentro de los límites físicos del sensor [{min_bound}, {max_bound}] (recibido low={low_val}, high={high_val})"
                    continue
            elif direction == "lower":
                if low_val > max_bound or high_val < min_bound:
                    errors[variable] = f"Los umbrales deben estar dentro de los límites físicos del sensor [{min_bound}, {max_bound}] (recibido low={low_val}, high={high_val})"
                    continue

    if errors:
        return json_error(f"Validation errors: {errors}")

    try:
        bulk_update(data, building_id)
    except ThresholdPersistenceError as e:
        return json_error(str(e), status=500)

    return json_ok({"thresholds": get_thresholds(building_id)})


@login_required
@require_http_methods(["GET"])
def view_get_sensor_limits(request: HttpRequest) -> JsonResponse:
    from apps.alerts.services.sensor_limit_service import get_sensor_limits
    from apps.alerts.services.threshold_service import get_thresholds
    from apps.sensors.sensor_config import LIMITS_EXCLUDE_VARS
    try:
        building_id = int(request.GET.get("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido", status=400)
    
    limits = get_sensor_limits(building_id)
    limits = {k: v for k, v in limits.items() if k not in LIMITS_EXCLUDE_VARS}
    thresholds = get_thresholds(building_id)
    return JsonResponse({
        "limits": limits,
        "thresholds": thresholds
    })


@require_http_methods(["POST"])
@login_required
@admin_required
def view_update_sensor_limits(request: HttpRequest) -> JsonResponse:
    from apps.alerts.services.sensor_limit_service import bulk_update_limits, get_sensor_limits
    from apps.alerts.services.threshold_service import get_thresholds
    from apps.sensors.sensor_config import SENSOR_RANGES, LIMITS_EXCLUDE_VARS
    try:
        raw = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    if not isinstance(raw, dict):
        return json_error("Body must be a JSON object")

    try:
        building_id = int(raw.pop("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido")

    thresholds = get_thresholds(building_id)
    data = {k: v for k, v in raw.items() if k not in LIMITS_EXCLUDE_VARS}
    errors: dict[str, str] = {}
    cleaned_data: dict[str, float] = {}

    for variable, max_val_raw in data.items():
        try:
            max_val = float(max_val_raw)
            cleaned_data[variable] = max_val
        except (ValueError, TypeError):
            errors[variable] = "Value must be numeric"
            continue

        default_min = SENSOR_RANGES.get(variable, (0.0, 100.0))[0]
        if max_val <= default_min:
            errors[variable] = f"El límite máximo ({max_val}) debe ser mayor que el mínimo por defecto ({default_min})"
            continue

        if variable in thresholds:
            t_config = thresholds[variable]
            if "high" in t_config:
                high_thresh = float(t_config["high"])
                if max_val < high_thresh:
                    label = "máximo aceptable" if t_config.get("direction") == "range" else "crítico"
                    errors[variable] = f"El límite máximo ({max_val}) no puede ser inferior al umbral {label} ({high_thresh})"

    if errors:
        return json_error(f"Validation errors: {errors}")

    try:
        bulk_update_limits(cleaned_data, building_id)
    except Exception as e:
        return json_error(str(e), status=500)

    return json_ok({
        "sensor_ranges": get_sensor_limits(building_id),
        "thresholds": get_thresholds(building_id)
    })


@require_http_methods(["POST"])
@login_required
def view_clear_alerts(request: HttpRequest) -> JsonResponse:
    now = timezone.now()
    request.session["alerts_cleared_at"] = now.timestamp()

    try:
        from apps.sensors.simulation.globals import simulators
        for sim in simulators.values():
            sim.active_alerts.clear()
            sim.last_email_sent_time = 0.0
            if hasattr(sim, "manual_overrides") and isinstance(sim.manual_overrides, dict):
                sim.manual_overrides.clear()
            if hasattr(sim, "last_email_sent_time_per_var") and isinstance(sim.last_email_sent_time_per_var, dict):
                sim.last_email_sent_time_per_var.clear()
    except Exception as exc:
        logger.warning("No se pudo limpiar active_alerts de los simuladores: %s", exc)

    usuario_id = request.session.get("usuario_id")
    try:
        usuario_obj = Usuario.objects.get(pk=usuario_id)
        usuario_obj.alerts_cleared_at = now
        usuario_obj.save(update_fields=["alerts_cleared_at"])
    except Usuario.DoesNotExist:
        pass

    return json_ok()


def _build_report_email_body(sim) -> tuple[str, str]:
    timestamp = time_module.strftime("%d/%m/%Y %H:%M:%S")
    edificio = getattr(sim, "nombre", "") or ""
    subject = f"Reporte de monitoreo: {edificio} — {timestamp}" if edificio else f"Reporte de monitoreo — {timestamp}"
    body = build_report_email_html(edificio=edificio)
    return subject, body


@require_http_methods(["POST"])
@login_required
@admin_required
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
@login_required
@admin_required
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
