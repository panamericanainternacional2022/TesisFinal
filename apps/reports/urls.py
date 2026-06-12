from django.urls import path
from .views import historial_pdf_view, descargar_pdf_view

urlpatterns = [
    path("historial/pdf/", historial_pdf_view, name="historial_pdf"),
    path("descargar_pdf/", descargar_pdf_view, name="descargar_pdf"),
]
