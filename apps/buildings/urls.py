from django.urls import path
from apps.buildings.views.building_views import (
    register_building_view,
    building_list_view,
    edit_building_view,
    delete_building_view,
    select_building_view,
)
from apps.buildings.views.configuration_view import configuration_view

urlpatterns = [
    path("registro_edificio/", register_building_view, name="register_building"),
    path("lista_edificios/", building_list_view, name="building_list"),
    path(
        "editar_edificio/<int:building_id>/",
        edit_building_view,
        name="edit_building",
    ),
    path(
        "eliminar_edificio/<int:building_id>/",
        delete_building_view,
        name="delete_building",
    ),
    path(
        "seleccionar/edificio/<str:action>/",
        select_building_view,
        name="select_building",
    ),
    path("configuracion/", configuration_view, name="configuration"),
]
