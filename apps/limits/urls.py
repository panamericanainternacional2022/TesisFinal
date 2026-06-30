from django.urls import path

from .views import (
    render_admin_limits,
    view_get_sensor_limits,
    view_update_sensor_limits,
)

urlpatterns = [
    path("limits/", render_admin_limits, name="sensor_limits"),
    path("api/sensor-limits/", view_get_sensor_limits, name="api_sensor_limits"),
    path("api/sensor-limits/update/", view_update_sensor_limits, name="api_sensor_limits_update"),
]
