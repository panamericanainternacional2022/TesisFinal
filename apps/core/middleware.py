from functools import lru_cache
import time

from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings


class AuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._admin_paths_cache = None
        self._admin_paths_ts = 0
        self._admin_paths_ttl = 5 if settings.DEBUG else 300

    def _get_admin_paths(self):
        now = time.time()
        if self._admin_paths_cache is None or now - self._admin_paths_ts > self._admin_paths_ttl:
            paths = [
                reverse("usuario"),
                reverse("lista_usuario"),
                reverse("registro_beneficiario"),
                reverse("lista_edificios"),
                reverse("registro_edificio"),
                reverse("editar_beneficiario", args=[0]).rstrip("0/"),
                reverse("eliminar_beneficiario", args=[0]).rstrip("0/"),
                reverse("editar_edificio", args=[0]).rstrip("0/"),
                reverse("eliminar_edificio", args=[0]).rstrip("0/"),
            ]
            self._admin_paths_cache = paths
            self._admin_paths_ts = now
        return self._admin_paths_cache

    def __call__(self, request):
        path = request.path_info
        login_url = reverse("login")

        public_paths = [login_url, "/static/", "/admin/", "/completar_registro/"]

        is_public = any(path.startswith(p) for p in public_paths if p)
        is_logged_in = request.session.get("usuario_id") is not None

        if not is_public and not is_logged_in:
            return redirect(login_url)

        if is_logged_in and path == login_url:
            return redirect("menu_seleccion")

        if is_logged_in:
            rol = request.session.get("usuario_rol", "US")
            admin_paths = self._get_admin_paths()

            if any(path.startswith(p) for p in admin_paths if p):
                if rol not in ("SA", "ADMIN"):
                    return redirect("menu_seleccion")

        response = self.get_response(request)

        response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

        return response
