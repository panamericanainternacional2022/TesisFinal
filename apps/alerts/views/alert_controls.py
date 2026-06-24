import json
from datetime import timedelta
from typing import Optional

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required
from apps.core.services.http_response import json_error, json_ok
from apps.users.models import Usuario


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
        dt_val = timezone.now() + timedelta(minutes=float(duration_minutes))
        until_ts = dt_val.timestamp()
    if usuario_obj:
        usuario_obj.alerts_disabled = True
        usuario_obj.alerts_disabled_until = timezone.now() + timedelta(minutes=float(duration_minutes)) if duration_minutes is not None else None
        usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
    request.session["alerts_disabled"] = True
    if until_ts:
        request.session["alerts_disabled_until_ts"] = until_ts
    else:
        request.session.pop("alerts_disabled_until_ts", None)
    return until_ts


@login_required
@require_http_methods(["POST"])
def toggle_email_alerts_view(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    enabled = data.get("enabled", True)
    usuario_id = request.session.get("usuario_id")

    from apps.core.auth_decorators import is_admin_role
    rol = request.session.get("usuario_rol", "US")
    if is_admin_role(rol):
        return json_error("Admin cannot disable email alerts")

    try:
        usuario_obj = Usuario.objects.get(pk=usuario_id)
    except Exception:
        return json_error("User not found")

    disabled = not enabled
    usuario_obj.email_alerts_disabled = disabled
    usuario_obj.save(update_fields=["email_alerts_disabled"])
    request.session["email_alerts_disabled"] = disabled

    return json_ok({"email_alerts_disabled": disabled})


@login_required
@require_http_methods(["POST"])
def clear_notifications_view(request: HttpRequest) -> JsonResponse:
    import logging
    _logger = logging.getLogger(__name__)

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
        _logger.info(
            "active_alerts y last_email_sent_time limpiados en %d simulador(es)",
            len(simulators),
        )
    except Exception as exc:
        _logger.warning("No se pudo limpiar active_alerts de los simuladores: %s", exc)

    usuario_id = request.session.get("usuario_id")
    try:
        usuario_obj = Usuario.objects.get(pk=usuario_id)
        usuario_obj.alerts_cleared_at = now
        usuario_obj.save(update_fields=["alerts_cleared_at"])
    except Usuario.DoesNotExist:
        pass

    return json_ok({"message": "Notifications cleared successfully"})
