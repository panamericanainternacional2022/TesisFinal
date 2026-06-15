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
                reverse("user_register"),
                reverse("user_list"),
                reverse("user_create"),
                reverse("building_list"),
                reverse("register_building"),
                reverse("user_edit", args=[0]).rstrip("0/"),
                reverse("user_delete", args=[0]).rstrip("0/"),
                reverse("edit_building", args=[0]).rstrip("0/"),
                reverse("delete_building", args=[0]).rstrip("0/"),
            ]
            self._admin_paths_cache = paths
            self._admin_paths_ts = now
        return self._admin_paths_cache

    def __call__(self, request):
        path = request.path_info
        login_url = reverse("login")

        public_paths = [login_url, "/static/", "/admin/", "/complete-registration/"]

        is_public = any(path.startswith(p) for p in public_paths if p)
        
        user_id = request.session.get("usuario_id")
        is_logged_in = False
        if user_id:
            from apps.users.models import Usuario
            if Usuario.objects.filter(id_usuario=user_id).exists():
                is_logged_in = True
            else:
                if hasattr(request.session, "flush"):
                    request.session.flush()
                else:
                    request.session.clear()

        if not is_public and not is_logged_in:
            return redirect(login_url)

        if is_logged_in and path == login_url:
            return redirect("monitor")

        if is_logged_in:
            rol = request.session.get("usuario_rol", "US")
            admin_paths = self._get_admin_paths()

            if any(path.startswith(p) for p in admin_paths if p):
                if rol not in ("SA", "ADMIN"):
                    return redirect("monitor")

        response = self.get_response(request)

        response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

        return response
