import json
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.buildings.models import Building
from apps.dashboard.shared import build_monitoring_config


@login_required
def render_admin_limits(request) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    buildings = list(Building.objects.all())

    from apps.core.services.http_request import get_building_id_param
    building_id = get_building_id_param(request, "edificio", "edificio_id")
    valid_ids = [b.pk for b in buildings]
    if building_id:
        try:
            building_id = int(building_id)
            if building_id not in valid_ids:
                building_id = valid_ids[0] if valid_ids else 0
        except (ValueError, TypeError, IndexError):
            building_id = valid_ids[0] if valid_ids else 0
    else:
        building_id = valid_ids[0] if valid_ids else 0

    return render(
        request,
        "limits/limits.html",
        {
            "rol": rol,
            "edificios": buildings,
            "edificio_id": building_id,
            "config_json": build_monitoring_config(building_id),
            "is_admin": True,
        },
    )


@login_required
@require_http_methods(["GET"])
def view_get_sensor_limits(request: HttpRequest) -> JsonResponse:
    from apps.limits.services import get_sensor_limits
    from apps.thresholds.services import get_thresholds
    from apps.sensors.sensor_config import LIMITS_EXCLUDE_VARS
    try:
        building_id = int(request.GET.get("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido", status=400)
    
    limits = get_sensor_limits(building_id)
    limits = {k: v for k, v in limits.items() if k not in LIMITS_EXCLUDE_VARS}
    thresholds = get_thresholds(building_id)
    return JsonResponse({
        "limits": limits,
        "thresholds": thresholds
    })


@require_http_methods(["POST"])
@login_required
@admin_required
def view_update_sensor_limits(request: HttpRequest) -> JsonResponse:
    from apps.limits.services import bulk_update_limits, get_sensor_limits
    from apps.thresholds.services import get_thresholds
    from apps.sensors.sensor_config import SENSOR_RANGES, LIMITS_EXCLUDE_VARS
    try:
        raw = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error("Invalid JSON")

    if not isinstance(raw, dict):
        return json_error("Body must be a JSON object")

    try:
        building_id = int(raw.pop("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido")

    thresholds = get_thresholds(building_id)
    data = {k: v for k, v in raw.items() if k not in LIMITS_EXCLUDE_VARS}
    errors: dict[str, str] = {}
    cleaned_data: dict[str, float] = {}

    for variable, max_val_raw in data.items():
        try:
            max_val = float(max_val_raw)
            cleaned_data[variable] = max_val
        except (ValueError, TypeError):
            errors[variable] = "Value must be numeric"
            continue

        default_min = SENSOR_RANGES.get(variable, (0.0, 100.0))[0]
        if max_val <= default_min:
            errors[variable] = f"El límite máximo ({max_val}) debe ser mayor que el mínimo por defecto ({default_min})"
            continue

        if variable in thresholds:
            t_config = thresholds[variable]
            if "high" in t_config:
                high_thresh = float(t_config["high"])
                if max_val < high_thresh:
                    label = "máximo aceptable" if t_config.get("direction") == "range" else "crítico"
                    errors[variable] = f"El límite máximo ({max_val}) no puede ser inferior al umbral {label} ({high_thresh})"

    if errors:
        return json_error(f"Validation errors: {errors}")

    try:
        bulk_update_limits(cleaned_data, building_id)
    except Exception as e:
        return json_error(str(e), status=500)

    return json_ok({
        "sensor_ranges": get_sensor_limits(building_id),
        "thresholds": get_thresholds(building_id)
    })
