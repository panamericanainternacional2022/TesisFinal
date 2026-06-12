from django.shortcuts import redirect
from django.contrib import messages

ADMIN_ROLES = ("SA", "ADMIN")


def _is_admin_role(rol):
    return rol in ADMIN_ROLES


def _login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.session.get("usuario_id"):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapper


def _admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not _is_admin_role(request.session.get("usuario_rol")):
            messages.error(request, "No tienes permiso para acceder a esta sección.")
            return redirect("menu_seleccion")
        return view_func(request, *args, **kwargs)
    return wrapper
