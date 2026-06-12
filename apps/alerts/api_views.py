import json
import time as time_module
import threading

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.auth_decorators import _login_required, _admin_required
from apps.alerts.services.threshold_service import get_thresholds, update_threshold
from apps.alerts.services.alert_service import (
    send_email_alert,
    get_building_emails,
)
from apps.sensors.sensor_config import VAR_NAMES, UNITS


def _json_error(msg, status=400):
    return JsonResponse({"status": "error", "message": msg}, status=status)


def _json_ok(extra=None):
    resp = {"status": "ok"}
    if extra:
        resp.update(extra)
    return JsonResponse(resp)


@_login_required
@require_http_methods(["GET"])
def view_get_thresholds(request):
    return JsonResponse(get_thresholds())


@require_http_methods(["POST"])
def view_update_thresholds(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    variable = data.get("variable")
    risk = data.get("risk")
    value = data.get("value")
    if not variable or not risk or value is None:
        return _json_error("Faltan campos: variable, risk, value")
    try:
        value = float(value)
    except (ValueError, TypeError):
        return _json_error("value debe ser numérico")

    existing = get_thresholds().get(variable, {"direction": "higher", "low": 0, "medium": 0, "high": 0})
    direction = existing.get("direction", "higher")

    risk_lower = risk.lower()

    if risk_lower not in ("low", "medium", "high"):
        return _json_error(f"Riesgo inválido: {risk}")

    if value < 0:
        return _json_error("El valor del umbral no puede ser negativo.")

    if direction == "range":
        if risk_lower == "low":
            high_val = existing.get("high", 240)
            if value >= high_val:
                return _json_error(f"El límite inferior ({value}) debe ser menor que el límite superior ({high_val}).")
        elif risk_lower == "high":
            low_val = existing.get("low", 200)
            if value <= low_val:
                return _json_error(f"El límite superior ({value}) debe ser mayor que el límite inferior ({low_val}).")
        elif risk_lower in ("medium",):
            return _json_error("Para variables de rango solo se permiten thresholds 'low' y 'high'.")

    if direction == "higher":
        thresholds_ordered = {"low": 0, "medium": 0, "high": 0}
        for k in ("low", "medium", "high"):
            thresholds_ordered[k] = existing.get(k, 0)
        thresholds_ordered[risk_lower] = value

        if thresholds_ordered["low"] >= thresholds_ordered["medium"] and thresholds_ordered["medium"] != 0:
            return _json_error("El umbral 'low' debe ser menor que 'medium'.")
        if thresholds_ordered["medium"] >= thresholds_ordered["high"] and thresholds_ordered["high"] != 0:
            return _json_error("El umbral 'medium' debe ser menor que 'high'.")

    if direction == "lower":
        thresholds_ordered = {"low": 99999, "medium": 99999, "high": 99999}
        for k in ("low", "medium", "high"):
            thresholds_ordered[k] = existing.get(k, 99999)
        thresholds_ordered[risk_lower] = value

        if thresholds_ordered["low"] <= thresholds_ordered["medium"] and thresholds_ordered["medium"] != 99999:
            return _json_error("El umbral 'low' debe ser mayor que 'medium' (dirección descendente).")
        if thresholds_ordered["medium"] <= thresholds_ordered["high"] and thresholds_ordered["high"] != 99999:
            return _json_error("El umbral 'medium' debe ser mayor que 'high' (dirección descendente).")

    existing[risk_lower] = value
    update_threshold(variable, existing)
    return _json_ok({"thresholds": get_thresholds()})


@require_http_methods(["POST"])
def view_clear_alerts(request):
    request.session["alerts_cleared_at"] = time_module.time()
    return _json_ok()


@require_http_methods(["POST"])
def view_toggle_alerts(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    edificio_id = data.get("edificio_id")
    enabled = data.get("enabled")
    if enabled is None:
        return _json_error("Falta campo 'enabled'")
    from apps.sensors.simulation.globals import simulators
    sim = simulators.get(edificio_id) if edificio_id else next(iter(simulators.values()), None)
    if not sim:
        return _json_error("Simulador no encontrado", 404)
    sim.alert_enabled = bool(enabled)
    return _json_ok({"alert_enabled": sim.alert_enabled})


@require_http_methods(["POST"])
def send_test_email(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    email = data.get("email", "")
    if not email:
        return _json_error("Falta campo 'email'")
    threading.Thread(
        target=send_email_alert,
        kwargs={
            "risk_level": "Info",
            "subject": "[Prueba] Correo de prueba PCLogo",
            "body": "Este es un correo de prueba del sistema PCLogo.",
            "recipients": [email],
        },
        daemon=True,
    ).start()
    return _json_ok({"message": f"Correo de prueba enviado a {email}"})


@require_http_methods(["POST"])
def send_all_subscribers(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    edificio_id = data.get("edificio_id")
    from apps.sensors.simulation.globals import simulators
    sim = simulators.get(edificio_id) if edificio_id else next(iter(simulators.values()), None)
    if not sim:
        return _json_error("Simulador no encontrado", 404)
    emails = get_building_emails(edificio_id or sim.edificio_id)
    if not emails:
        return _json_error("No hay suscriptores para este edificio")
    timestamp = time_module.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[Reporte PCLogo] Resumen de monitoreo - {timestamp}"
    body = f"""REPORTE PERIODICO DE MONITOREO

Resumen de lecturas actuales del edificio.

Fecha/Hora: {timestamp}

Variables monitoreadas:
"""
    for var, val in sim.sensor_data.items():
        body += f"  {VAR_NAMES.get(var, var)}: {val} {UNITS.get(var, '')}\n"
    body += "\nEste reporte es generado automaticamente por el sistema PCLogo."
    for email in emails:
        threading.Thread(
            target=send_email_alert,
            args=("Info", subject, body, email),
            daemon=True,
        ).start()
    return _json_ok({"message": f"Reporte enviado a {len(emails)} suscriptores"})
