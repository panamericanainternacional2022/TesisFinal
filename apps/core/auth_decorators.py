import functools
from collections.abc import Callable
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

ADMIN_ROLES = ("SA", "ADMIN")


def _login_required(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    @functools.wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.session.get("usuario_id"):
            return redirect("login")
        return view_func(request, *args, **kwargs)
    return wrapper


def _admin_required(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    @functools.wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not _is_admin_role(request.session.get("usuario_rol")):
            messages.error(request, "No tienes permiso para acceder a esta sección.")
            return redirect("menu_seleccion")
        return view_func(request, *args, **kwargs)
    return wrapper


def _is_admin_role(role: str) -> bool:
    return role in ADMIN_ROLES
