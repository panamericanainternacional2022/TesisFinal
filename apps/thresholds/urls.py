from django.urls import path

from .views import (
    render_admin_thresholds,
    view_get_thresholds,
    view_update_thresholds,
)

urlpatterns = [
    path("thresholds/", render_admin_thresholds, name="thresholds"),
    path("api/thresholds/", view_get_thresholds, name="api_thresholds"),
    path("api/thresholds/update/", view_update_thresholds, name="api_thresholds_update"),
]
