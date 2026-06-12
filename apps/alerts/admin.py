from django.contrib import admin
from apps.alerts.models import Notification, ThresholdConfig

admin.site.register([Notification, ThresholdConfig])
