#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    """Run administrative tasks."""
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                if _line.strip() and not _line.startswith("#") and "=" in _line:
                    _key, _val = _line.strip().split("=", 1)
                    os.environ.setdefault(_key.strip(), _val.strip().strip("'\""))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import eventlet
    eventlet.monkey_patch()
    try:
        import eventlet.support.psycopg2_patcher
        eventlet.support.psycopg2_patcher.make_psycopg_green()
    except ImportError:
        pass

    # ──── Inicializar simulación (solo proceso servidor, no reloader) ────
    if len(sys.argv) > 1 and sys.argv[1] == "runserver":
        if "--noreload" in sys.argv or os.environ.get("RUN_MAIN") == "true":
            import django
            django.setup()

            # Load simulators
            from apps.sensors.simulation.models import BuildingSimulator
            from apps.sensors.simulation.globals import simulators
            from apps.sensors.engine import generate_data_and_emit
            from apps.buildings.models import MonitoringEquipment
            import logging

            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )
            logger = logging.getLogger(__name__)

            equipos = MonitoringEquipment.objects.select_related("building").all()
            for eq in equipos:
                if not eq.building:
                    continue
                eid = eq.building.id
                enombre = eq.building.name or f"Edificio #{eid}"
                if eid not in simulators:
                    simulators[eid] = BuildingSimulator(eid, enombre)
                simulators[eid].equipment_types.add(eq.equipment_type)
                simulators[eid].has_pump = "bomba" in simulators[eid].equipment_types
                simulators[eid].has_elevator = "elevador" in simulators[eid].equipment_types
                simulators[eid].pump_on = simulators[eid].has_pump
                simulators[eid].elevator_on = simulators[eid].has_elevator
                logger.info(
                    "Simulador creado: edificio=%s tipo=%s", eid, eq.equipment_type
                )

            # Sincronizar variables globales legacy
            import apps.sensors.simulation.globals as _sim_globals

            _first = next(iter(simulators.values()), None)
            if _first:
                _sim_globals.sensor_data.update(_first.sensor_data)
                _sim_globals.pump_on = _first.pump_on
                _sim_globals.elevator_on = _first.elevator_on
                _sim_globals.equipment_types.clear()
                _sim_globals.equipment_types.update(_first.equipment_types)
                _sim_globals.protection_ends.update(_first.protection_ends)
                _sim_globals.active_alerts.update(_first.active_alerts)
                _sim_globals.door_close_attempts = _first.door_close_attempts
                _sim_globals.sim_paused = _first.sim_paused
                _sim_globals.sim_speed = _first.sim_speed

            # ── Watchdog: relanza el engine si muere ──────────────────────────
            def _engine_watchdog():
                """Greenlet supervisor: si generate_data_and_emit termina
                (por crash o excepción no capturada), lo relanza tras 5 s."""
                while True:
                    logger.info("Loop de simulación iniciado via manage.py runserver")
                    gt = eventlet.spawn(generate_data_and_emit)
                    try:
                        gt.wait()   # bloquea hasta que el greenlet termine
                        logger.warning(
                            "Loop de simulación terminó normalmente (inesperado) — reintentando"
                        )
                    except Exception:
                        logger.exception(
                            "Loop de simulación falló con excepción — reintentando en 5 s"
                        )
                    eventlet.sleep(5)

            eventlet.spawn(_engine_watchdog)
            logger.info("Watchdog del simulador iniciado: %d edificio(s)", len(simulators))

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
