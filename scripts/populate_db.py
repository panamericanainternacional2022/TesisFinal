import sys
import os
import django
from django.utils import timezone

# Add the project root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set the Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Setup Django
django.setup()

from front.models import (  # noqa: E402
    Persona,
    Usuario,
    Edificio,
    UsuarioEdificio,
    EquipoMonitoreo,
    DisposSensor,
    EquipoSensor,
    Status,
    StatusEquipoMonitoreo,
    AccionPrev,
    Notificacion,
    HistoricoFalla,
)


def populate():
    print("Iniciando limpieza de la base de datos...")
    
    # Eliminar en orden inverso de dependencias para evitar errores de llave foránea
    HistoricoFalla.objects.all().delete()
    Notificacion.objects.all().delete()
    AccionPrev.objects.all().delete()
    StatusEquipoMonitoreo.objects.all().delete()
    EquipoSensor.objects.all().delete()
    UsuarioEdificio.objects.all().delete()
    Status.objects.all().delete()
    DisposSensor.objects.all().delete()
    EquipoMonitoreo.objects.all().delete()
    Edificio.objects.all().delete()
    Usuario.objects.all().delete()
    Persona.objects.all().delete()
    
    print("Base de datos limpia.")

    print("Iniciando población de base de datos...")

    print("Creando Personas...")
    p1, _ = Persona.objects.get_or_create(
        ci=12345678,
        defaults={
            "name": "Juan",
            "apellido": "Perez",
            "email": "juan@example.com",
            "telefono": "04141234567",
        },
    )
    p2, _ = Persona.objects.get_or_create(
        ci=87654321,
        defaults={
            "name": "Maria",
            "apellido": "Gomez",
            "email": "maria@example.com",
            "telefono": "04121234567",
        },
    )
    p3, _ = Persona.objects.get_or_create(
        ci=11223344,
        defaults={
            "name": "Tommy",
            "apellido": "Tupiza",
            "email": "tjta3105@gmail.com",
            "telefono": "04241234567",
        },
    )
    p4, _ = Persona.objects.get_or_create(
        ci=44332211,
        defaults={
            "name": "Admin",
            "apellido": "Sistema",
            "email": "admin@example.com",
            "telefono": "04161234567",
        },
    )
    p5, _ = Persona.objects.get_or_create(
        ci=55667788,
        defaults={
            "name": "Carlos",
            "apellido": "Rodriguez",
            "email": "carlos@example.com",
            "telefono": "04149876543",
        },
    )

    print("Creando Usuarios...")
    u1, _ = Usuario.objects.get_or_create(
        username="juanp",
        defaults={"password": "password123", "id_persona": p1, "rol": "US", "registrado": True},
    )
    u2, _ = Usuario.objects.get_or_create(
        username="mariag",
        defaults={"password": "password123", "id_persona": p2, "rol": "US", "registrado": True},
    )
    u3, _ = Usuario.objects.get_or_create(
        username="tommyt",
        defaults={"password": "password123", "id_persona": p3, "rol": "US", "registrado": True},
    )
    u4, _ = Usuario.objects.get_or_create(
        username="admin",
        defaults={"password": "password123", "id_persona": p4, "rol": "SA", "registrado": True},
    )
    u5, _ = Usuario.objects.get_or_create(
        username="carlosr",
        defaults={"password": "password123", "id_persona": p5, "rol": "US", "registrado": True},
    )

    print("Creando Edificios...")
    e1, _ = Edificio.objects.get_or_create(
        rif="J-12345678-9",
        defaults={
            "nb_edificio": "Conjunto Junin",
            "direccion": "Centro de la ciudad",
        },
    )
    e2, _ = Edificio.objects.get_or_create(
        rif="J-98765432-1",
        defaults={
            "nb_edificio": "Residencia La Campiña",
            "direccion": "Norte de la ciudad",
        },
    )

    print("Asignando Usuarios a Edificios...")
    UsuarioEdificio.objects.get_or_create(id_usuario=u1, id_edificio=e1)
    UsuarioEdificio.objects.get_or_create(id_usuario=u2, id_edificio=e2)
    UsuarioEdificio.objects.get_or_create(id_usuario=u3, id_edificio=e1)
    UsuarioEdificio.objects.get_or_create(id_usuario=u5, id_edificio=e2)

    print("Creando Equipos de Monitoreo...")
    eq1_bomba, _ = EquipoMonitoreo.objects.get_or_create(
        id_edificio=e1, tipo=EquipoMonitoreo.TIPO_BOMBA,
        defaults={"nb_equipo": f"Bomba de agua - {e1.nb_edificio}"},
    )
    eq1_elevador, _ = EquipoMonitoreo.objects.get_or_create(
        id_edificio=e1, tipo=EquipoMonitoreo.TIPO_ELEVADOR,
        defaults={"nb_equipo": f"Elevador - {e1.nb_edificio}"},
    )
    eq2_bomba, _ = EquipoMonitoreo.objects.get_or_create(
        id_edificio=e2, tipo=EquipoMonitoreo.TIPO_BOMBA,
        defaults={"nb_equipo": f"Bomba de agua - {e2.nb_edificio}"},
    )

    print("Creando Dispositivos Sensores...")
    ds1, _ = DisposSensor.objects.get_or_create(
        nb_sensor="Sensor de Temperatura", modelo_iot="TempIOT-01"
    )
    ds2, _ = DisposSensor.objects.get_or_create(
        nb_sensor="Sensor de Voltaje", modelo_iot="VoltIOT-02"
    )
    ds3, _ = DisposSensor.objects.get_or_create(
        nb_sensor="Sensor de Corriente", modelo_iot="CurrIOT-03"
    )

    print("Asociando Sensores a Equipos (EquipoSensor)...")
    es1, _ = EquipoSensor.objects.get_or_create(
        id_equipo_monitoreo=eq1_bomba,
        id_dispos_sensor=ds1,
        defaults={
            "tipo_valor_capt": 35.5,
            "fecha_hora_lect": timezone.now(),
            "descripcion_falla": "Normal",
        },
    )
    es2, _ = EquipoSensor.objects.get_or_create(
        id_equipo_monitoreo=eq1_bomba,
        id_dispos_sensor=ds2,
        defaults={
            "tipo_valor_capt": 220.0,
            "fecha_hora_lect": timezone.now(),
            "descripcion_falla": "Normal",
        },
    )

    print("Creando Status...")
    s1, _ = Status.objects.get_or_create(nb_status="Operativo")
    s2, _ = Status.objects.get_or_create(nb_status="Falla")
    s3, _ = Status.objects.get_or_create(nb_status="Mantenimiento")

    print("Asignando Status a Equipos...")
    sem1, _ = StatusEquipoMonitoreo.objects.get_or_create(
        id_status=s1, id_equipo_monitoreo=eq1_bomba
    )
    sem2, _ = StatusEquipoMonitoreo.objects.get_or_create(
        id_status=s1, id_equipo_monitoreo=eq2_bomba
    )
    sem3, _ = StatusEquipoMonitoreo.objects.get_or_create(
        id_status=s1, id_equipo_monitoreo=eq1_elevador
    )

    print("¡Población de base de datos completada exitosamente!")


if __name__ == "__main__":
    populate()
