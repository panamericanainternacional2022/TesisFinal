from typing import Optional


def get_building_id_param(request, *param_names: str) -> str:
    if not param_names:
        param_names = ("edificio", "edificio_id", "building")
    for name in param_names:
        raw = request.GET.get(name, "")
        if raw:
            break
    raw = raw.strip()
    if raw.lower() in ("", "none", "null"):
        return ""
    return raw
