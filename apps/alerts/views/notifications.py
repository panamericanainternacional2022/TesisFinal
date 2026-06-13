import datetime as dt
import time as _time

from django.shortcuts import render
from django.http import HttpRequest
from django.db.models import Q

from apps.core.auth_decorators import login_required
from apps.users.models import Usuario
from apps.buildings.models import Building, UserBuilding, MonitoringEquipment
from apps.alerts.models import Notification
from apps.alerts.views.shared import parse_notification_for_display
from django.core.paginator import Paginator


@login_required
def notifications_view(request: HttpRequest):
    from apps.core.auth_decorators import is_admin_role
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return render(request, "alerts/notifications.html", {
            "notifications": None, "buildings": [], "rol": "US",
            "alerts_disabled": False, "alerts_disabled_until_ms": None,
        })

    rol = request.session.get("usuario_rol", "US")
    building_id_raw = (request.GET.get("building") or request.GET.get("edificio") or "").strip()

    if is_admin_role(rol):
        buildings = Building.objects.all()
        notifications = Notification.objects.all()
        if building_id_raw:
            notifications = notifications.filter(
                monitoring_equipment__building_id=building_id_raw
            )
    else:
        user_buildings = UserBuilding.objects.filter(
            user_id=usuario_id
        ).values_list("building", flat=True)
        buildings = Building.objects.filter(id__in=user_buildings)

        if building_id_raw:
            if building_id_raw.isdigit() and int(building_id_raw) in list(user_buildings):
                notifications = Notification.objects.filter(
                    monitoring_equipment__building_id=building_id_raw
                )
            else:
                notifications = Notification.objects.none()
        else:
            equipos = MonitoringEquipment.objects.filter(
                building_id__in=list(user_buildings)
            ).values_list("id", flat=True)
            notifications = Notification.objects.filter(
                user_id=usuario_id
            ) | Notification.objects.filter(monitoring_equipment_id__in=list(equipos))

    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        cleared_dt = dt.datetime.fromtimestamp(alerts_cleared_at, tz=dt.timezone.utc)
        notifications = notifications.filter(date__gt=cleared_dt)

    notifications = (
        notifications.select_related("user", "monitoring_equipment__building")
        .exclude(Q(message__risk="Info") | Q(message__contains='"risk": "Info"') | Q(message__contains='"risk":"Info"'))
        .exclude(Q(message__risk="Bajo") | Q(message__contains='"risk": "Bajo"') | Q(message__contains='"risk":"Bajo"'))
        .exclude(Q(message__risk="Medio") | Q(message__contains='"risk": "Medio"') | Q(message__contains='"risk":"Medio"'))
        .distinct()
        .order_by("-date")
    )

    paginator = Paginator(notifications, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for notif in page_obj:
        parse_notification_for_display(notif)

    _update_alert_disabled_state(request, usuario_id)

    alerts_disabled = request.session.get("alerts_disabled", False)
    alerts_disabled_until_ts = request.session.get("alerts_disabled_until_ts", None)
    alerts_disabled_until_ms = int(alerts_disabled_until_ts * 1000) if alerts_disabled_until_ts else None

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
        },
    )


def _update_alert_disabled_state(request: HttpRequest, usuario_id: int) -> None:
    try:
        user_obj = Usuario.objects.get(pk=usuario_id)
    except Exception:
        user_obj = None

    if not user_obj:
        alerts_disabled = request.session.get("alerts_disabled", False)
        alerts_disabled_until_ts = request.session.get("alerts_disabled_until_ts", None)
    else:
        alerts_disabled = user_obj.alerts_disabled
        alerts_disabled_until_ts = user_obj.alerts_disabled_until

    if alerts_disabled and alerts_disabled_until_ts:
        if _time.time() > alerts_disabled_until_ts:
            alerts_disabled = False
            alerts_disabled_until_ts = None
            if user_obj:
                user_obj.alerts_disabled = False
                user_obj.alerts_disabled_until = None
                user_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
            request.session["alerts_disabled"] = False
            request.session.pop("alerts_disabled_until_ts", None)

    request.session["alerts_disabled"] = alerts_disabled
    if alerts_disabled_until_ts:
        request.session["alerts_disabled_until_ts"] = alerts_disabled_until_ts
