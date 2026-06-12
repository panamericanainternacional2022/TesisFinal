from django.urls import path

from apps.users.views.auth import (
    login_view,
    logout_view,
    complete_registration_view,
)
from apps.users.views.admin import (
    user_register_view,
    beneficiary_list_view,
    beneficiary_create_view,
    beneficiary_update_view,
    beneficiary_delete_view,
    user_select_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("register/", user_register_view, name="user_register"),
    path("beneficiaries/", beneficiary_list_view, name="beneficiary_list"),
    path(
        "beneficiaries/create/",
        beneficiary_create_view,
        name="beneficiary_create",
    ),
    path(
        "beneficiaries/<int:beneficiario_id>/edit/",
        beneficiary_update_view,
        name="beneficiary_edit",
    ),
    path(
        "beneficiaries/<int:beneficiario_id>/delete/",
        beneficiary_delete_view,
        name="beneficiary_delete",
    ),
    path(
        "select/user/<str:accion>/",
        user_select_view,
        name="user_select",
    ),
    path("complete-registration/", complete_registration_view, name="complete_registration"),
]
