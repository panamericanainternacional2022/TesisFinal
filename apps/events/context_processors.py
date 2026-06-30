import datetime as dt

from apps.events.shared import _build_notification_query


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

    notifications_count = notifications.distinct().count()

    return {"unread_notifications_count": notifications_count}
