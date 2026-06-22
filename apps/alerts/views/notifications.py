from django.shortcuts import render
from django.http import HttpRequest
from django.utils import timezone
from django.core.paginator import Paginator
import datetime as dt

from apps.core.auth_decorators import login_required
from apps.core.services.http_request import get_building_id_param
from apps.users.models import Usuario
from apps.buildings.models import Building
from apps.alerts.models import Notification
from apps.alerts.views.shared import (
    parse_notification_for_display, exclude_severity_levels, _build_notification_query,
)
from apps.sensors.sensor_config import RISK_INFO, RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO, PAGE_SIZE

_EXCLUDED_SEVERITIES = [RISK_INFO, RISK_BAJO, RISK_MEDIO]


@login_required
def notifications_view(request: HttpRequest):
    from apps.core.auth_decorators import is_admin_role
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return render(request, "alerts/notifications.html", {
            "notifications": None, "buildings": [], "rol": "US",
            "alerts_disabled": False, "alerts_disabled_until_ms": None,
            "email_alerts_disabled": False,
        })

    rol = request.session.get("usuario_rol", "US")
    building_id_raw = get_building_id_param(request, "building", "edificio")

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

    notifications = notifications.select_related("user", "monitoring_equipment__building")

    notifications = exclude_severity_levels(notifications, _EXCLUDED_SEVERITIES)

    notifications = notifications.distinct().order_by("-date")

    paginator = Paginator(notifications, PAGE_SIZE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for notif in page_obj:
        parse_notification_for_display(notif)

    _update_alert_disabled_state(request, usuario_id)

    alerts_disabled = request.session.get("alerts_disabled", False)
    alerts_disabled_until_ts = request.session.get("alerts_disabled_until_ts", None)
    alerts_disabled_until_ms = int(alerts_disabled_until_ts * 1000) if alerts_disabled_until_ts else None

    email_alerts_disabled = request.session.get("email_alerts_disabled", False)

    return render(
        request,
        "alerts/notifications.html",
        {
            "notifications": page_obj,
            "buildings": buildings,
            "selected_building_id": int(building_id_raw) if building_id_raw.isdigit() else None,
            "rol": rol,
            "alerts_disabled": alerts_disabled,
            "alerts_disabled_until_ms": alerts_disabled_until_ms,
            "email_alerts_disabled": email_alerts_disabled,
            "RISK_CRITICO": RISK_CRITICO, "RISK_ALTO": RISK_ALTO,
            "RISK_MEDIO": RISK_MEDIO, "RISK_BAJO": RISK_BAJO, "RISK_INFO": RISK_INFO,
        },
    )


def _update_alert_disabled_state(request: HttpRequest, usuario_id: int) -> None:
    try:
        user_obj = Usuario.objects.get(pk=usuario_id)
    except Exception:
        user_obj = None

    alerts_disabled_until_dt = None
    if not user_obj:
        alerts_disabled = request.session.get("alerts_disabled", False)
        alerts_disabled_until_ts = request.session.get("alerts_disabled_until_ts", None)
    else:
        alerts_disabled = user_obj.alerts_disabled
        alerts_disabled_until_dt = user_obj.alerts_disabled_until
        alerts_disabled_until_ts = alerts_disabled_until_dt.timestamp() if alerts_disabled_until_dt else None

    if alerts_disabled and alerts_disabled_until_dt:
        if timezone.now() > alerts_disabled_until_dt:
            alerts_disabled = False
            alerts_disabled_until_ts = None
            alerts_disabled_until_dt = None
            if user_obj:
                user_obj.alerts_disabled = False
                user_obj.alerts_disabled_until = None
                user_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
            request.session["alerts_disabled"] = False
            request.session.pop("alerts_disabled_until_ts", None)

    request.session["alerts_disabled"] = alerts_disabled
    if alerts_disabled_until_ts:
        request.session["alerts_disabled_until_ts"] = alerts_disabled_until_ts

    if user_obj:
        request.session["email_alerts_disabled"] = user_obj.email_alerts_disabled
