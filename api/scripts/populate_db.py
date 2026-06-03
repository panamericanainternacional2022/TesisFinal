import sys
import os
import django
from django.utils import timezone

# Add the project root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set the Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

# Setup Django
django.setup()

from core.models import (  # noqa: E402
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
    print("Iniciando población de base de datos...")

    print("Creando Personas...")
    p1, _ = Persona.objects.get_or_create(
        ci=12345678,
        defaults={
            "name": "Juan",
            "apellido": "Perez",
            "email": "juan@example.com",
            "telefono": "04141234567",
            "direccion": "Av Principal",
        },
    )
    p2, _ = Persona.objects.get_or_create(
        ci=87654321,
        defaults={
            "name": "Maria",
            "apellido": "Gomez",
            "email": "maria@example.com",
            "telefono": "04121234567",
            "direccion": "Av Secundaria",
        },
    )

    print("Creando Usuarios...")
    u1, _ = Usuario.objects.get_or_create(
        username="juanp",
        defaults={"password": "password123", "id_persona": p1, "rol": "SA"},
    )
    u2, _ = Usuario.objects.get_or_create(
        username="mariag",
        defaults={"password": "password123", "id_persona": p2, "rol": "US"},
    )

    print("Creando Edificios...")
    e1, _ = Edificio.objects.get_or_create(
        rif="J-12345678-9",
        defaults={
            "nb_edificio": "Edificio Central",
            "direccion": "Centro de la ciudad",
        },
    )
    e2, _ = Edificio.objects.get_or_create(
        rif="J-98765432-1",
        defaults={"nb_edificio": "Edificio Norte", "direccion": "Norte de la ciudad"},
    )

    print("Asignando Usuarios a Edificios...")
    UsuarioEdificio.objects.get_or_create(id_usuario=u1, id_edificio=e1)
    UsuarioEdificio.objects.get_or_create(id_usuario=u2, id_edificio=e2)

    print("Creando Equipos de Monitoreo...")
    em1, _ = EquipoMonitoreo.objects.get_or_create(
        nb_equipo="Tablero Principal", id_edificio=e1
    )
    em2, _ = EquipoMonitoreo.objects.get_or_create(
        nb_equipo="Bomba de Agua", id_edificio=e2
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
        id_equipo_monitoreo=em1,
        id_dispos_sensor=ds1,
        defaults={
            "tipo_valor_capt": 35.5,
            "fecha_hora_lect": timezone.now(),
            "descripcion_falla": "Normal",
        },
    )
    es2, _ = EquipoSensor.objects.get_or_create(
        id_equipo_monitoreo=em1,
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
        id_status=s1, id_equipo_monitoreo=em1
    )
    sem2, _ = StatusEquipoMonitoreo.objects.get_or_create(
        id_status=s1, id_equipo_monitoreo=em2
    )

    print("Creando Acciones Preventivas...")
    AccionPrev.objects.get_or_create(
        id_equipo_monitoreo=em1,
        id_dispos_sensor=ds1,
        defaults={
            "parametro": "Temperatura",
            "valor_min": 10.0,
            "valor_max": 40.0,
            "accion_preventiva": "Revisar ventilacion",
            "id_status": s2,
        },
    )

    print("Creando Notificaciones...")
    Notificacion.objects.get_or_create(
        id_usuario=u1,
        id_equipo_monitoreo=em1,
        defaults={
            "fecha": timezone.now(),
            "mensaje": "El equipo ha sido registrado exitosamente.",
        },
    )

    print("Creando Historico de Fallas...")
    HistoricoFalla.objects.get_or_create(
        id_equipo_sensor=es1,
        id_status_equipo_monitoreo=sem1,
        defaults={"fecha": timezone.now()},
    )

    print("¡Población de base de datos completada exitosamente!")


if __name__ == "__main__":
    populate()
