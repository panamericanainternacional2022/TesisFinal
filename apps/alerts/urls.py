from django.urls import path
from .views import (
    notificaciones_view,
    toggle_alerts_session_view,
    limpiar_notificaciones_view,
)
from .api_views import (
    view_get_thresholds,
    view_update_thresholds,
    view_clear_alerts,
    view_toggle_alerts,
    send_test_email,
    send_all_subscribers,
)

urlpatterns = [
    path("notificaciones/", notificaciones_view, name="notificaciones"),
    path(
        "notificaciones/toggle_alerts/",
        toggle_alerts_session_view,
        name="toggle_alerts_session",
    ),
    path(
        "notificaciones/limpiar/",
        limpiar_notificaciones_view,
        name="limpiar_notificaciones",
    ),
    path("api/thresholds/", view_get_thresholds, name="api_thresholds"),
    path("api/thresholds/update/", view_update_thresholds, name="api_thresholds_update"),
    path("api/clear-alerts/", view_clear_alerts, name="api_clear_alerts"),
    path("api/toggle-alerts/", view_toggle_alerts, name="api_toggle_alerts"),
    path("api/send-test-email/", send_test_email, name="api_send_test_email"),
    path(
        "api/send-all-subscribers/",
        send_all_subscribers,
        name="api_send_all_subscribers",
    ),
]
