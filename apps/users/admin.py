from django.contrib import admin
from apps.users.models import Persona, Usuario

admin.site.register([Persona, Usuario])
