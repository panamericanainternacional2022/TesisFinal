from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from apps.users.models import Persona, Usuario


class ReportViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", last_name="User", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_history_pdf_requires_login(self):
        self.client.get(reverse("logout"))
        response = self.client.get(reverse("history_pdf"))
        self.assertEqual(response.status_code, 302)

    @patch("fpdf.FPDF")
    def test_history_pdf_returns_pdf(self, mock_fpdf_class):
        mock_pdf_instance = MagicMock()
        mock_pdf_instance.page_no.return_value = 1
        mock_pdf_instance.output.return_value = b"%PDF-1.4 mock"
        mock_fpdf_class.return_value = mock_pdf_instance
        response = self.client.get(reverse("history_pdf"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

class ReportViewNonAdminTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="User", last_name="Test", email="u@u.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="normal", password=make_password("pass123"), id_persona=self.persona, rol="US", registered=True)
        self.client.post(reverse("login"), {"username": "normal", "password": "pass123"})

    def test_history_pdf_non_admin_access(self):
        response = self.client.get(reverse("history_pdf"))
        self.assertEqual(response.status_code, 200)
