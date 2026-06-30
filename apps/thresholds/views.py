import json
import logging
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import login_required, admin_required
from apps.core.services.http_response import json_error, json_ok
from apps.buildings.models import Building
from apps.dashboard.shared import build_monitoring_config
from apps.thresholds.services import get_thresholds, bulk_update, ThresholdPersistenceError

logger = logging.getLogger(__name__)
VALID_DIRECTIONS = frozenset({"higher", "lower", "range"})


@login_required
def render_admin_thresholds(request) -> HttpResponse:
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
        "thresholds/thresholds.html",
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
def view_get_thresholds(request: HttpRequest) -> JsonResponse:
    try:
        building_id = int(request.GET.get("edificio_id", 0))
    except (ValueError, TypeError):
        building_id = 0
    if not building_id:
        return json_error("edificio_id requerido", status=400)
    return JsonResponse(get_thresholds(building_id))


@require_http_methods(["POST"])
@login_required
@admin_required
def view_update_thresholds(request: HttpRequest) -> JsonResponse:
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

    data = raw
    errors: dict[str, str] = {}

    for variable, config in data.items():
        if not isinstance(config, dict):
            errors[variable] = "Invalid config format"
            continue

        direction = config.get("direction")
        if direction not in VALID_DIRECTIONS:
            errors[variable] = f"Invalid direction: {direction}"
            continue

        try:
            config["low"] = float(config.get("low", 0))
            if direction == "range":
                if "high" not in config:
                    errors[variable] = "Missing 'high' for range direction"
                    continue
                config["high"] = float(config["high"])
            else:
                config["medium"] = float(config.get("medium", 0))
                config["high"] = float(config.get("high", 0))
        except (ValueError, TypeError) as e:
            errors[variable] = f"Non-numeric threshold value: config={config}"
            logger.warning("Threshold non-numeric for %s: %s — config=%s", variable, e, config)
            continue

        if direction == "range":
            if config["low"] >= config["high"]:
                errors[variable] = f"Low limit ({config['low']}) must be lower than high limit ({config['high']})"
                logger.warning("Threshold range fail for %s: low=%s high=%s", variable, config['low'], config['high'])
                continue
        elif direction == "higher":
            if not (config["low"] < config["medium"] < config["high"]):
                errors[variable] = f"Thresholds must be ascending: low={config['low']} < medium={config['medium']} < high={config['high']}"
                logger.warning("Threshold higher fail for %s: low=%s med=%s high=%s", variable, config['low'], config['medium'], config['high'])
                continue
        elif direction == "lower":
            if not (config["low"] > config["medium"] > config["high"]):
                errors[variable] = "Thresholds must be descending: low > medium > high"
                continue

        from apps.limits.services import get_sensor_limits
        sensor_limits = get_sensor_limits(building_id)
        limits = sensor_limits.get(variable)
        if limits:
            min_bound, max_bound = limits
            low_val = config["low"]
            high_val = config["high"]
            if direction == "range":
                if low_val < min_bound or high_val > max_bound:
                    errors[variable] = f"Los umbrales [{low_val}, {high_val}] deben estar dentro de los límites físicos del sensor [{min_bound}, {max_bound}]"
                    continue
            elif direction == "higher":
                if low_val < min_bound or high_val > max_bound:
                    errors[variable] = f"Los umbrales deben estar dentro de los límites físicos del sensor [{min_bound}, {max_bound}] (recibido low={low_val}, high={high_val})"
                    continue
            elif direction == "lower":
                if low_val > max_bound or high_val < min_bound:
                    errors[variable] = f"Los umbrales deben estar dentro de los límites físicos del sensor [{min_bound}, {max_bound}] (recibido low={low_val}, high={high_val})"
                    continue

    if errors:
        return json_error(f"Validation errors: {errors}")

    try:
        bulk_update(data, building_id)
    except ThresholdPersistenceError as e:
        return json_error(str(e), status=500)

    return json_ok({"thresholds": get_thresholds(building_id)})
