from django.urls import path
from .views import (
    login_view,
    logout_view,
    usuario_view,
    lista_usuario_view,
    registro_beneficiario_view,
    editar_beneficiario_view,
    eliminar_beneficiario_view,
    seleccionar_usuario_view,
    completar_registro_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("usuario/", usuario_view, name="usuario"),
    path("lista_usuario/", lista_usuario_view, name="lista_usuario"),
    path(
        "registro_beneficiario/",
        registro_beneficiario_view,
        name="registro_beneficiario",
    ),
    path(
        "editar_beneficiario/<int:beneficiario_id>/",
        editar_beneficiario_view,
        name="editar_beneficiario",
    ),
    path(
        "eliminar_beneficiario/<int:beneficiario_id>/",
        eliminar_beneficiario_view,
        name="eliminar_beneficiario",
    ),
    path(
        "seleccionar/usuario/<str:accion>/",
        seleccionar_usuario_view,
        name="seleccionar_usuario",
    ),
    path("completar_registro/", completar_registro_view, name="completar_registro"),
]
