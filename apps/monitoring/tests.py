from django.test import TestCase
from django.urls import reverse
from django.http import StreamingHttpResponse
from unittest.mock import patch, MagicMock
from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment
from apps.alerts.models import Notification
from apps.sensors.sensor_config import RISK_ALTO


class MenuSeleccionViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="User", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_menu_returns_200(self):
        response = self.client.get(reverse("menu"))
        self.assertEqual(response.status_code, 200)

    def test_redirects_to_login_if_not_authenticated(self):
        self.client.get(reverse("logout"))
        response = self.client.get(reverse("menu"))
        self.assertEqual(response.status_code, 302)


class HistorialViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="User", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.edificio = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir")
        self.equipo = MonitoringEquipment.objects.create(name="Bomba", building=self.edificio, equipment_type="bomba")
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_historial_empty(self):
        response = self.client.get(reverse("history"))
        self.assertEqual(response.status_code, 200)

    def test_historial_with_data(self):
        Notification.objects.create(
            user=self.usuario, monitoring_equipment=self.equipo,
            date="2026-01-01 12:00:00+00", message=f'{{"risk": "{RISK_ALTO}", "variable": "temperature", "value": 85, "action": "Revisar"}}',
        )
        response = self.client.get(reverse("history"))
        self.assertEqual(response.status_code, 200)


class MonitorViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="User", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_monitoreo_returns_200(self):
        response = self.client.get(reverse("monitor"))
        self.assertEqual(response.status_code, 200)

    @patch("apps.sensors.payload.build_live_payload_for_sim")
    @patch("apps.monitoring.simulation.api.get_simulator")
    def test_api_status_returns_json(self, mock_get_sim, mock_payload):
        mock_payload.return_value = {"status": "ok"}
        mock_sim = MagicMock()
        mock_sim.edificio_id = 1
        mock_get_sim.return_value = mock_sim
        response = self.client.get(reverse("api_status"), {"edificio_id": 1})
        self.assertEqual(response.status_code, 200)


class SseStreamTests(TestCase):
    @patch("apps.monitoring.simulation.streaming.get_simulator")
    def test_sse_returns_streaming_response(self, mock_get_sim):
        from apps.users.models import Persona, Usuario
        from django.contrib.auth.hashers import make_password
        p = Persona.objects.create(ci="99999999", first_name="SSE", first_last_name="Test", email="sse@test.com")
        Usuario.objects.create(username="ssetest", password=make_password("pass"), id_persona=p, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "ssetest", "password": "pass"})
        mock_sim = MagicMock()
        mock_sim.sensor_data = {}
        mock_sim.pending_notifications = []
        mock_sim.pump_on = False
        mock_sim.elevator_on = False
        mock_sim.protection_ends = {}
        mock_sim.active_alerts = {}
        mock_sim.alert_enabled = True
        mock_sim.edificio_id = 1
        mock_sim.history = []
        mock_get_sim.return_value = mock_sim
        response = self.client.get("/sse/1/")
        self.assertIsInstance(response, StreamingHttpResponse)
