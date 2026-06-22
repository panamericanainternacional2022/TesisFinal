from django.urls import path
from .views.notifications import notifications_view
from .views.alert_controls import toggle_alerts_session_view, toggle_email_alerts_view, clear_notifications_view
from .api_views import (
    view_get_thresholds,
    view_update_thresholds,
    view_get_sensor_limits,
    view_update_sensor_limits,
    view_clear_alerts,
    send_test_email,
    send_all_subscribers,
    view_notification_count,
)

urlpatterns = [
    path("notifications/", notifications_view, name="notifications"),
    path(
        "notifications/toggle-alerts/",
        toggle_alerts_session_view,
        name="toggle_alerts_session",
    ),
    path(
        "notifications/clear/",
        clear_notifications_view,
        name="clear_notifications",
    ),
    path(
        "notifications/toggle-email-alerts/",
        toggle_email_alerts_view,
        name="toggle_email_alerts",
    ),
    path("api/notifications/count/", view_notification_count, name="api_notification_count"),
    path("api/thresholds/", view_get_thresholds, name="api_thresholds"),
    path("api/thresholds/update/", view_update_thresholds, name="api_thresholds_update"),
    path("api/sensor-limits/", view_get_sensor_limits, name="api_sensor_limits"),
    path("api/sensor-limits/update/", view_update_sensor_limits, name="api_sensor_limits_update"),
    path("api/clear-alerts/", view_clear_alerts, name="api_clear_alerts"),
    path("api/send-test-email/", send_test_email, name="api_send_test_email"),
    path(
        "api/send-all-subscribers/",
        send_all_subscribers,
        name="api_send_all_subscribers",
    ),
]
