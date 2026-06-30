from django.urls import path

from .views import (
    user_register_view,
    user_list_view,
    user_create_view,
    user_update_view,
    user_delete_view,
    check_cedula_uniqueness_view,
)

urlpatterns = [
    path("register/", user_register_view, name="user_register"),
    path("users/", user_list_view, name="user_list"),
    path(
        "users/create/",
        user_create_view,
        name="user_create",
    ),
    path(
        "users/<int:user_id>/edit/",
        user_update_view,
        name="user_edit",
    ),
    path(
        "users/<int:user_id>/delete/",
        user_delete_view,
        name="user_delete",
    ),
    path("api/check-cedula/", check_cedula_uniqueness_view, name="check_cedula"),
]
