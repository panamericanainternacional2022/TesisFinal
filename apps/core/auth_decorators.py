import functools

from django.shortcuts import redirect
from django.contrib import messages

ADMIN_ROLES = ("SA", "ADMIN")


def is_admin_role(rol: str) -> bool:
    return rol in ADMIN_ROLES


def login_required(view_func):
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_admin_role(request.session.get("usuario_rol")):
            messages.error(request, "No tiene permiso para acceder a esta sección.")
            return redirect("monitor")
        return view_func(request, *args, **kwargs)
    return wrapper
