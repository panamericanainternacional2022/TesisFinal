import json
import time as _time
from typing import Optional

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import _login_required
from apps.users.models import Usuario


@_login_required
@require_http_methods(["POST"])
def toggle_alerts_session_view(request: HttpRequest) -> JsonResponse:
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    enabled = data.get("enabled", True)
    duration_minutes = data.get("duration_minutes", None)

    usuario_id = request.session.get("usuario_id")
    try:
        usuario_obj = Usuario.objects.get(pk=usuario_id)
    except Exception:
        usuario_obj = None

    if enabled:
        _enable_alerts(usuario_obj, request)
        return JsonResponse({
            "status": "ok", "alerts_disabled": False, "alerts_disabled_until_ms": None,
        })
    else:
        until_ts = _disable_alerts(usuario_obj, request, duration_minutes)
        until_ms = int(until_ts * 1000) if until_ts else None
        return JsonResponse({
            "status": "ok", "alerts_disabled": True, "alerts_disabled_until_ms": until_ms,
        })


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
        until_ts = _time.time() + float(duration_minutes) * 60
    if usuario_obj:
        usuario_obj.alerts_disabled = True
        usuario_obj.alerts_disabled_until = until_ts
        usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
    request.session["alerts_disabled"] = True
    if until_ts:
        request.session["alerts_disabled_until_ts"] = until_ts
    else:
        request.session.pop("alerts_disabled_until_ts", None)
    return until_ts


@_login_required
@require_http_methods(["POST"])
def clear_notifications_view(request: HttpRequest) -> JsonResponse:
    request.session["alerts_cleared_at"] = _time.time()
    return JsonResponse({"status": "ok", "message": "Notifications cleared successfully"})
