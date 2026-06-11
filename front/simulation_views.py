"""
Vistas Django del motor de simulación.
Reemplaza toda la API que antes vivía en routes.py (Flask).
"""

import json
import logging
import time as time_module

import eventlet
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from simulation import simulators, BuildingSimulator
from simulation import (
    RATIONING_THRESHOLD, MAX_HISTORY_SIZE, PROTECTION_HOLD_SECONDS,
    inject_fault, clear_fault, reset_simulator,
)
from payload import build_live_payload_for_sim
from front.sensor_config import (
    STATS_VARS, PUMP_VARS, ELEVATOR_VARS, VAR_NAMES, UNITS,
)
from front.services.risk_service import classify_risk
from front.services.threshold_service import get_thresholds, update_threshold
from front.services.alert_service import (
    generate_recommendations,
    get_professional_action,
    get_alert_log,
    send_email_alert,
    get_building_emails,
)
from alerts import send_alert

from front.models import Edificio, EquipoMonitoreo, Notificacion, UsuarioEdificio

logger = logging.getLogger(__name__)


# ─── HELPERS ───────────────────────────────────────────────────────

def _get_sim(edificio_id):
    sim = simulators.get(edificio_id)
    if not sim:
        return None
    return sim


def _json_error(msg, status=400):
    return JsonResponse({"status": "error", "message": msg}, status=status)


def _json_ok(extra=None):
    resp = {"status": "ok"}
    if extra:
        resp.update(extra)
    return JsonResponse(resp)


# ─── SSE / REAL-TIME ──────────────────────────────────────────────

@login_required
def sse_stream(request, edificio_id):
    """Streaming SSE para un edificio específico."""
    sim = _get_sim(edificio_id)
    if not sim:
        return _json_error("Edificio no encontrado", 404)

    def event_stream():
        while True:
            eventlet.sleep(5)
            payload = build_live_payload_for_sim(sim)
            yield f"data: {json.dumps(payload)}\n\n"
            while sim.pending_notifications:
                notif = sim.pending_notifications.popleft()
                yield f"event: notification\ndata: {json.dumps(notif)}\n\n"

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


# ─── DATA API ─────────────────────────────────────────────────────

@login_required
def api_status(request):
    """Estado actual del simulador activo (primer edificio o por ?edificio_id)."""
    eid = request.GET.get("edificio_id")
    if eid:
        eid = int(eid)
    else:
        eid = next(iter(simulators.keys()), None)
    sim = _get_sim(eid)
    if not sim:
        return _json_error("No hay simuladores activos", 404)
    return JsonResponse(build_live_payload_for_sim(sim))


@login_required
def api_edificios(request):
    """Lista de edificios con sus equipos de monitoreo."""
    data = []
    for eq in EquipoMonitoreo.objects.select_related("id_edificio").all():
        if not eq.id_edificio:
            continue
        e = eq.id_edificio
        sim = simulators.get(e.id_edificio)
        data.append({
            "id": e.id_edificio,
            "nombre": e.nb_edificio,
            "direccion": e.direccion or "",
            "rif": e.rif or "",
            "tipo": eq.tipo,
            "simulador_activo": sim is not None,
            "sim_paused": sim.sim_paused if sim else False,
        })
    return JsonResponse(data, safe=False)


@login_required
def api_usuarios_edificio(request, edificio_id):
    """Usuarios asociados a un edificio."""
    usuarios = UsuarioEdificio.objects.filter(
        id_edificio_id=edificio_id
    ).select_related("id_usuario__id_persona")
    data = []
    for ue in usuarios:
        p = ue.id_usuario.id_persona if ue.id_usuario else None
        data.append({
            "id": ue.id_usuario.id_usuario if ue.id_usuario else None,
            "nombre": f"{p.nombre} {p.apellido}" if p else "Desconocido",
            "email": p.email if p else "",
        })
    return JsonResponse(data, safe=False)


@login_required
def api_notifications(request):
    """Últimas 50 notificaciones desde la BD."""
    qs = Notificacion.objects.select_related("id_edificio").order_by("-fecha_hora")[:50]
    data = []
    for n in qs:
        data.append({
            "id": n.id_notificacion,
            "timestamp": n.fecha_hora.isoformat() if n.fecha_hora else "",
            "variable": n.variable or "",
            "value": n.valor,
            "risk": n.nivel_riesgo or "",
            "message": n.mensaje or "",
            "edificio": n.id_edificio.nb_edificio if n.id_edificio else None,
        })
    return JsonResponse(data, safe=False)


