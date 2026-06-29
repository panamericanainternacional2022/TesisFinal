import datetime as dt

from apps.alerts.views.shared import _build_notification_query, exclude_severity_levels
from apps.sensors.sensor_config import RISK_INFORMATIVO

_EXCLUDED_SEVERITIES = [RISK_INFORMATIVO]


def unread_notifications(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return {"unread_notifications_count": 0}

    rol = request.session.get("usuario_rol", "US")

    notifications, _ = _build_notification_query(usuario_id, rol)

    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        cleared_dt = dt.datetime.fromtimestamp(alerts_cleared_at, tz=dt.timezone.utc)
        notifications = notifications.filter(date__gt=cleared_dt)

    notifications = exclude_severity_levels(notifications, _EXCLUDED_SEVERITIES)

    notifications_count = notifications.distinct().count()

    return {"unread_notifications_count": notifications_count}
