from django.urls import path
from .views import (
    registro_edificio_view,
    lista_edificios_view,
    editar_edificio_view,
    eliminar_edificio_view,
    seleccionar_edificio_view,
    configuracion_view,
)

urlpatterns = [
    path("registro_edificio/", registro_edificio_view, name="registro_edificio"),
    path("lista_edificios/", lista_edificios_view, name="lista_edificios"),
    path(
        "editar_edificio/<int:edificio_id>/",
        editar_edificio_view,
        name="editar_edificio",
    ),
    path(
        "eliminar_edificio/<int:edificio_id>/",
        eliminar_edificio_view,
        name="eliminar_edificio",
    ),
    path(
        "seleccionar/edificio/<str:accion>/",
        seleccionar_edificio_view,
        name="seleccionar_edificio",
    ),
    path("configuracion/", configuracion_view, name="configuracion"),
]