# ─── UMBRALES ─────────────────────────────────────────────────────

@login_required
def view_get_thresholds(request):
    return JsonResponse(get_thresholds())


@login_required
@require_http_methods(["POST"])
def view_update_thresholds(request):
    import json as _json_mod
    try:
        data = _json_mod.loads(request.body)
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
    update_threshold(variable, risk, value)
    return _json_ok({"thresholds": get_thresholds()})


# ─── ACCIONES MANUALES ────────────────────────────────────────────

@login_required
@require_http_methods(["POST"])
def manual_update(request):
    """Actualiza manualmente una variable de sensor."""
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")

    variable = data.get("variable")
    value = data.get("value")
    edificio_id = data.get("edificio_id")

    sim = None
    if edificio_id:
        sim = _get_sim(edificio_id)
    if not sim:
        sim = next(iter(simulators.values()), None)
    if not sim:
        return _json_error("No hay simuladores activos", 404)

    sd = sim.sensor_data
    if variable not in sd:
        return _json_error("Variable no válida")

    if variable == "door_status":
        if value not in ("open", "closed"):
            return _json_error('door_status debe ser "open" o "closed"')
        sd[variable] = value
    elif variable == "motor_stuck":
        sd[variable] = bool(value)
    else:
        try:
            sd[variable] = float(value)
        except (ValueError, TypeError):
            return _json_error("Valor numérico inválido")

    risk, _ = (
        classify_risk(variable, sd[variable])
        if variable != "motor_stuck"
        else ("Crítico" if sd[variable] else "Bajo")
    )
    if risk in ("Alto", "Crítico") and sim.alert_enabled:
        action = get_professional_action(variable, risk, sd[variable])
        send_alert(
            variable,
            sd[variable],
            risk,
            f"Valor manual ({sd[variable]}): {action}",
            sim=sim,
        )

    timestamp = time_module.strftime("%Y-%m-%d %H:%M:%S")
    sensor_type = "Bomba" if variable in PUMP_VARS else "Elevador"
    sim.history.append({
        "timestamp": timestamp,
        "type": sensor_type,
        "variable": f"{variable} (manual)",
        "value": sd[variable],
        "risk": risk,
        "color": "red" if risk in ("Alto", "Crítico") else "green",
    })
    if len(sim.history) > MAX_HISTORY_SIZE:
        sim.history = sim.history[-MAX_HISTORY_SIZE:]

    return _json_ok({"variable": variable, "value": sd[variable], "risk": risk})


# ─── NOTIFICACIONES / ALERTAS ────────────────────────────────────

@login_required
@require_http_methods(["POST"])
def view_clear_alerts(request):
    """Limpia notificaciones (usa timestamp en sesión como Django)."""
    request.session["alerts_cleared_at"] = time_module.time()
    return _json_ok()


@login_required
@require_http_methods(["POST"])
def view_toggle_alerts(request):
    """Activa/desactiva alertas para un simulador."""
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    edificio_id = data.get("edificio_id")
    enabled = data.get("enabled")
    if enabled is None:
        return _json_error("Falta campo 'enabled'")
    sim = _get_sim(edificio_id) if edificio_id else next(iter(simulators.values()), None)
    if not sim:
        return _json_error("Simulador no encontrado", 404)
    sim.alert_enabled = bool(enabled)
    return _json_ok({"alert_enabled": sim.alert_enabled})


# ─── CORREOS ──────────────────────────────────────────────────────

@login_required
@require_http_methods(["POST"])
def send_test_email(request):
    """Envía un correo de prueba a un destinatario."""
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    email = data.get("email", "")
    if not email:
        return _json_error("Falta campo 'email'")
    import threading
    threading.Thread(
        target=send_email_alert,
        args=("Info", "[Prueba] Correo de prueba PCLogo", "Este es un correo de prueba del sistema PCLogo."),
        daemon=True,
    ).start()
    return _json_ok({"message": f"Correo de prueba enviado a {email}"})


