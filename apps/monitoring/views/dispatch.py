from django.http import HttpRequest, HttpResponse

from .admin import (
    render_admin_monitoring,
    render_admin_history,
    render_admin_thresholds,
    render_admin_limits,
)
from .user import (
    render_user_monitoring,
    render_user_history,
)


def monitoring_view(request: HttpRequest) -> HttpResponse:
    from apps.core.auth_decorators import is_admin_role
    rol = request.session.get("usuario_rol", "US")
    if is_admin_role(rol):
        return render_admin_monitoring(request)
    return render_user_monitoring(request)


def history_view(request: HttpRequest) -> HttpResponse:
    from apps.core.auth_decorators import is_admin_role
    rol = request.session.get("usuario_rol", "US")
    if is_admin_role(rol):
        return render_admin_history(request)
    return render_user_history(request)


def thresholds_view(request: HttpRequest) -> HttpResponse:
    """Thresholds page is admin-only."""
    from apps.core.auth_decorators import is_admin_role
    rol = request.session.get("usuario_rol", "US")
    if not is_admin_role(rol):
        from django.shortcuts import redirect
        return redirect('monitor')
    return render_admin_thresholds(request)


def limits_view(request: HttpRequest) -> HttpResponse:
    """Sensor limits page is admin-only."""
    from apps.core.auth_decorators import is_admin_role
    rol = request.session.get("usuario_rol", "US")
    if not is_admin_role(rol):
        from django.shortcuts import redirect
        return redirect('monitor')
    return render_admin_limits(request)
