from django.contrib import admin
from front.models import (
    AccionPrev,
    DisposSensor,
    Edificio,
    EquipoMonitoreo,
    EquipoSensor,
    HistoricoFalla,
    Notificacion,
    Persona,
    Status,
    StatusEquipoMonitoreo,
    Usuario,
    UsuarioEdificio,
)

admin.site.register(
    [
        AccionPrev,
        DisposSensor,
        Edificio,
        EquipoMonitoreo,
        EquipoSensor,
        HistoricoFalla,
        Notificacion,
        Persona,
        Status,
        StatusEquipoMonitoreo,
        Usuario,
        UsuarioEdificio,
    ]
)
