from django.urls import path
from .views import (
    notifications_view,
    toggle_alerts_session_view,
    clear_notifications_view,
    view_notification_count,
    view_clear_alerts,
    send_test_email,
    send_all_subscribers,
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
    path("api/notifications/count/", view_notification_count, name="api_notification_count"),
    path("api/clear-alerts/", view_clear_alerts, name="api_clear_alerts"),
    path("api/send-test-email/", send_test_email, name="api_send_test_email"),
    path(
        "api/send-all-subscribers/",
        send_all_subscribers,
        name="api_send_all_subscribers",
    ),
]
