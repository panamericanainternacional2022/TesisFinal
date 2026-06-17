import datetime as dt

from django.db.models import Q, QuerySet
from django.utils import timezone as tz

from apps.buildings.models import UserBuilding, MonitoringEquipment
from apps.sensors.sensor_config import SEVERITY_LEVELS
from apps.core.date_utils import PERIOD_DELTA_MAP


ALL_SEVERITIES = SEVERITY_LEVELS
DELTA_MAP = PERIOD_DELTA_MAP


def build_monitoring_config(building_id: int) -> dict:
    from apps.sensors.sensor_config import (
        NO_RISK_VARS, PUMP_VARS, ELEVATOR_VARS, VAR_NAMES, UNITS,
        RISK_INFO, RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO, RISK_UNKNOWN,
        VALUE_DISPLAY_ES, SENSOR_RANGES
    )
    return {
        "no_risk_vars": NO_RISK_VARS,
        "pump_vars": PUMP_VARS,
        "elevator_vars": ELEVATOR_VARS,
        "var_names": VAR_NAMES,
        "units": UNITS,
        "value_display_es": VALUE_DISPLAY_ES,
        "sensor_ranges": SENSOR_RANGES,
        "edificio_id": building_id,
        "risk_labels": {
            "info": RISK_INFO,
            "bajo": RISK_BAJO,
            "medio": RISK_MEDIO,
            "alto": RISK_ALTO,
            "critico": RISK_CRITICO,
            "unknown": RISK_UNKNOWN,
        },
    }


def get_equipment_sensors(equipment: MonitoringEquipment) -> list[dict]:
    from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS, VAR_NAMES, UNITS
    variable_list = PUMP_VARS if equipment.equipment_type == MonitoringEquipment.TYPE_PUMP else ELEVATOR_VARS
    return [
        {"nombre": VAR_NAMES.get(v, v), "unidad": UNITS.get(v, "")}
        for v in variable_list
    ]


def filter_severity(queryset: QuerySet, severity: str) -> QuerySet:
    from apps.alerts.views.shared import filter_severity_include
    return filter_severity_include(queryset, severity)


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
    return sorted({
        n.parsed_data["variable"]
        for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable")
    })


def extract_severities(parsed_list: list) -> list[str]:
    from apps.sensors.sensor_config import SEVERITY_LEVELS
    present = {
        n.parsed_data["risk"]
        for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("risk")
    }
    return [s for s in SEVERITY_LEVELS if s in present]


def filter_severity_python(parsed_list: list, severity: str) -> list:
    if not severity:
        return parsed_list
    return [
        n for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("risk") == severity
    ]


def filter_by_variable(parsed_list: list, variable: str) -> list:
    if not variable:
        return parsed_list
    return [
        n for n in parsed_list
        if n.parsed_data.get("parsed") and n.parsed_data.get("variable") == variable
    ]
