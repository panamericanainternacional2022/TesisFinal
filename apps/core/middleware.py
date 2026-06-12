import time
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


class AuthMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._admin_paths_cache: list[str] | None = None
        self._admin_paths_ts: float = 0
        self._admin_paths_ttl: int = 5 if settings.DEBUG else 300

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path_info
        login_url = reverse("login")

        if not self._is_authenticated(request, path, login_url):
            return redirect(login_url)
        if self._is_at_login_page(request, path, login_url):
            return redirect("menu_seleccion")
        admin_redirect = self._check_admin_access(request, path)
        if admin_redirect is not None:
            return admin_redirect

        response = self.get_response(request)
        self._set_no_cache_headers(response)
        return response

    def _is_authenticated(self, request: HttpRequest, path: str, login_url: str) -> bool:
        public_paths = [login_url, "/static/", "/admin/", "/completar_registro/"]
        is_public = any(path.startswith(p) for p in public_paths if p)
        is_logged_in = request.session.get("usuario_id") is not None
        return is_public or is_logged_in

    def _is_at_login_page(self, request: HttpRequest, path: str, login_url: str) -> bool:
        is_logged_in = request.session.get("usuario_id") is not None
        return is_logged_in and path == login_url

    def _check_admin_access(self, request: HttpRequest, path: str) -> HttpResponse | None:
        is_logged_in = request.session.get("usuario_id") is not None
        if not is_logged_in:
            return None
        rol = request.session.get("usuario_rol", "US")
        admin_paths = self._get_admin_paths()
        if any(path.startswith(p) for p in admin_paths if p):
            if rol not in ("SA", "ADMIN"):
                return redirect("menu_seleccion")
        return None

    def _set_no_cache_headers(self, response: HttpResponse) -> None:
        response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

    def _get_admin_paths(self) -> list[str]:
        now = time.time()
        if self._admin_paths_cache is None or now - self._admin_paths_ts > self._admin_paths_ttl:
            paths = [
                reverse("usuario"),
                reverse("lista_usuario"),
                reverse("registro_beneficiario"),
                reverse("building_list"),
                reverse("register_building"),
                reverse("editar_beneficiario", args=[0]).rstrip("0/"),
                reverse("eliminar_beneficiario", args=[0]).rstrip("0/"),
                reverse("edit_building", args=[0]).rstrip("0/"),
                reverse("delete_building", args=[0]).rstrip("0/"),
            ]
            self._admin_paths_cache = paths
            self._admin_paths_ts = now
        return self._admin_paths_cache
