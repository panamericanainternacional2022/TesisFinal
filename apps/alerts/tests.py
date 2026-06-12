import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.alerts.models import Notificacion, UmbralConfig
from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding


# ─── MODEL TESTS ─────────────────────────────────────────────────────

class NotificacionModelTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Test", last_name="User", email="t@t.com", phone="04121234567")
        self.usuario = Usuario.objects.create(username="testuser", password="abc", id_persona=self.persona, rol="US")
        self.building = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir")
        self.equipment = MonitoringEquipment.objects.create(name="Bomba", building=self.building, equipment_type="bomba")

    def test_create_notificacion(self):
        notif = Notificacion.objects.create(
            id_usuario=self.usuario,
            id_equipo_monitoreo=self.equipment,
            fecha=timezone.now(),
            mensaje='{"risk": "Alto", "variable": "temperature", "value": 85, "action": "Revisar"}',
        )
        self.assertEqual(Notificacion.objects.count(), 1)
        self.assertEqual(notif.mensaje, notif.mensaje)

    def test_create_umbral_config(self):
        umbral = UmbralConfig.objects.create(variable="temperature", direction="higher", low=20, medium=40, high=60)
        self.assertEqual(UmbralConfig.objects.count(), 1)
        self.assertEqual(umbral.variable, "temperature")


# ─── VIEW TESTS (notificaciones) ────────────────────────────────────

class NotificacionesViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", last_name="User", email="a@a.com", phone="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.building = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir")
        self.equipment = MonitoringEquipment.objects.create(name="Bomba", building=self.building, equipment_type="bomba")
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_get_notificaciones_empty(self):
        response = self.client.get(reverse("notificaciones"))
        self.assertEqual(response.status_code, 200)

    def test_get_notificaciones_with_data(self):
        Notificacion.objects.create(
            id_usuario=self.usuario, id_equipo_monitoreo=self.equipment,
            fecha=timezone.now(), mensaje='{"risk": "Alto", "variable": "temperature", "value": 85, "action": "Revisar"}',
        )
        response = self.client.get(reverse("notificaciones"))
        self.assertEqual(response.status_code, 200)

    def test_limpiar_notificaciones(self):
        response = self.client.post(reverse("limpiar_notificaciones"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")


# ─── API VIEW TESTS ─────────────────────────────────────────────────

class AlertApiViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", last_name="User", email="a@a.com", phone="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    @patch("apps.alerts.api_views.get_thresholds")
    def test_get_thresholds(self, mock_get):
        mock_get.return_value = {"temperature": {"direction": "higher", "low": 20, "medium": 40, "high": 60}}
        response = self.client.get(reverse("api_thresholds"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("temperature", data)

    @patch("apps.alerts.api_views.update_threshold")
    def test_update_thresholds(self, mock_update):
        mock_update.return_value = None
        response = self.client.post(reverse("api_thresholds_update"), json.dumps({"variable": "temperature", "risk": "low", "value": 10}), content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_toggle_alerts_session_disabled(self):
        response = self.client.post(reverse("toggle_alerts_session"), json.dumps({"enabled": False, "duration_minutes": 60}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["alerts_disabled"])

    def test_toggle_alerts_session_enabled(self):
        self.client.post(reverse("toggle_alerts_session"), json.dumps({"enabled": False, "duration_minutes": 60}), content_type="application/json")
        response = self.client.post(reverse("toggle_alerts_session"), json.dumps({"enabled": True}), content_type="application/json")
        data = json.loads(response.content)
        self.assertFalse(data["alerts_disabled"])
