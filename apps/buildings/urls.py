from django.urls import path
from apps.buildings.views.building_views import (
    register_building_view,
    building_list_view,
    edit_building_view,
    delete_building_view,
    select_building_view,
    check_rif_uniqueness_view,
)
from apps.buildings.views.configuration_view import configuration_view

urlpatterns = [
    path("buildings/create/", register_building_view, name="register_building"),
    path("buildings/", building_list_view, name="building_list"),
    path(
        "buildings/<int:building_id>/edit/",
        edit_building_view,
        name="edit_building",
    ),
    path(
        "buildings/<int:building_id>/delete/",
        delete_building_view,
        name="delete_building",
    ),
    path(
        "buildings/select/<str:action>/",
        select_building_view,
        name="select_building",
    ),
    path("settings/", configuration_view, name="configuration"),
    path("api/check-rif/", check_rif_uniqueness_view, name="check_rif"),
]
