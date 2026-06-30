from django.urls import path

from .views import (
    register_building_view,
    building_list_view,
    edit_building_view,
    delete_building_view,
    check_rif_uniqueness_view,
)

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
    path("api/check-rif/", check_rif_uniqueness_view, name="check_rif"),
]
