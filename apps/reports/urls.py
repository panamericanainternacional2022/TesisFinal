from django.urls import path
from .views.history import history_pdf_view
from .views.users import user_pdf_view

urlpatterns = [
    path("historial/pdf/", history_pdf_view, name="history_pdf"),
    path("usuarios/pdf/", user_pdf_view, name="user_pdf"),
]
