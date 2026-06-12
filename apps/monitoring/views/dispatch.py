from django.http import HttpRequest, HttpResponse

from apps.core.auth_decorators import _is_admin_role
from .admin import (
    render_admin_monitoreo,
    render_admin_historial,
    monitoreo_edificio_view,
    simulador_status_view,
    simulador_start_view,
    simulador_stop_view,
    simulador_restart_view,
)
from .user import (
    render_user_monitoreo,
    render_user_historial,
    menu_seleccion_view,
)


def monitoreo_view(request: HttpRequest) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    if _is_admin_role(rol):
        return render_admin_monitoreo(request)
    return render_user_monitoreo(request)


def historial_view(request: HttpRequest) -> HttpResponse:
    rol = request.session.get("usuario_rol", "US")
    if _is_admin_role(rol):
        return render_admin_historial(request)
    return render_user_historial(request)
