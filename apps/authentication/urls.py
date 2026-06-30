from django.urls import path

from .views import (
    login_view,
    logout_view,
    complete_registration_view,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("complete-registration/", complete_registration_view, name="complete_registration"),
]
