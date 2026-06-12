from django.urls import path
from django.views.generic import RedirectView
from .views import (
    menu_seleccion_view,
    historial_view,
    monitoreo_view,
    monitoreo_edificio_view,
    simulador_status_view,
    simulador_start_view,
    simulador_stop_view,
    simulador_restart_view,
)
from .simulation_views import (
    sse_stream,
    api_status,
    api_edificios,
    api_usuarios_edificio,
    api_notifications,
    manual_update,
    sim_status,
    sim_pause,
    sim_reset,
    sim_inject_fault,
    sim_clear_fault,
    sim_set_speed,
    sim_toggle_pump,
    sim_toggle_elevator,
)

urlpatterns = [
    path("", RedirectView.as_view(url="/login/", permanent=False), name="home"),
    path("menu_seleccion/", menu_seleccion_view, name="menu_seleccion"),
    path("historial/", historial_view, name="historial"),
    path("monitoreo/", monitoreo_view, name="monitoreo"),
    path(
        "monitoreo/edificio/<int:edificio_id>/",
        monitoreo_edificio_view,
        name="monitoreo_edificio",
    ),
    path(
        "monitoreo/simulador/status/",
        simulador_status_view,
        name="simulador_status",
    ),
    path(
        "monitoreo/simulador/start/",
        simulador_start_view,
        name="simulador_start",
    ),
    path(
        "monitoreo/simulador/stop/",
        simulador_stop_view,
        name="simulador_stop",
    ),
    path(
        "monitoreo/simulador/restart/",
        simulador_restart_view,
        name="simulador_restart",
    ),
    # ─── SIMULACIÓN API (reemplaza routes.py Flask) ─────
    path("sse/<int:edificio_id>/", sse_stream, name="sse_stream"),
    path("api/status/", api_status, name="api_status"),
    path("api/edificios/", api_edificios, name="api_edificios"),
    path(
        "api/usuarios_edificio/<int:edificio_id>/",
        api_usuarios_edificio,
        name="api_usuarios_edificio",
    ),
    path("api/notifications/", api_notifications, name="api_notifications"),
    path("api/manual-update/", manual_update, name="manual_update"),
    path(
        "api/sim/<int:edificio_id>/status/",
        sim_status,
        name="sim_status_api",
    ),
    path(
        "api/sim/<int:edificio_id>/pause/",
        sim_pause,
        name="sim_pause_api",
    ),
    path(
        "api/sim/<int:edificio_id>/reset/",
        sim_reset,
        name="sim_reset_api",
    ),
    path(
        "api/sim/<int:edificio_id>/inject-fault/",
        sim_inject_fault,
        name="sim_inject_fault_api",
    ),
    path(
        "api/sim/<int:edificio_id>/clear-fault/",
        sim_clear_fault,
        name="sim_clear_fault_api",
    ),
    path(
        "api/sim/<int:edificio_id>/set-speed/",
        sim_set_speed,
        name="sim_set_speed_api",
    ),
    path(
        "api/sim/<int:edificio_id>/toggle-pump/",
        sim_toggle_pump,
        name="sim_toggle_pump_api",
    ),
    path(
        "api/sim/<int:edificio_id>/toggle-elevator/",
        sim_toggle_elevator,
        name="sim_toggle_elevator_api",
    ),
]
