import datetime as dt

from django.db.models import Q, QuerySet
from django.utils import timezone as tz

from apps.buildings.models import Building, UserBuilding, MonitoringEquipment
from apps.alerts.models import Notification


ALL_SEVERITIES = ["Info", "Bajo", "Medio", "Alto", "Crítico"]

DELTA_MAP = {
    "1h":  dt.timedelta(hours=1),
    "12h": dt.timedelta(hours=12),
    "24h": dt.timedelta(hours=24),
    "3d":  dt.timedelta(days=3),
    "7d":  dt.timedelta(days=7),
}


def build_monitoring_config(building_id: int) -> str:
    import json
    from apps.sensors.sensor_config import NO_RISK_VARS, PUMP_VARS, ELEVATOR_VARS, VAR_NAMES, UNITS
    return json.dumps({
        "no_risk_vars": NO_RISK_VARS,
        "pump_vars": PUMP_VARS,
        "elevator_vars": ELEVATOR_VARS,
        "var_names": VAR_NAMES,
        "units": UNITS,
        "edificio_id": building_id,
    })


def get_equipment_sensors(equipment: MonitoringEquipment) -> list[dict]:
    from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS, VAR_NAMES, UNITS
    variable_list = PUMP_VARS if equipment.equipment_type == MonitoringEquipment.TYPE_PUMP else ELEVATOR_VARS
    return [
        {"nombre": VAR_NAMES.get(v, v), "unidad": UNITS.get(v, "")}
        for v in variable_list
    ]


def filter_severity(queryset: QuerySet, severity: str) -> QuerySet:
    if severity and severity in ALL_SEVERITIES:
        return queryset.filter(
            Q(message__risk=severity)
            | Q(message__contains=f'"risk": "{severity}"')
            | Q(message__contains=f'"risk":"{severity}"')
        )
    return queryset


def filter_date_range(queryset: QuerySet, period: str, date_from: str, date_to: str) -> QuerySet:
    now = tz.now()
    if period in DELTA_MAP:
        delta = DELTA_MAP[period]
        return queryset.filter(date__gte=now - delta)
    if period == "custom":
        if date_from:
            try:
                naive = dt.datetime.strptime(date_from, "%Y-%m-%d")
                queryset = queryset.filter(date__gte=tz.make_aware(naive))
            except ValueError:
                pass
        if date_to:
            try:
                naive = dt.datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                queryset = queryset.filter(date__lte=tz.make_aware(naive))
            except ValueError:
                pass
    return queryset


def build_query_string(**params: str) -> str:
    return "&".join(f"{k}={v}" for k, v in params.items() if v)


def get_user_building_ids(user_id: int) -> list[int]:
    return list(UserBuilding.objects.filter(user_id=user_id).values_list("building_id", flat=True))


def parse_notifications(notifications: QuerySet) -> list:
    from apps.alerts.views.shared import parse_notification_for_display
    parsed = []
    for notif in notifications:
        parsed.append(parse_notification_for_display(notif))
    return parsed


def extract_variables(parsed_list: list) -> list[str]:
    return sorted(set(
        n.parsed_data.get("variable", "")
        for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable")
    ))


def filter_by_variable(parsed_list: list, variable: str) -> list:
    if not variable:
        return parsed_list
    return [
        n for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable
    ]
