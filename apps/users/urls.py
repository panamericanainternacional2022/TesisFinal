from django.urls import path

from apps.users.views.auth import (
    login_view,
    logout_view,
    complete_registration_view,
)
from apps.users.views.admin import (
    user_registration_view,
    beneficiary_list_view,
    beneficiary_create_view,
    beneficiary_update_view,
    beneficiary_delete_view,
    user_select_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("usuario/", user_registration_view, name="usuario"),
    path("lista_usuario/", beneficiary_list_view, name="lista_usuario"),
    path(
        "registro_beneficiario/",
        beneficiary_create_view,
        name="registro_beneficiario",
    ),
    path(
        "editar_beneficiario/<int:beneficiario_id>/",
        beneficiary_update_view,
        name="editar_beneficiario",
    ),
    path(
        "eliminar_beneficiario/<int:beneficiario_id>/",
        beneficiary_delete_view,
        name="eliminar_beneficiario",
    ),
    path(
        "seleccionar/usuario/<str:accion>/",
        user_select_view,
        name="seleccionar_usuario",
    ),
    path("completar_registro/", complete_registration_view, name="completar_registro"),
]
