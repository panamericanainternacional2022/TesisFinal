from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.http import StreamingHttpResponse
from unittest.mock import patch, MagicMock
from apps.monitoring.views import menu_seleccion_view, historial_view, monitoreo_view
from apps.monitoring.simulation_views import sse_stream, api_status
from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.alerts.models import Notificacion


class MenuSeleccionViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", last_name="User", email="a@a.com", phone="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_menu_returns_200(self):
        response = self.client.get(reverse("menu_seleccion"))
        self.assertEqual(response.status_code, 200)

    def test_redirects_to_login_if_not_authenticated(self):
        self.client.get(reverse("logout"))
        response = self.client.get(reverse("menu_seleccion"))
        self.assertEqual(response.status_code, 302)


class HistorialViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", last_name="User", email="a@a.com", phone="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.edificio = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir")
        self.equipo = MonitoringEquipment.objects.create(name="Bomba", building=self.edificio, equipment_type="bomba")
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_historial_empty(self):
        response = self.client.get(reverse("historial"))
        self.assertEqual(response.status_code, 200)

    def test_historial_with_data(self):
        Notificacion.objects.create(
            id_usuario=self.usuario, id_equipo_monitoreo=self.equipo,
            fecha="2026-01-01 12:00:00+00", mensaje='{"risk": "Alto", "variable": "temperature", "value": 85, "action": "Revisar"}',
        )
        response = self.client.get(reverse("historial"))
        self.assertEqual(response.status_code, 200)


class MonitorViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", last_name="User", email="a@a.com", phone="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_monitoreo_returns_200(self):
        response = self.client.get(reverse("monitoreo"))
        self.assertEqual(response.status_code, 200)

    @patch("apps.monitoring.simulation_views.build_live_payload_for_sim")
    @patch("apps.monitoring.simulation_views.simulators")
    def test_api_status_returns_json(self, mock_simulators, mock_payload):
        mock_payload.return_value = {"status": "ok"}
        mock_sim = MagicMock()
        mock_sim.edificio_id = 1
        mock_simulators.items.return_value = [(1, mock_sim)]
        mock_simulators.get.return_value = mock_sim
        response = self.client.get(reverse("api_status"))
        self.assertEqual(response.status_code, 200)


class SseStreamTests(TestCase):
    @patch("apps.monitoring.simulation_views.simulators")
    def test_sse_returns_streaming_response(self, mock_simulators):
        from apps.users.models import Persona, Usuario
        from django.contrib.auth.hashers import make_password
        p = Persona.objects.create(ci="99999999", name="SSE", last_name="Test", email="sse@test.com", phone="")
        u = Usuario.objects.create(username="ssetest", password=make_password("pass"), id_persona=p, rol="SA", registered=True)
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
        mock_simulators.get.return_value = mock_sim
        response = self.client.get(f"/sse/1/")
        self.assertIsInstance(response, StreamingHttpResponse)
