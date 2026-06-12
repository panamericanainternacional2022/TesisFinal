import json
import time as _time

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import _login_required, _is_admin_role
from apps.users.models import Usuario
from apps.buildings.models import Edificio, UsuarioEdificio, EquipoMonitoreo
from apps.alerts.models import Notificacion
from apps.sensors.sensor_config import (
    VAR_NAMES, UNITS, RISK_NAMES_ES, DEVICE_NAMES_ES, VALUE_DISPLAY_ES,
)
from django.db.models import Q
from django.core.paginator import Paginator


def _parse_notif_for_historial(notif):
    import re
    import json as _json

    var_names = VAR_NAMES
    units = UNITS
    risk_names_es = RISK_NAMES_ES
    device_names_es = DEVICE_NAMES_ES

    def _translate_devices(text):
        for en, es in device_names_es.items():
            text = re.sub(rf"\b{re.escape(en)}\b", es, text, flags=re.IGNORECASE)
        return text

    def _build_protection_action(risk, raw_action):
        risk_es = risk_names_es.get(risk, risk.lower())
        devices_match = re.search(r"[Dd]ispositivos?\s+apagados?:\s*(.+)", raw_action)
        if devices_match:
            devices_es = _translate_devices(devices_match.group(1).rstrip("."))
            return f"Protección automática activada (alerta {risk_es}). Dispositivos apagados: {devices_es}."
        return f"Protección automática activada (alerta {risk_es}). {_translate_devices(raw_action)}"

    def _make_parsed(risk, variable, value, action):
        var_display = var_names.get(variable, variable.replace("_", " ").title())
        value_str = str(value).lower().strip() if value is not None else ""

        if variable in VALUE_DISPLAY_ES:
            value_display = VALUE_DISPLAY_ES[variable].get(value_str, str(value).capitalize())
        elif value_str == "pump":
            value_display = "Bomba de agua"
        elif value_str == "elevator":
            value_display = "Elevador"
        elif value_str in device_names_es:
            value_display = device_names_es[value_str].capitalize()
        elif value_str:
            value_display = value_str.capitalize()
        else:
            value_display = ""

        if variable == "Protección automática":
            action = _build_protection_action(risk, action)
        elif variable.startswith("Protección "):
            action = _translate_devices(action)
        return {
            "parsed": True,
            "risk": risk,
            "variable": var_display,
            "value": value_display,
            "unit": units.get(variable, ""),
            "action": action,
        }

    raw = (notif.mensaje or "").strip()
    parsed_data = None

    if raw.startswith("{"):
        try:
            data = _json.loads(raw)
            parsed_data = _make_parsed(
                risk=data.get("risk", ""),
                variable=data.get("variable", ""),
                value=data.get("value") or "",
                action=data.get("action", ""),
            )
        except (ValueError, KeyError):
            parsed_data = None

    if parsed_data is None:
        m = re.match(r"^\[(.*?)\]\s+(.*?)\s+=\s+(.*?)\s+-\s+(.*)$", raw)
        if m:
            parsed_data = _make_parsed(
                risk=m.group(1).strip(),
                variable=m.group(2).strip(),
                value=m.group(3).strip(),
                action=m.group(4).strip(),
            )

    if parsed_data is None:
        pm = re.match(
            r"Protecci[oó]n autom[áa]tica activada\s*\(Alerta\s+(\w+)\s+de\s+(\w+)\).+\s*Dispositivos\s+apagados:\s*(.+)",
            raw,
            re.IGNORECASE,
        )
        if pm:
            p_risk = pm.group(1).strip().capitalize()
            p_variable = pm.group(2).strip()
            p_devices_es = _translate_devices(pm.group(3).rstrip("."))
            p_risk_es = risk_names_es.get(p_risk, p_risk.lower())
            p_var_es = var_names.get(p_variable, p_variable.replace("_", " "))
            parsed_data = {
                "parsed": True,
                "risk": p_risk,
                "variable": "Protección automática",
                "value": "True",
                "unit": "",
                "action": (
                    f"Protección automática activada ({p_var_es} {p_risk_es}). "
                    f"Dispositivos apagados: {p_devices_es}."
                ),
            }

    notif.parsed_data = parsed_data or {"parsed": False}
    return notif


