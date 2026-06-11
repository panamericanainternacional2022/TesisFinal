"""
Módulo de rutas Flask para el sistema PCLogo.
Contiene register_routes(app, socketio) que registra todos los endpoints.
"""

from simulation import MAX_HISTORY_SIZE
import json
import logging
import threading
import time

import eventlet
from flask import render_template, request, jsonify, Response
from flask_socketio import emit

from front.sensor_config import (
    VAR_NAMES, UNITS, STATS_VARS, PUMP_VARS, ELEVATOR_VARS, NO_RISK_VARS,
)
from thresholds import thresholds, save_to_db
from front.services.risk_service import classify_risk
from alerts import (
    send_alert, get_professional_action, generate_recommendations,
    send_email_alert, get_building_emails,
)
from payload import build_live_payload
from pdf_report import generate_pdf_report

import entry
import simulation

logger = logging.getLogger(__name__)


def register_routes(app, socketio):

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    @app.after_request
    def apply_cors(response):
        response.headers.set("Access-Control-Allow-Origin", "*")
        response.headers.set("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        response.headers.set("Access-Control-Allow-Credentials", "true")
        return response

    # ------------------------------------------------------------------
    # index
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("monitoreo_dashboard.html",
            no_risk_vars=NO_RISK_VARS,
            bomba_vars=PUMP_VARS,
            elevador_vars=ELEVATOR_VARS,
            var_names=VAR_NAMES,
            units=UNITS)

    # ------------------------------------------------------------------
    # API status
    # ------------------------------------------------------------------
    @app.route("/api/status")
    def api_status():
        return jsonify(build_live_payload())

    # ------------------------------------------------------------------
    # SSE streaming
    # ------------------------------------------------------------------
    @app.route("/stream/monitoreo")
    def stream_monitoring():
        def event_stream():
            while True:
                eventlet.sleep(5)
                monitoring_payload = build_live_payload()
                yield f"data: {json.dumps(monitoring_payload)}\n\n"
                while simulation.pending_notifications:
                    notification = simulation.pending_notifications.popleft()
                    yield "event: notification\n"
                    yield f"data: {json.dumps(notification)}\n\n"

        return Response(event_stream(), mimetype="text/event-stream")

    # ------------------------------------------------------------------
    # Notificaciones desde Django
    # ------------------------------------------------------------------
    @app.route("/api/notifications")
    def api_notifications():
        if not entry.DJANGO_CONNECTED:
            return jsonify({"error": "Django no está disponible"}), 500
        try:
            from front.models import Notificacion
            notifications = Notificacion.objects.select_related(
                "id_equipo_monitoreo__id_edificio"
            ).order_by("-fecha")[:50]
            payload = []
            for n in notifications:
                payload.append(
                    {
                        "id": n.id_notificacion,
                        "fecha": n.fecha.isoformat() if n.fecha else None,
                        "mensaje": n.mensaje,
                        "equipo": n.id_equipo_monitoreo.nb_equipo
                        if n.id_equipo_monitoreo
                        else None,
                        "edificio": n.id_equipo_monitoreo.id_edificio.nb_edificio
                        if n.id_equipo_monitoreo and n.id_equipo_monitoreo.id_edificio
                        else None,
                    }
                )
            return jsonify(payload)
        except Exception as e:
            logger.warning("Error al buscar notificaciones Django: %s", e)
            return jsonify({"error": str(e)}), 500

    # ------------------------------------------------------------------
    # Umbrales
    # ------------------------------------------------------------------
    @app.route("/get_thresholds")
    def get_thresholds():
        return jsonify(thresholds)

    @app.route("/update_thresholds", methods=["POST"])
    def update_thresholds():
        thresholds.update(request.json)
        save_to_db()
        return jsonify({"status": "ok", "thresholds": thresholds})

    # ------------------------------------------------------------------
    # Limpiar alertas
    # ------------------------------------------------------------------
    @app.route("/clear_alerts", methods=["POST"])
    def clear_alerts():
        simulation.alert_log.clear()
        if entry.DJANGO_CONNECTED:
            try:
                from front.models import EquipoMonitoreo, Notificacion
                equipo = EquipoMonitoreo.objects.first() if EquipoMonitoreo.objects.exists() else None
                if equipo:
                    Notificacion.objects.filter(id_equipo_monitoreo=equipo).delete()
                else:
                    Notificacion.objects.all().delete()
                logger.info("Notificaciones de Django eliminadas")
            except Exception as e:
                logger.warning("Error al eliminar notificaciones en Django: %s", e)
        return jsonify({"status": "ok", "message": "Alertas limpiadas"})

    # ------------------------------------------------------------------
    # Toggle alertas
    # ------------------------------------------------------------------
    @app.route("/toggle_alerts", methods=["POST"])
    def toggle_alerts():
        try:
            data = request.get_json(force=True, silent=True) or {}
            entry.alert_enabled = bool(data.get("enabled", True))
            logger.info("alert_enabled cambiado a: %s", entry.alert_enabled)
            return jsonify({"status": "ok", "alert_enabled": entry.alert_enabled})
        except Exception as e:
            logger.error("Error en /toggle_alerts: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 400

    # ------------------------------------------------------------------
    # Cambiar edificio activo
    # ------------------------------------------------------------------
    @app.route("/api/set_active_building/<int:edificio_id>", methods=["POST"])
    def api_set_active_building(edificio_id):
        from engine import _sync_globals_to_sim
        entry.active_edificio_id = edificio_id
        logger.info(f"Edificio activo cambiado a: {entry.active_edificio_id}")
        new_sim = simulation.simulators.get(edificio_id)
        if new_sim:
            _sync_globals_to_sim(new_sim)
            logger.info(f"Globales sincronizados al simulador: {new_sim}")
        else:
            logger.warning(f"No existe simulador para edificio_id={edificio_id} (sin equipos). Limpiando equipment_types.")
            simulation.equipment_types = set()
            simulation.pump_on = False
            simulation.elevator_on = False
            entry.equipment_types = set()
            entry.pump_on = False
            entry.elevator_on = False
        return jsonify({"status": "ok", "active_edificio_id": entry.active_edificio_id, "simuladores": list(simulation.simulators.keys())})

    # ------------------------------------------------------------------
    # Listar edificios desde Django
    # ------------------------------------------------------------------
    @app.route("/api/edificios", methods=["GET"])
    def api_edificios():
        if not entry.DJANGO_CONNECTED:
            return jsonify([{"id": 1, "nombre": "Edificio Simulado (Sin DB)"}])
        try:
            from front.models import Edificio
            edificios = Edificio.objects.all().order_by("nb_edificio")
            return jsonify([{
                "id": e.id_edificio,
                "nombre": e.nb_edificio or f"Edificio #{e.id_edificio}",
                "equipos": [{"tipo": eq.tipo, "nombre": eq.nb_equipo} for eq in e.equipomonitoreo_set.all()],
            } for e in edificios])
        except Exception as e:
            logger.error(f"Error cargando edificios: {e}")
            return jsonify([{"id": 1, "nombre": "Edificio Simulado (Error)"}])

    # ------------------------------------------------------------------
    # Usuarios de un edificio
    # ------------------------------------------------------------------
    @app.route("/api/usuarios_edificio/<int:edificio_id>", methods=["GET"])
    def api_usuarios_edificio(edificio_id):
        if not entry.DJANGO_CONNECTED:
            return jsonify([])
        try:
            from front.models import UsuarioEdificio
            users = UsuarioEdificio.objects.filter(id_edificio_id=edificio_id).select_related('id_usuario__id_persona')
            payload = []
            for u in users:
                if u.id_usuario and u.id_usuario.id_persona:
                    p = u.id_usuario.id_persona
                    if p.email:
                        payload.append({
                            "nombre": p.name or "",
                            "apellido": p.apellido or "",
                            "email": p.email.strip()
                        })
            return jsonify(payload)
        except Exception as e:
            logger.error(f"Error cargando usuarios de edificio: {e}")
            return jsonify([])

    # ------------------------------------------------------------------
    # Enviar email de prueba
    # ------------------------------------------------------------------
    @app.route("/api/send_test_email", methods=["POST"])
    def api_send_test_email():
        data = request.json
        email = data.get("email")
        risk_level = data.get("risk_level", "Bajo")
        message = "Este es tu reporte del edificio generado por el sistema de monitoreo."
        try:
            pdf_io = generate_pdf_report("hour")
            threading.Thread(
                target=send_email_alert,
                args=(risk_level, "Reporte de Edificio ", message, pdf_io, "reporte.pdf", [email]),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Error generando o enviando PDF a {email}: {e}")
            threading.Thread(
                target=send_email_alert,
                args=(risk_level, "Reporte de Edificio ", message + f"\n\n(No se pudo adjuntar el reporte: {e})", None, "reporte.pdf", [email]),
                daemon=True
            ).start()
        return jsonify({"status": "ok", "message": f"Prueba enviada a {email}"})

    # ------------------------------------------------------------------
    # Enviar a todos los suscriptores
    # ------------------------------------------------------------------
    @app.route("/api/send_all_subscribers", methods=["POST"])
    def api_send_all_subscribers():
        data = request.json
        edificio_id = data.get("edificio_id")
        risk_level = data.get("risk_level", "Bajo")
        emails = get_building_emails(edificio_id)
        if not emails:
            return jsonify({"status": "error", "message": "No hay correos registrados para este edificio"}), 400

        message = "Este es el reporte del edificio enviado a todos los suscriptores."
        try:
            pdf_io = generate_pdf_report("hour")
            threading.Thread(
                target=send_email_alert,
                args=(risk_level, "Reporte de Edificio (Masivo) ", message, pdf_io, "reporte.pdf", emails),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Error generando o enviando PDF masivo: {e}")
            threading.Thread(
                target=send_email_alert,
                args=(risk_level, "Reporte de Edificio (Masivo) ", message + f"\n\n(No se pudo adjuntar el reporte: {e})", None, "reporte.pdf", emails),
                daemon=True
            ).start()
        return jsonify({"status": "ok", "message": f"Prueba enviada a {len(emails)} destinatarios"})

    # ------------------------------------------------------------------
    # Actualización manual de sensor
    # ------------------------------------------------------------------
    @app.route("/manual_update", methods=["POST"])
    def manual_update():
        from simulation import (
            sensor_data, history, door_close_attempts, RATIONING_THRESHOLD,
        )

        data = request.json
        variable = data.get("variable")
        value = data.get("value")
        if variable not in sensor_data:
            return jsonify({"status": "error", "message": "Variable no válida"}), 400
        if variable == "door_status":
            if value not in ["open", "closed"]:
                return jsonify(
                    {"status": "error", "message": 'door_status debe ser "open" o "closed"'}
                ), 400
            sensor_data[variable] = value
        elif variable == "motor_stuck":
            sensor_data[variable] = bool(value)
        else:
            try:
                sensor_data[variable] = float(value)
            except ValueError:
                return jsonify(
                    {"status": "error", "message": "Valor numérico inválido"}
                ), 400
        risk, _ = (
            classify_risk(variable, sensor_data[variable])
            if variable != "motor_stuck"
            else ("Crítico" if sensor_data[variable] else "Bajo")
        )
        if risk in ("Alto", "Crítico") and entry.alert_enabled:
            action = get_professional_action(variable, risk, sensor_data[variable])
            send_alert(
                variable,
                sensor_data[variable],
                risk,
                f"Valor manual ({sensor_data[variable]}): {action}",
            )
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        sensor_type = "Bomba" if variable in PUMP_VARS else "Elevador"
        history.append(
            {
                "timestamp": timestamp,
                "type": sensor_type,
                "variable": f"{variable} (manual)",
                "value": sensor_data[variable],
                "risk": risk,
                "color": "red" if risk in ("Alto", "Crítico") else "green",
            }
        )
        if len(history) > MAX_HISTORY_SIZE:
            history.pop(0)
        stats = {}
        for var in STATS_VARS:
            vals = [
                r["value"]
                for r in history
                if r["variable"] == var and isinstance(r["value"], (int, float))
            ]
            if vals:
                stats[var] = {
                    "avg": sum(vals) / len(vals),
                    "min": min(vals),
                    "max": max(vals),
                }
        recs = generate_recommendations(sensor_data, stats)
        socketio.emit(
            "sensor_update",
            {
                "current": sensor_data,
                "history": history,
                "thresholds": thresholds,
                "alert_enabled": entry.alert_enabled,
                "alert_log": simulation.alert_log[:50],
                "rationing": sensor_data["flow_rate"] < RATIONING_THRESHOLD,
                "door_close_attempts": door_close_attempts,
                "recommendations": recs,
                "stats": stats,
            },
        )
        return jsonify(
            {
                "status": "ok",
                "variable": variable,
                "value": sensor_data[variable],
                "risk": risk,
            }
        )

    # ------------------------------------------------------------------
    # SIMULATOR CONTROL
    # ------------------------------------------------------------------
    @app.route("/api/sim/status")
    def api_sim_status():
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        return jsonify({
            "edificio_id": sim.edificio_id,
            "paused": sim.sim_paused,
            "speed": sim.sim_speed,
            "faults": dict(sim.sim_faults),
            "pump_on": sim.pump_on,
            "elevator_on": sim.elevator_on,
        })

    @app.route("/api/sim/pause", methods=["POST"])
    def api_sim_pause():
        data = request.get_json(force=True, silent=True) or {}
        paused = data.get("paused")
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        if paused is None:
            sim.sim_paused = not sim.sim_paused
        else:
            sim.sim_paused = bool(paused)
        logger.info(f"Simulador {'pausado' if sim.sim_paused else 'reanudado'}: edificio={sim.edificio_id}")
        return jsonify({"status": "ok", "paused": sim.sim_paused})

    @app.route("/api/sim/reset", methods=["POST"])
    def api_sim_reset():
        from engine import _sync_globals_to_sim
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        ok, msg = simulation.reset_simulator(sim.edificio_id)
        if ok:
            _sync_globals_to_sim(sim)
            logger.info(f"Simulador reiniciado: edificio={sim.edificio_id}")
            return jsonify({"status": "ok", "message": msg})
        return jsonify({"status": "error", "message": msg}), 400

    @app.route("/api/sim/inject_fault", methods=["POST"])
    def api_sim_inject_fault():
        data = request.get_json(force=True, silent=True) or {}
        device = data.get("device")
        fault_type = data.get("fault_type")
        if not device or not fault_type:
            return jsonify({"error": "device y fault_type requeridos"}), 400
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        ok, msg = simulation.inject_fault(sim.edificio_id, device, fault_type)
        if ok:
            return jsonify({"status": "ok", "message": msg, "faults": dict(sim.sim_faults)})
        return jsonify({"status": "error", "message": msg}), 400

    @app.route("/api/sim/clear_fault", methods=["POST"])
    def api_sim_clear_fault():
        data = request.get_json(force=True, silent=True) or {}
        device = data.get("device")
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        ok, msg = simulation.clear_fault(sim.edificio_id, device)
        if ok:
            return jsonify({"status": "ok", "message": msg, "faults": dict(sim.sim_faults)})
        return jsonify({"status": "error", "message": msg}), 400

    @app.route("/api/sim/set_speed", methods=["POST"])
    def api_sim_set_speed():
        data = request.get_json(force=True, silent=True) or {}
        speed = data.get("speed", 1.0)
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        sim.sim_speed = max(0.1, min(10.0, float(speed)))
        logger.info(f"Velocidad simulador cambiada a {sim.sim_speed}x: edificio={sim.edificio_id}")
        return jsonify({"status": "ok", "speed": sim.sim_speed})

    @app.route("/api/sim/toggle_pump", methods=["POST"])
    def api_sim_toggle_pump():
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        if not sim.has_pump:
            return jsonify({"error": "El edificio no tiene bomba"}), 400
        data = request.get_json(force=True, silent=True) or {}
        on = data.get("on")
        if on is None:
            sim.pump_on = not sim.pump_on
        else:
            sim.pump_on = bool(on)
        logger.info(f"Bomba {'encendida' if sim.pump_on else 'apagada'}: edificio={sim.edificio_id}")
        return jsonify({"status": "ok", "pump_on": sim.pump_on})

    @app.route("/api/sim/toggle_elevator", methods=["POST"])
    def api_sim_toggle_elevator():
        sim = simulation.simulators.get(entry.active_edificio_id)
        if not sim:
            return jsonify({"error": "No active simulator"}), 404
        if not sim.has_elevator:
            return jsonify({"error": "El edificio no tiene elevador"}), 400
        data = request.get_json(force=True, silent=True) or {}
        on = data.get("on")
        if on is None:
            sim.elevator_on = not sim.elevator_on
        else:
            sim.elevator_on = bool(on)
        logger.info(f"Elevador {'encendido' if sim.elevator_on else 'apagado'}: edificio={sim.edificio_id}")
        return jsonify({"status": "ok", "elevator_on": sim.elevator_on})

    # ------------------------------------------------------------------
    # WebSocket connect
    # ------------------------------------------------------------------
    @socketio.on("connect")
    def handle_connect():
        payload = build_live_payload()
        emit("init_data", payload)
