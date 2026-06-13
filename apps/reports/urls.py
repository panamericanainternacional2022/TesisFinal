from django.urls import path
from .views.history import history_pdf_view
from .views.beneficiaries import beneficiary_pdf_view

urlpatterns = [
    path("historial/pdf/", history_pdf_view, name="history_pdf"),
    path("beneficiarios/pdf/", beneficiary_pdf_view, name="beneficiary_pdf"),
]
