from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.monitoring.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.buildings.urls")),
    path("", include("apps.alerts.urls")),
    path("", include("apps.reports.urls")),
]
