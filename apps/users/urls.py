from django.urls import path

from apps.users.views.auth import (
    login_view,
    logout_view,
    complete_registration_view,
)
from apps.users.views.admin import (
    user_register_view,
    user_list_view,
    user_create_view,
    user_update_view,
    user_delete_view,
    user_select_view,
    check_cedula_uniqueness_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
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
    path(
        "select/user/<str:action>/",
        user_select_view,
        name="user_select",
    ),
    path("complete-registration/", complete_registration_view, name="complete_registration"),
    path("api/check-cedula/", check_cedula_uniqueness_view, name="check_cedula"),
]
