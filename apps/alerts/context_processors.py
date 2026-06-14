import datetime as dt
from django.db.models import Q
from apps.core.auth_decorators import is_admin_role
from apps.buildings.models import UserBuilding, MonitoringEquipment
from apps.alerts.models import Notification
from apps.sensors.sensor_config import RISK_INFO, RISK_BAJO, RISK_MEDIO

def unread_notifications(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return {"unread_notifications_count": 0}

    rol = request.session.get("usuario_rol", "US")
    
    if is_admin_role(rol):
        notifications = Notification.objects.all()
    else:
        user_buildings = UserBuilding.objects.filter(
            user_id=usuario_id
        ).values_list("building", flat=True)
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

    notifications_count = (
        notifications
        .exclude(Q(message__risk=RISK_INFO) | Q(message__contains=f'"risk": "{RISK_INFO}"') | Q(message__contains=f'"risk":"{RISK_INFO}"'))
        .exclude(Q(message__risk=RISK_BAJO) | Q(message__contains=f'"risk": "{RISK_BAJO}"') | Q(message__contains=f'"risk":"{RISK_BAJO}"'))
        .exclude(Q(message__risk=RISK_MEDIO) | Q(message__contains=f'"risk": "{RISK_MEDIO}"') | Q(message__contains=f'"risk":"{RISK_MEDIO}"'))
        .distinct()
        .count()
    )

    return {"unread_notifications_count": notifications_count}
