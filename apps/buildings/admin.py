from django.contrib import admin
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding

admin.site.register([Building, MonitoringEquipment, UserBuilding])
