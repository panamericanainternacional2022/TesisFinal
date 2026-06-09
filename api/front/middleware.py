from django.shortcuts import redirect
from django.urls import reverse


class AuthMiddleware:
    _sessions_cleared = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        login_url = reverse("login")

        public_paths = [login_url, "/static/", "/admin/", "/completar_registro/"]

        is_public = any(path.startswith(p) for p in public_paths if p)
        is_logged_in = request.session.get("usuario_id") is not None
        if is_logged_in:
            from front.models import Usuario

            if not Usuario.objects.filter(
                id_usuario=request.session.get("usuario_id")
            ).exists():
                request.session.flush()
                is_logged_in = False

        if not is_public and not is_logged_in:
            return redirect(login_url)

        if is_logged_in and path == login_url:
            return redirect("menu_seleccion")

        if is_logged_in:
            rol = request.session.get("usuario_rol", "US")
            admin_paths = [
                reverse("usuario"),
                reverse("lista_usuario"),
                reverse("registro_beneficiario"),
                reverse("lista_edificios"),
                reverse("registro_edificio"),
                "/editar_beneficiario/",
                "/eliminar_beneficiario/",
                "/editar_edificio/",
                "/eliminar_edificio/",
            ]

            if any(path.startswith(p) for p in admin_paths if p):
                if rol not in ("SA", "ADMIN"):
                    return redirect("menu_seleccion")

        response = self.get_response(request)

        # Evita cualquier tipo de cache en el navegador y bfcache
        response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

        return response
