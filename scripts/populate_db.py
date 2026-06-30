import sys
import os
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            if _line.strip() and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.strip().split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip().strip("'\""))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django.setup()

import random

from django.contrib.auth.hashers import make_password

from apps.users.models import (
    Persona,
    Usuario,
)
from apps.buildings.models import (
    Building,
    UserBuilding,
    MonitoringEquipment,
)
from apps.events.models import Notification
from apps.thresholds.models import ThresholdConfig
from apps.limits.models import SensorLimitConfig
from apps.sensors.sensor_config import DEFAULT_THRESHOLDS, SENSOR_RANGES


def populate():
    print("Iniciando limpieza de la base de datos...")
    
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE TABLE edificio, equipo_monitoreo, notificacion, persona, "
            "umbral_config, limite_sensor_config, usuario, usuario_edificio RESTART IDENTITY CASCADE;"
        )
    
    print("Base de datos limpia y secuencias reiniciadas desde 0.")

    print("Iniciando población de base de datos...")

    print("Creando Personas...")

    def random_ci(num):
        prefix = random.choice(["V-", "E-"])
        return f"{prefix}{num}"

    p1, _ = Persona.objects.get_or_create(
        ci=random_ci(12345678),
        defaults={
            "first_name": "Juan",
            "middle_name": "",
            "first_last_name": "Perez",
            "second_last_name": "",
            "email": "mantillaqed@gmail.com",
        },
    )
    p2, _ = Persona.objects.get_or_create(
        ci=random_ci(87654321),
        defaults={
            "first_name": "Maria",
            "middle_name": "",
            "first_last_name": "Gomez",
            "second_last_name": "",
            "email": "elvistek2012@gmail.com",
        },
    )
    p3, _ = Persona.objects.get_or_create(
        ci=random_ci(44332211),
        defaults={
            "first_name": "David",
            "middle_name": "",
            "first_last_name": "Mantilla",
            "second_last_name": "",
            "email": "mantillaquid@gmail.com",
        },
    )
    p4, _ = Persona.objects.get_or_create(
        ci=random_ci(11223344),
        defaults={
            "first_name": "Admin",
            "middle_name": "",
            "first_last_name": "Admin",
            "second_last_name": "",
            "email": "admin@example.com",
        },
    )

    print("Creando Usuarios...")
    _hashed_pw = make_password("password123")
    u1, _ = Usuario.objects.get_or_create(
        username="juanp",
        defaults={"password": _hashed_pw, "id_persona": p1, "rol": "US", "registered": True},
    )
    u2, _ = Usuario.objects.get_or_create(
        username="mariag",
        defaults={"password": _hashed_pw, "id_persona": p2, "rol": "US", "registered": True},
    )
    u3, _ = Usuario.objects.get_or_create(
        username="davidm",
        defaults={"password": _hashed_pw, "id_persona": p3, "rol": "US", "registered": True},
    )
    u4, _ = Usuario.objects.get_or_create(
        username="admin",
        defaults={"password": _hashed_pw, "id_persona": p4, "rol": "SA", "registered": True},
    )

    print("Creando Edificios...")
    e1, _ = Building.objects.get_or_create(
        rif="J-12345678-9",
        defaults={
            "name": "Conjunto Junin",
            "address": "Centro de la ciudad",
            "floors": 10,
        },
    )
    e2, _ = Building.objects.get_or_create(
        rif="J-98765432-1",
        defaults={
            "name": "Residencia La Campiña",
            "address": "Norte de la ciudad",
            "floors": 15,
        },
    )

    print("Asignando Usuarios a Edificios...")
    UserBuilding.objects.get_or_create(user=u1, building=e1)
    UserBuilding.objects.get_or_create(user=u2, building=e2)
    UserBuilding.objects.get_or_create(user=u3, building=e1)
    UserBuilding.objects.get_or_create(user=u3, building=e2)
    UserBuilding.objects.get_or_create(user=u4, building=e1)
    UserBuilding.objects.get_or_create(user=u4, building=e2)

    print("Creando Equipos de Monitoreo...")
    eq1_bomba, _ = MonitoringEquipment.objects.get_or_create(
        building=e1, equipment_type=MonitoringEquipment.TYPE_PUMP,
        defaults={"name": "Bomba de agua"},
    )
    eq1_elevador, _ = MonitoringEquipment.objects.get_or_create(
        building=e1, equipment_type=MonitoringEquipment.TYPE_ELEVATOR,
        defaults={"name": "Elevador"},
    )
    eq2_bomba, _ = MonitoringEquipment.objects.get_or_create(
        building=e2, equipment_type=MonitoringEquipment.TYPE_PUMP,
        defaults={"name": "Bomba de agua"},
    )

    print("Sembrando umbrales por edificio...")
    for edificio in [e1, e2]:
        for variable, cfg in DEFAULT_THRESHOLDS.items():
            ThresholdConfig.objects.update_or_create(
                building=edificio,
                variable=variable,
                defaults={
                    "direction": cfg.get("direction", "higher"),
                    "low": cfg.get("low", 0),
                    "medium": cfg.get("medium"),
                    "high": cfg.get("high", 0),
                },
            )

    print("Sembrando límites de sensores por edificio...")
    for edificio in [e1, e2]:
        for variable, val_range in SENSOR_RANGES.items():
            SensorLimitConfig.objects.get_or_create(
                building=edificio,
                variable=variable,
                defaults={
                    "max_value": val_range[1],
                },
            )

    print("¡Población de base de datos completada exitosamente!")


if __name__ == "__main__":
    populate()
