from django.contrib import admin
from apps.buildings.models import Edificio, EquipoMonitoreo, UsuarioEdificio

admin.site.register([Edificio, EquipoMonitoreo, UsuarioEdificio])
