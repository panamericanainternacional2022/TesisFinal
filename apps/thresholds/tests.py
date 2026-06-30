import json
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse

from apps.thresholds.models import ThresholdConfig
from apps.users.models import Persona, Usuario
from apps.buildings.models import Building


class ThresholdModelTests(TestCase):
    def setUp(self):
        self.building = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir", floors=10)

    def test_create_threshold_config(self):
        umbral = ThresholdConfig.objects.create(building=self.building, variable="temperature", direction="higher", low=20, medium=40, high=60)
        self.assertEqual(ThresholdConfig.objects.count(), 1)
        self.assertEqual(umbral.variable, "temperature")


class ThresholdApiViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="User", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True)
        self.building = Building.objects.create(name="Test", rif="J-11111111-0", address="Dir", floors=10)
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    @patch("apps.thresholds.views.get_thresholds")
    def test_get_thresholds(self, mock_get):
        mock_get.return_value = {"temperature": {"direction": "higher", "low": 20, "medium": 40, "high": 60}}
        response = self.client.get(reverse("api_thresholds"), {"edificio_id": self.building.pk})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("temperature", data)

    @patch("apps.thresholds.views.bulk_update")
    def test_update_thresholds(self, mock_bulk):
        mock_bulk.return_value = None
        payload = {"edificio_id": self.building.pk, "temperature": {"direction": "higher", "low": 30, "medium": 50, "high": 80}}
        response = self.client.post(reverse("api_thresholds_update"), json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
