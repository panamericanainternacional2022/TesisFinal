from django.urls import path

from .views import configuration_view

urlpatterns = [
    path("settings/", configuration_view, name="configuration"),
]
