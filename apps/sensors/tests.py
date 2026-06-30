import time
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.users.models import Persona, Usuario
from apps.buildings.models import Building, MonitoringEquipment, UserBuilding
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.physics.pump import _update_pump
from apps.sensors.simulation.physics.elevator import _update_elevator
from apps.sensors.engine import _run_sim_tick, _handle_enum_alert
from apps.events.models import Notification
from apps.sensors.sensor_config import RISK_CRITICO


class SimulatorPhysicsAndAlertsTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="99999999", first_name="Juan", first_last_name="Perez", email="juanp@example.com"
        )
        self.usuario = Usuario.objects.create(
            username="juanp", password="hashed_password", id_persona=self.persona, rol="US", registered=True
        )
        self.building = Building.objects.create(
            name="Conjunto Junin", rif="J-22222222-2", address="Calle Falsa 123", floors=15
        )
        self.equipment_pump = MonitoringEquipment.objects.create(
            name="Bomba Principal", building=self.building, equipment_type="bomba"
        )
        self.equipment_elev = MonitoringEquipment.objects.create(
            name="Elevador Principal", building=self.building, equipment_type="elevador"
        )
        
        UserBuilding.objects.create(user=self.usuario, building=self.building)

        self.sim = BuildingSimulator(
            edificio_id=self.building.id,
            nombre=self.building.name,
            equipment_types={"bomba", "elevador"},
            floors=self.building.floors
        )

    def test_manual_override_lock_duration(self):

        self.sim.sensor_data["voltage"] = 150.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        
        _update_pump(self.sim)
        
        self.assertEqual(self.sim.sensor_data["voltage"], 150.0)

    def test_voltage_outage_dependency(self):

        self.sim.sensor_data["voltage"] = 0.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        
        for _ in range(5):
            _update_pump(self.sim)
            
        self.assertEqual(self.sim.sensor_data["flow_rate"], 0.0)
        self.assertEqual(self.sim.sensor_data["pressure"], 0.0)
        self.assertEqual(self.sim.sensor_data["vibration"], 0.0)
        self.assertEqual(self.sim.sensor_data["current"], 0.0)

    def test_tank_level_low_dependency(self):

        self.sim.sensor_data["tank_level"] = 5.0
        self.sim.manual_overrides["tank_level"] = time.time() + 90.0
        
        _update_pump(self.sim)
        
        self.assertLessEqual(self.sim.sensor_data["flow_rate"], 2.0)
        self.assertLessEqual(self.sim.sensor_data["pressure"], 1.0)
        
        self.assertGreaterEqual(self.sim.sensor_data["vibration"], 1.0)
        self.assertGreaterEqual(self.sim.sensor_data["temperature"], 50.0)

    def test_centrifugal_pump_curve(self):

        self.sim.sensor_data["flow_rate"] = 10.0
        self.sim.manual_overrides["flow_rate"] = time.time() + 90.0
        
        _update_pump(self.sim)
        
        pressure = self.sim.sensor_data["pressure"]
        self.assertAlmostEqual(pressure, 5.8, delta=0.5)

    def test_gradual_manual_transition(self):

        from apps.sensors.simulation.simulation_engine import update_sensor_data
        
        self.sim.sensor_data["voltage"] = 220.0
        self.sim.manual_targets["voltage"] = 185.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        
        update_sensor_data(self.sim)
        
        self.assertEqual(self.sim.sensor_data["voltage"], 205.0)
        
        update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 190.0)
        
        update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 185.0)
        
        for _ in range(3):
            update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 185.0)

    def test_elevator_overload_behavior(self):

        self.sim._elev_state = "DOOR_CLOSING"
        self.sim._elev_timer = 0.5
        self.sim.sensor_data["load"] = 1000
        self.sim.manual_overrides["load"] = time.time() + 90.0
        
        _update_elevator(self.sim)
        
        self.assertEqual(self.sim._elev_state, "DOOR_OPENING")
        self.assertEqual(self.sim.sensor_data["door_status"], "open")
        self.assertEqual(self.sim.sensor_data["speed"], 0.0)

    def test_door_status_alert_logic(self):

        self.sim._elev_state = "DOORS_OPEN"
        self.sim.sensor_data["door_status"] = "open"
        self.sim.sensor_data["speed"] = 0.0
        self.sim.door_close_attempts = 0
        
        _handle_enum_alert(self.sim, "door_status", "open")
        self.assertNotIn("door_status", self.sim.active_alerts)
        
        self.sim.sensor_data["speed"] = 1.0
        _handle_enum_alert(self.sim, "door_status", "open")
        self.assertIn("door_status", self.sim.active_alerts)
        self.assertEqual(self.sim.active_alerts["door_status"], RISK_CRITICO)
        
        self.sim.sensor_data["speed"] = 0.0
        self.sim.door_close_attempts = 2
        _handle_enum_alert(self.sim, "door_status", "open")
        self.assertIn("door_status", self.sim.active_alerts)

    @patch("apps.events.alerts.engine.threading.Thread")
    def test_email_cooldown_per_variable(self, mock_thread):

        with patch("apps.events.services.alert_service.get_building_emails") as mock_emails:
            mock_emails.return_value = ["juanp@example.com"]
            
            self.sim.last_email_sent_time_per_var.clear()
            self.sim.active_alerts.clear()
            
            from apps.events.alerts.engine import send_alert
            
            send_alert("motor_stuck", True, "Crítico", "Revisar motor", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 1)
            
            send_alert("door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 2)
            
            self.sim.active_alerts.pop("door_status", None)
            send_alert("door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 2)

    def test_dynamic_equipment_status(self):

        from apps.sensors.services.payload_service import _fetch_equipment_status
        from apps.buildings.models import MonitoringEquipment
        
        self.equipment_pump.status = "operativo"
        self.equipment_pump.save()
        
        pump_s, elev_s = _fetch_equipment_status(
            django_connected=True,
            active_edificio_id=self.building.id,
            sim_faults={},
            active_alerts={},
            protection_ends={}
        )
        self.assertEqual(pump_s, "operativo")
        
        pump_s, elev_s = _fetch_equipment_status(
            django_connected=True,
            active_edificio_id=self.building.id,
            sim_faults={"pump": "dry_run"},
            active_alerts={},
            protection_ends={}
        )
        self.assertEqual(pump_s, "falla")
        self.equipment_pump.refresh_from_db()
        self.assertEqual(self.equipment_pump.status, "falla")
        
        pump_s, elev_s = _fetch_equipment_status(
            django_connected=True,
            active_edificio_id=self.building.id,
            sim_faults={},
            active_alerts={},
            protection_ends={"pump": time.time() + 30}
        )
        self.assertEqual(pump_s, "mantenimiento")
        self.equipment_pump.refresh_from_db()
        self.assertEqual(self.equipment_pump.status, "mantenimiento")
