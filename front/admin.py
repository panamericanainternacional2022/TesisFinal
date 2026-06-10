from django.contrib import admin
from front.models import (
    Edificio,
    EquipoMonitoreo,
    Notificacion,
    Persona,
    Usuario,
    UsuarioEdificio,
)

admin.site.register(
    [
        Edificio,
        EquipoMonitoreo,
        Notificacion,
        Persona,
        Usuario,
        UsuarioEdificio,
    ]
)
