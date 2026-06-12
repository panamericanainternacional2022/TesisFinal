from django.urls import path
from django.views.generic import RedirectView

from .views.dispatch import monitoreo_view, historial_view
from .views.user import menu_seleccion_view
from .views.admin import (
    monitoreo_edificio_view,
    simulador_status_view,
    simulador_start_view,
    simulador_stop_view,
    simulador_restart_view,
)
from .simulation.streaming import sse_stream
from .simulation.api import api_status, api_buildings, api_building_users, api_notifications
from .simulation.controls import (
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
    path("menu/", menu_seleccion_view, name="menu"),
    path("history/", historial_view, name="history"),
    path("monitor/", monitoreo_view, name="monitor"),
    path(
        "monitor/building/<int:building_id>/",
        monitoreo_edificio_view,
        name="monitor_building",
    ),
    path(
        "monitor/simulator/status/",
        simulador_status_view,
        name="simulator_status",
    ),
    path(
        "monitor/simulator/start/",
        simulador_start_view,
        name="simulator_start",
    ),
    path(
        "monitor/simulator/stop/",
        simulador_stop_view,
        name="simulator_stop",
    ),
    path(
        "monitor/simulator/restart/",
        simulador_restart_view,
        name="simulator_restart",
    ),
    # ─── SIMULACIÓN API (reemplaza routes.py Flask) ─────
    path("sse/<int:building_id>/", sse_stream, name="sse_stream"),
    path("api/status/", api_status, name="api_status"),
    path("api/edificios/", api_buildings, name="api_edificios"),
    path(
        "api/usuarios_edificio/<int:building_id>/",
        api_building_users,
        name="api_usuarios_edificio",
    ),
    path("api/notifications/", api_notifications, name="api_notifications"),
    path("api/manual-update/", manual_update, name="manual_update"),
    path(
        "api/sim/<int:building_id>/status/",
        sim_status,
        name="sim_status_api",
    ),
    path(
        "api/sim/<int:building_id>/pause/",
        sim_pause,
        name="sim_pause_api",
    ),
    path(
        "api/sim/<int:building_id>/reset/",
        sim_reset,
        name="sim_reset_api",
    ),
    path(
        "api/sim/<int:building_id>/inject-fault/",
        sim_inject_fault,
        name="sim_inject_fault_api",
    ),
    path(
        "api/sim/<int:building_id>/clear-fault/",
        sim_clear_fault,
        name="sim_clear_fault_api",
    ),
    path(
        "api/sim/<int:building_id>/set-speed/",
        sim_set_speed,
        name="sim_set_speed_api",
    ),
    path(
        "api/sim/<int:building_id>/toggle-pump/",
        sim_toggle_pump,
        name="sim_toggle_pump_api",
    ),
    path(
        "api/sim/<int:building_id>/toggle-elevator/",
        sim_toggle_elevator,
        name="sim_toggle_elevator_api",
    ),
]
