from unittest.mock import Mock
from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from django.urls import reverse
from apps.core.auth_decorators import is_admin_role, login_required, ADMIN_ROLES
from apps.core.services.risk_service import classify_risk


class IsAdminRoleTests(TestCase):
    def test_admin_roles_return_true(self):
        for rol in ADMIN_ROLES:
            self.assertTrue(is_admin_role(rol))

    def test_non_admin_roles_return_false(self):
        for rol in ("US", "OP", None, ""):
            self.assertFalse(is_admin_role(rol))


class LoginRequiredDecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.mock_view = Mock(return_value=HttpResponse("ok"))
        self.wrapped = login_required(self.mock_view)

    def test_redirects_when_not_logged_in(self):
        request = self.factory.get("/")
        request.session = {}
        response = self.wrapped(request)
        self.assertEqual(response.status_code, 302)
        self.mock_view.assert_not_called()

    def test_calls_view_when_logged_in(self):
        request = self.factory.get("/")
        request.session = {"usuario_id": 1}
        response = self.wrapped(request)
        self.assertEqual(response.status_code, 200)
        self.mock_view.assert_called_once()


class AdminRequiredDecoratorTests(TestCase):
    def test_redirects_when_not_admin(self):
        response = self.client.get(reverse("beneficiary_list"))
        self.assertEqual(response.status_code, 302)

    def test_calls_view_when_admin(self):
        from apps.users.models import Persona
        p = Persona.objects.create(ci="12345678", name="Admin", last_name="U", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        from apps.users.models import Usuario
        Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=p, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})
        response = self.client.get(reverse("beneficiary_list"))
        self.assertEqual(response.status_code, 200)


class ClassifyRiskTests(TestCase):
    def test_motor_stuck_true_returns_critico(self):
        risk, color = classify_risk("motor_stuck", True)
        self.assertEqual(risk, "Crítico")
        self.assertEqual(color, "red")

    def test_motor_stuck_false_returns_bajo(self):
        risk, color = classify_risk("motor_stuck", False)
        self.assertEqual(risk, "Bajo")
        self.assertEqual(color, "green")

    def test_no_risk_vars_return_bajo(self):
        for var in ("position", "door_status"):
            risk, color = classify_risk(var, 42)
            self.assertEqual(risk, "Bajo")
            self.assertEqual(color, "green")

    def test_zero_flow_rate_returns_critico(self):
        risk, color = classify_risk("flow_rate", 0)
        self.assertEqual(risk, "Crítico")
        self.assertEqual(color, "red")

    def test_zero_pressure_returns_critico(self):
        risk, color = classify_risk("pressure", 0)
        self.assertEqual(risk, "Crítico")
        self.assertEqual(color, "red")

    def test_unknown_variable_returns_desconocido(self):
        risk, color = classify_risk("nonexistent_var", 50)
        self.assertEqual(risk, "Desconocido")
        self.assertEqual(color, "gray")

    def test_range_direction(self):
        thresholds = {
            "temperature": {"direction": "range", "low": 20, "high": 80},
        }
        risk, color = classify_risk("temperature", 50, thresholds=thresholds)
        self.assertEqual(risk, "Bajo")

    def test_range_direction_high(self):
        thresholds = {
            "temperature": {"direction": "range", "low": 20, "high": 80},
        }
        risk, color = classify_risk("temperature", 99, thresholds=thresholds)
        self.assertEqual(risk, "Alto")

    def test_higher_direction(self):
        thresholds = {
            "flow_rate": {"direction": "higher", "low": 10, "medium": 20, "high": 30},
        }
        test_cases = [
            (5, "Bajo", "green"),
            (15, "Medio", "yellow"),
            (25, "Alto", "orange"),
            (35, "Crítico", "red"),
        ]
        for value, expected_risk, expected_color in test_cases:
            risk, color = classify_risk("flow_rate", value, thresholds=thresholds)
            self.assertEqual(risk, expected_risk, f"flow_rate={value}")
            self.assertEqual(color, expected_color, f"flow_rate={value}")

    def test_lower_direction(self):
        thresholds = {
            "tank_level": {"direction": "lower", "low": 80, "medium": 60, "high": 40},
        }
        test_cases = [
            (90, "Bajo", "green"),
            (70, "Medio", "yellow"),
            (50, "Alto", "orange"),
            (30, "Crítico", "red"),
        ]
        for value, expected_risk, expected_color in test_cases:
            risk, color = classify_risk("tank_level", value, thresholds=thresholds)
            self.assertEqual(risk, expected_risk, f"tank_level={value}")
            self.assertEqual(color, expected_color, f"tank_level={value}")
