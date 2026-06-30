from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.authentication.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.buildings.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.limits.urls")),
    path("", include("apps.thresholds.urls")),
    path("", include("apps.settings.urls")),
    path("", include("apps.reports.urls")),
]
