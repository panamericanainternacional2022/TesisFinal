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

    # Intercept runserver command
    if len(sys.argv) > 1 and sys.argv[1] == "runserver":
        host = os.environ.get("SIM_HOST", "127.0.0.1")
        port = int(os.environ.get("SIM_PORT", 8000))
        
        # Simple parsing of runserver args (e.g. runserver 8000 or runserver 127.0.0.1:8000)
        for arg in sys.argv[2:]:
            if not arg.startswith("-"):
                if ":" in arg:
                    h, p = arg.split(":", 1)
                    if h: host = h
                    if p.isdigit(): port = int(p)
                elif arg.isdigit():
                    port = int(arg)

        import eventlet
        eventlet.monkey_patch()
        import eventlet.wsgi
        try:
            import eventlet.support.psycopg2_patcher
            eventlet.support.psycopg2_patcher.make_psycopg_green()
        except ImportError:
            pass
        
        import django
        django.setup()
        
        # Load simulators
        from apps.sensors.simulation.models import BuildingSimulator
        from apps.sensors.simulation.globals import simulators
        from apps.sensors.engine import generate_data_and_emit
        from apps.buildings.models import MonitoringEquipment
        import logging
        
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
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
            logger.info("Simulador creado: edificio=%s tipo=%s", eid, eq.equipment_type)
            
        if not simulators:
            from apps.buildings.models import Building as BuildingModel
            dummy_edificio, _ = BuildingModel.objects.get_or_create(
                rif="J-00000000-0",
                defaults={"name": "Edificio Simulado", "address": "Dirección simulada"},
            )
            MonitoringEquipment.objects.get_or_create(
                building=dummy_edificio, equipment_type=MonitoringEquipment.TYPE_PUMP,
                defaults={"name": f"Bomba de agua - {dummy_edificio.name}"},
            )
            MonitoringEquipment.objects.get_or_create(
                building=dummy_edificio, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
                defaults={"name": f"Elevador - {dummy_edificio.name}"},
            )
            _dummy = BuildingSimulator(1, "Edificio Simulado", equipment_types={"bomba", "elevador"})
            simulators[1] = _dummy
            logger.warning("No hay equipos en BD. Simulador dummy creado.")
            
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
            
        # Iniciar loop
        eventlet.spawn(generate_data_and_emit)
        logger.info("Loop de simulación iniciado via manage.py runserver")
        
        from django.core.handlers.wsgi import WSGIHandler
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        
        application = StaticFilesHandler(WSGIHandler())
        logger.info("Servidor PCLogo unificado (runserver) en http://%s:%s", host, port)
        eventlet.wsgi.server(eventlet.listen((host, port)), application)
        return

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