@_login_required
def notificaciones_view(request):
    usuario_id = request.session["usuario_id"]
    rol = request.session.get("usuario_rol", "US")
    edificio_id = request.GET.get("edificio", "").strip()

    if _is_admin_role(rol):
        edificios = Edificio.objects.all()
        notificaciones = Notificacion.objects.all()
        if edificio_id:
            notificaciones = notificaciones.filter(id_equipo_monitoreo__id_edificio_id=edificio_id)
    else:
        usuario_edificios = UsuarioEdificio.objects.filter(
            id_usuario_id=usuario_id
        ).values_list("id_edificio", flat=True)
        edificios = Edificio.objects.filter(id_edificio__in=usuario_edificios)

        if edificio_id:
            if edificio_id.isdigit() and int(edificio_id) in list(usuario_edificios):
                notificaciones = Notificacion.objects.filter(id_equipo_monitoreo__id_edificio_id=edificio_id)
            else:
                notificaciones = Notificacion.objects.none()
        else:
            equipos = EquipoMonitoreo.objects.filter(
                id_edificio_id__in=list(usuario_edificios)
            ).values_list("id_equipo_monitoreo", flat=True)
            notificaciones = Notificacion.objects.filter(
                id_usuario_id=usuario_id
            ) | Notificacion.objects.filter(id_equipo_monitoreo_id__in=list(equipos))

    alerts_cleared_at = request.session.get("alerts_cleared_at")
    if alerts_cleared_at:
        import datetime as dt
        cleared_dt = dt.datetime.fromtimestamp(alerts_cleared_at, tz=dt.timezone.utc)
        notificaciones = notificaciones.filter(fecha__gt=cleared_dt)

    notificaciones = (
        notificaciones.select_related("id_usuario", "id_equipo_monitoreo__id_edificio")
        .exclude(mensaje__contains='"risk": "Info"')
        .exclude(mensaje__contains='"risk":"Info"')
        .exclude(mensaje__contains='"risk": "Bajo"')
        .exclude(mensaje__contains='"risk":"Bajo"')
        .exclude(mensaje__contains='"risk": "Medio"')
        .exclude(mensaje__contains='"risk":"Medio"')
        .distinct()
        .order_by("-fecha")
    )

    paginator = Paginator(notificaciones, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for notif in page_obj:
        _parse_notif_for_historial(notif)

    usuario_id = request.session["usuario_id"]
    try:
        _usuario_obj = Usuario.objects.get(pk=usuario_id)
    except Exception:
        _usuario_obj = None

    if _usuario_obj:
        alertas_desactivadas = _usuario_obj.alerts_disabled
        alerts_disabled_until_ts = _usuario_obj.alerts_disabled_until
    else:
        alertas_desactivadas = request.session.get("alerts_disabled", False)
        alerts_disabled_until_ts = request.session.get("alerts_disabled_until_ts", None)

    if alertas_desactivadas and alerts_disabled_until_ts:
        if _time.time() > alerts_disabled_until_ts:
            alertas_desactivadas = False
            alerts_disabled_until_ts = None
            if _usuario_obj:
                _usuario_obj.alerts_disabled = False
                _usuario_obj.alerts_disabled_until = None
                _usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
            request.session["alerts_disabled"] = False
            request.session.pop("alerts_disabled_until_ts", None)

    alerts_disabled_until_ms = int(alerts_disabled_until_ts * 1000) if alerts_disabled_until_ts else None

    return render(
        request,
        "alerts/notificaciones.html",
        {
            "notificaciones": page_obj,
            "edificios": edificios,
            "selected_edificio_id": int(edificio_id) if edificio_id.isdigit() else None,
            "rol": rol,
            "alertas_desactivadas": alertas_desactivadas,
            "alerts_disabled_until_ms": alerts_disabled_until_ms,
        },
    )


@_login_required
def toggle_alerts_session_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            enabled = data.get("enabled", True)
            duration_minutes = data.get("duration_minutes", None)

            usuario_id = request.session.get("usuario_id")
            try:
                usuario_obj = Usuario.objects.get(pk=usuario_id)
            except Exception:
                usuario_obj = None

            if enabled:
                if usuario_obj:
                    usuario_obj.alerts_disabled = False
                    usuario_obj.alerts_disabled_until = None
                    usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
                request.session["alerts_disabled"] = False
                request.session.pop("alerts_disabled_until_ts", None)
                return JsonResponse({"status": "ok", "alerts_disabled": False, "alerts_disabled_until_ms": None})
            else:
                until_ts = None
                if duration_minutes is not None:
                    until_ts = _time.time() + float(duration_minutes) * 60
                if usuario_obj:
                    usuario_obj.alerts_disabled = True
                    usuario_obj.alerts_disabled_until = until_ts
                    usuario_obj.save(update_fields=["alerts_disabled", "alerts_disabled_until"])
                request.session["alerts_disabled"] = True
                if until_ts:
                    request.session["alerts_disabled_until_ts"] = until_ts
                else:
                    request.session.pop("alerts_disabled_until_ts", None)
                until_ms = int(until_ts * 1000) if until_ts else None
                return JsonResponse({"status": "ok", "alerts_disabled": True, "alerts_disabled_until_ms": until_ms})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"status": "error", "message": "Método no permitido"}, status=405)


@_login_required
def limpiar_notificaciones_view(request):
    if request.method == "POST":
        request.session["alerts_cleared_at"] = _time.time()
        return JsonResponse(
            {"status": "ok", "message": "Alertas limpiadas correctamente"}
        )
    return JsonResponse(
        {"status": "error", "message": "Método no permitido"}, status=405
    )
