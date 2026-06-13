# ruff: noqa: E402
import sys
import os
import django

# Add the project root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before Django setup
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            if _line.strip() and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.strip().split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip().strip("'\""))

# Set the Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Setup Django
django.setup()

from django.contrib.auth.hashers import make_password

from apps.users.models import (  # noqa: E402
    Persona,
    Usuario,
)
from apps.buildings.models import (
    Building,
    UserBuilding,
    MonitoringEquipment,
)
from apps.alerts.models import Notification


def populate():
    print("Iniciando limpieza de la base de datos...")
    
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE TABLE edificio, equipo_monitoreo, notificacion, persona, "
            "umbral_config, usuario, usuario_edificio RESTART IDENTITY CASCADE;"
        )
    
    print("Base de datos limpia y secuencias reiniciadas desde 0.")

    print("Iniciando población de base de datos...")

    print("Creando Personas...")
    p1, _ = Persona.objects.get_or_create(
        ci=12345678,
        defaults={
            "first_name": "Juan",
            "middle_name": "",
            "first_last_name": "Perez",
            "second_last_name": "",
            "email": "juan@example.com",
        },
    )
    p2, _ = Persona.objects.get_or_create(
        ci=87654321,
        defaults={
            "first_name": "Maria",
            "middle_name": "",
            "first_last_name": "Gomez",
            "second_last_name": "",
            "email": "maria@example.com",
        },
    )
    p3, _ = Persona.objects.get_or_create(
        ci=11223344,
        defaults={
            "first_name": "Tommy",
            "middle_name": "",
            "first_last_name": "Tupiza",
            "second_last_name": "",
            "email": "tjta3105@gmail.com",
        },
    )
    p4, _ = Persona.objects.get_or_create(
        ci=44332211,
        defaults={
            "first_name": "Admin",
            "middle_name": "",
            "first_last_name": "Sistema",
            "second_last_name": "",
            "email": "admin@example.com",
        },
    )
    p5, _ = Persona.objects.get_or_create(
        ci=55667788,
        defaults={
            "first_name": "Carlos",
            "middle_name": "",
            "first_last_name": "Rodriguez",
            "second_last_name": "",
            "email": "carlos@example.com",
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
        username="tommyt",
        defaults={"password": _hashed_pw, "id_persona": p3, "rol": "US", "registered": True},
    )
    u4, _ = Usuario.objects.get_or_create(
        username="admin",
        defaults={"password": _hashed_pw, "id_persona": p4, "rol": "SA", "registered": True},
    )
    u5, _ = Usuario.objects.get_or_create(
        username="carlosr",
        defaults={"password": _hashed_pw, "id_persona": p5, "rol": "US", "registered": True},
    )

    print("Creando Edificios...")
    e1, _ = Building.objects.get_or_create(
        rif="J-12345678-9",
        defaults={
            "name": "Conjunto Junin",
            "address": "Centro de la ciudad",
        },
    )
    e2, _ = Building.objects.get_or_create(
        rif="J-98765432-1",
        defaults={
            "name": "Residencia La Campiña",
            "address": "Norte de la ciudad",
        },
    )

    print("Asignando Usuarios a Edificios...")
    UserBuilding.objects.get_or_create(user=u1, building=e1)
    UserBuilding.objects.get_or_create(user=u2, building=e2)
    UserBuilding.objects.get_or_create(user=u3, building=e1)
    UserBuilding.objects.get_or_create(user=u5, building=e2)

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

    print("¡Población de base de datos completada exitosamente!")


if __name__ == "__main__":
    populate()
