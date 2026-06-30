import json
import logging
import threading
import time as time_module
import datetime as dt
from typing import Optional

from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from urllib.parse import urlencode

from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_request import get_building_id_param
from apps.core.services.http_response import json_error, json_ok
from apps.users.models import Usuario
from apps.buildings.models import Building
from apps.events.models import Notification
from apps.events.shared import (
    parse_notification_for_display, _build_notification_query,
    exclude_severity_levels,
)
from apps.sensors.sensor_config import RISK_INFORMATIVO, RISK_ALTO, RISK_CRITICO, PAGE_SIZE
from apps.dashboard.shared import (
    filter_date_range, build_query_string,
    parse_notifications, extract_variables,
    extract_severities, filter_severity_python, filter_by_variable,
)
from apps.events.services.alert_service import (
    send_email_alert,
    get_building_emails,
)
from apps.events.services.email_sender import build_report_email_html, send_email_raw

logger = logging.getLogger(__name__)


@login_required
def notifications_view(request: HttpRequest):
    from apps.core.auth_decorators import is_admin_role
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return render(request, "events/notifications.html", {
            "notifications": None, "edificios": [], "rol": "US",
            "alerts_disabled": False, "alerts_disabled_until_ms": None,
            "filter_query_string": "",
            "severidad": "", "variable_filter": "", "all_variables": [],
            "ALL_SEVERITIES": [], "fecha_desde": "", "fecha_hasta": "",
            "periodo_seleccionado": "1h", "total_count": 0,
        })

    rol = request.session.get("usuario_rol", "US")
    building_id_raw = get_building_id_param(request, "building", "edificio")
    severity = request.GET.get("severidad", "").strip()
    variable_filter = request.GET.get("variable", "").strip()
    period = request.GET.get("periodo", "1h").strip()
    date_from = request.GET.get("fecha_desde", "").strip()
    date_to = request.GET.get("fecha_hasta", "").strip()

    filter_params = {}
    if building_id_raw and building_id_raw.isdigit():
        filter_params["edificio"] = building_id_raw
    filter_query_string = urlencode(filter_params)

    notifications, _ = _build_notification_query(usuario_id, rol, building_id_raw)

    if is_admin_role(rol):
        buildings = Building.objects.all()
    else:
        from apps.buildings.models import UserBuilding
        user_building_ids = UserBuilding.objects.filter(
            user_id=usuario_id
        ).values_list("building", flat=True)
        buildings = Building.objects.filter(id__in=user_building_ids)

    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        cleared_dt = dt.datetime.fromtimestamp(alerts_cleared_at, tz=dt.timezone.utc)
        notifications = notifications.filter(date__gt=cleared_dt)

    notifications = filter_date_range(notifications, period, date_from, date_to)

    notifications = (
        notifications
        .select_related("user", "monitoring_equipment__building")
        .distinct()
        .order_by("-date")
    )

    parsed_list = parse_notifications(notifications)

    all_variables = extract_variables(parsed_list)
    available_severities = extract_severities(parsed_list)

    parsed_list = filter_severity_python(parsed_list, severity)
    parsed_list = filter_by_variable(parsed_list, variable_filter)

    _update_alert_disabled_state(request, usuario_id)

    alerts_disabled = request.session.get("alerts_disabled", False)
    alerts_disabled_until_ts = request.session.get("alerts_disabled_until_ts", None)
    alerts_disabled_until_ms = int(alerts_disabled_until_ts * 1000) if alerts_disabled_until_ts else None

    query_string = build_query_string(
        edificio=building_id_raw,
        severidad=severity,
        variable=variable_filter,
        periodo=period,
        fecha_desde=date_from if period == "custom" else None,
        fecha_hasta=date_to if period == "custom" else None,
    )

    paginator = Paginator(parsed_list, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    for notif in page_obj:
        parse_notification_for_display(notif)

    return render(
        request,
        "events/notifications.html",
        {
            "notifications": page_obj,
            "edificios": buildings,
            "selected_edificio_id": int(building_id_raw) if building_id_raw and building_id_raw.isdigit() else None,
            "rol": rol,
            "alerts_disabled": alerts_disabled,
            "alerts_disabled_until_ms": alerts_disabled_until_ms,
            "filter_query_string": query_string,
            "severidad": severity,
            "variable_filter": variable_filter,
            "all_variables": all_variables,
            "ALL_SEVERITIES": available_severities,
            "fecha_desde": date_from,
            "fecha_hasta": date_to,
            "periodo_seleccionado": period,
            "total_count": len(parsed_list),
        },
    )


@require_http_methods(["GET"])
def view_notification_count(request: HttpRequest) -> JsonResponse:
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return JsonResponse({"count": 0})

    rol = request.session.get("usuario_rol", "US")
    notifications, _ = _build_notification_query(usuario_id, rol)

    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        cleared_dt = dt.datetime.fromtimestamp(alerts_cleared_at, tz=dt.timezone.utc)
        notifications = notifications.filter(date__gt=cleared_dt)

    notifications = exclude_severity_levels(notifications, [RISK_INFORMATIVO])
    return JsonResponse({"count": notifications.distinct().count()})


@login_required
@require_http_methods(["POST"])
def toggle_alerts_session_view(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    enabled = data.get("enabled", True)
    duration_minutes = data.get("duration_minutes", None)

    usuario_id = request.session.get("usuario_id")
    try:
        usuario_obj = Usuario.objects.get(pk=usuario_id)
    except Exception:
        usuario_obj = None

    if enabled:
        _enable_alerts(usuario_obj, request)
        return json_ok({"alerts_disabled": False, "alerts_disabled_until_ms": None})
    else:
        until_ts = _disable_alerts(usuario_obj, request, duration_minutes)
        until_ms = int(until_ts * 1000) if until_ts else None
        return json_ok({"alerts_disabled": True, "alerts_disabled_until_ms": until_ms})


def _enable_alerts(usuario_obj: Optional[Usuario], request: HttpRequest) -> None:
    if usuario_obj:
        usuario_obj.alerts_disabled = False
        usuario_obj.alerts_disabled_until = None
        usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
    request.session["alerts_disabled"] = False
    request.session.pop("alerts_disabled_until_ts", None)


def _disable_alerts(
    usuario_obj: Optional[Usuario], request: HttpRequest, duration_minutes: Optional[float]
) -> Optional[float]:
    until_ts: Optional[float] = None
    if duration_minutes is not None:
        dt_val = timezone.now() + dt.timedelta(minutes=float(duration_minutes))
        until_ts = dt_val.timestamp()
    if usuario_obj:
        usuario_obj.alerts_disabled = True
        usuario_obj.alerts_disabled_until = timezone.now() + dt.timedelta(minutes=float(duration_minutes)) if duration_minutes is not None else None
        usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
    request.session["alerts_disabled"] = True
    if until_ts:
        request.session["alerts_disabled_until_ts"] = until_ts
    else:
        request.session.pop("alerts_disabled_until_ts", None)
    return until_ts


@login_required
@require_http_methods(["POST"])
def clear_notifications_view(request: HttpRequest) -> JsonResponse:
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

    return json_ok({"message": "Notifications cleared successfully"})


@require_http_methods(["POST"])
@login_required
def view_clear_alerts(request: HttpRequest) -> JsonResponse:
    return clear_notifications_view(request)


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


def _update_alert_disabled_state(request: HttpRequest, usuario_id: int) -> None:
    try:
        usuario_obj = Usuario.objects.get(pk=usuario_id)
        if (
            usuario_obj.alerts_disabled
            and usuario_obj.alerts_disabled_until
            and timezone.now() > usuario_obj.alerts_disabled_until
        ):
            usuario_obj.alerts_disabled = False
            usuario_obj.alerts_disabled_until = None
            usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
            request.session["alerts_disabled"] = False
            request.session.pop("alerts_disabled_until_ts", None)
    except Exception:
        pass
