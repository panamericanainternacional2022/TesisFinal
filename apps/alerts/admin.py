from django.contrib import admin
from apps.alerts.models import Notificacion, UmbralConfig

admin.site.register([Notificacion, UmbralConfig])