@login_required
@require_http_methods(["POST"])
def send_all_subscribers(request):
    """Envía reporte a todos los suscriptores de un edificio."""
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    edificio_id = data.get("edificio_id")
    sim = _get_sim(edificio_id) if edificio_id else next(iter(simulators.values()), None)
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
    import threading
    for email in emails:
        threading.Thread(
            target=send_email_alert,
            args=("Info", subject, body, email),
            daemon=True,
        ).start()
    return _json_ok({"message": f"Reporte enviado a {len(emails)} suscriptores"})


# ─── CONTROL DEL SIMULADOR ───────────────────────────────────────

@login_required
def sim_status(request, edificio_id):
    sim = _get_sim(edificio_id)
    if not sim:
        return _json_error("Edificio no encontrado", 404)
    return JsonResponse({
        "edificio_id": sim.edificio_id,
        "nombre": sim.nombre,
        "paused": sim.sim_paused,
        "speed": sim.sim_speed,
        "pump_on": sim.pump_on,
        "elevator_on": sim.elevator_on,
        "has_pump": sim.has_pump,
        "has_elevator": sim.has_elevator,
        "faults": dict(sim.sim_faults),
        "protection_active": bool(sim.protection_ends),
        "protection_targets": list(sim.protection_ends.keys()),
        "alert_enabled": sim.alert_enabled,
    })


@login_required
@require_http_methods(["POST"])
def sim_pause(request, edificio_id):
    sim = _get_sim(edificio_id)
    if not sim:
        return _json_error("Edificio no encontrado", 404)
    try:
        data = json.loads(request.body)
        paused = data.get("paused")
        if paused is not None:
            sim.sim_paused = bool(paused)
        else:
            sim.sim_paused = not sim.sim_paused
    except Exception:
        sim.sim_paused = not sim.sim_paused
    return _json_ok({"paused": sim.sim_paused})


@login_required
@require_http_methods(["POST"])
def sim_reset(request, edificio_id):
    ok, msg = reset_simulator(edificio_id)
    if not ok:
        return _json_error(msg, 404)
    return _json_ok({"message": msg})


@login_required
@require_http_methods(["POST"])
def sim_inject_fault(request, edificio_id):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    device = data.get("device")
    fault_type = data.get("fault_type")
    if not device or not fault_type:
        return _json_error("Faltan campos: device, fault_type")
    ok, msg = inject_fault(edificio_id, device, fault_type)
    if not ok:
        return _json_error(msg)
    return _json_ok({"message": msg})


@login_required
@require_http_methods(["POST"])
def sim_clear_fault(request, edificio_id):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("JSON inválido")
    device = data.get("device")
    ok, msg = clear_fault(edificio_id, device)
    if not ok:
        return _json_error(msg, 404)
    return _json_ok({"message": msg})


@login_required
@require_http_methods(["POST"])
def sim_set_speed(request, edificio_id):
    sim = _get_sim(edificio_id)
    if not sim:
        return _json_error("Edificio no encontrado", 404)
    try:
        data = json.loads(request.body)
        speed = float(data.get("speed", 1.0))
    except Exception:
        return _json_error("JSON inválido o speed no numérico")
    sim.sim_speed = max(0.1, min(10.0, speed))
    return _json_ok({"speed": sim.sim_speed})


@login_required
@require_http_methods(["POST"])
def sim_toggle_pump(request, edificio_id):
    sim = _get_sim(edificio_id)
    if not sim:
        return _json_error("Edificio no encontrado", 404)
    try:
        data = json.loads(request.body)
        on = data.get("on")
        if on is not None:
            sim.pump_on = bool(on)
        else:
            sim.pump_on = not sim.pump_on
    except Exception:
        sim.pump_on = not sim.pump_on
    return _json_ok({"pump_on": sim.pump_on})


@login_required
@require_http_methods(["POST"])
def sim_toggle_elevator(request, edificio_id):
    sim = _get_sim(edificio_id)
    if not sim:
        return _json_error("Edificio no encontrado", 404)
    try:
        data = json.loads(request.body)
        on = data.get("on")
        if on is not None:
            sim.elevator_on = bool(on)
        else:
            sim.elevator_on = not sim.elevator_on
    except Exception:
        sim.elevator_on = not sim.elevator_on
    return _json_ok({"elevator_on": sim.elevator_on})
