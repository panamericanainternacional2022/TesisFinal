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
from apps.alerts.models import Notification
from apps.sensors.sensor_config import RISK_CRITICO


class SimulatorPhysicsAndAlertsTests(TestCase):
    def setUp(self):
        # 1. Crear datos de prueba (Persona, Usuario, Edificio, Equipo)
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
        
        # Asignar usuario al edificio para que reciba correos
        UserBuilding.objects.create(user=self.usuario, building=self.building)

        # 2. Inicializar el simulador para el edificio
        self.sim = BuildingSimulator(
            edificio_id=self.building.id,
            nombre=self.building.name,
            equipment_types={"bomba", "elevador"},
            floors=self.building.floors
        )

    def test_manual_override_lock_duration(self):
        """Verifica que si se realiza un cambio manual, este queda bloqueado por 90s."""
        self.sim.sensor_data["voltage"] = 150.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        
        # Ejecutar tick de física
        _update_pump(self.sim)
        
        # El voltaje debe persistir en 150.0 en lugar de regresar a 220V
        self.assertEqual(self.sim.sensor_data["voltage"], 150.0)

    def test_voltage_outage_dependency(self):
        """Si el voltaje cae a 0 (corte), los demás sensores decaen a 0."""
        self.sim.sensor_data["voltage"] = 0.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        
        # Ejecutar varios ticks
        for _ in range(5):
            _update_pump(self.sim)
            
        self.assertEqual(self.sim.sensor_data["flow_rate"], 0.0)
        self.assertEqual(self.sim.sensor_data["pressure"], 0.0)
        self.assertEqual(self.sim.sensor_data["vibration"], 0.0)
        self.assertEqual(self.sim.sensor_data["current"], 0.0)

    def test_tank_level_low_dependency(self):
        """Si el nivel de tanque baja a 5%, el caudal/presión caen y temp/vib suben."""
        self.sim.sensor_data["tank_level"] = 5.0
        self.sim.manual_overrides["tank_level"] = time.time() + 90.0
        
        _update_pump(self.sim)
        
        # Caudal y presión deben bajar debido a sequía/marcha en seco
        self.assertLessEqual(self.sim.sensor_data["flow_rate"], 2.0)
        self.assertLessEqual(self.sim.sensor_data["pressure"], 1.0)
        
        # Vibración y temperatura suben por cavitación/marcha en seco
        self.assertGreaterEqual(self.sim.sensor_data["vibration"], 1.0)
        self.assertGreaterEqual(self.sim.sensor_data["temperature"], 50.0)

    def test_centrifugal_pump_curve(self):
        """La presión debe derivarse de la curva centrífuga PUMP_P0 - PUMP_K * flow^2."""
        # Forzar un caudal específico
        self.sim.sensor_data["flow_rate"] = 10.0
        self.sim.manual_overrides["flow_rate"] = time.time() + 90.0
        
        _update_pump(self.sim)
        
        # PUMP_P0=7.0, PUMP_K=0.012. Con caudal 10: 7.0 - 0.012*(10^2) = 5.8 bar nominales (+/- ruido)
        pressure = self.sim.sensor_data["pressure"]
        self.assertAlmostEqual(pressure, 5.8, delta=0.5)

    def test_gradual_manual_transition(self):
        """Verifica que la transición de un cambio manual ocurra gradualmente en varios ticks."""
        from apps.sensors.simulation.simulation_engine import update_sensor_data
        
        # Iniciar voltaje en 220.0
        self.sim.sensor_data["voltage"] = 220.0
        # Establecer target manual a 185.0 V (mínimo es 180V)
        self.sim.manual_targets["voltage"] = 185.0
        self.sim.manual_overrides["voltage"] = time.time() + 90.0
        
        # Ejecutar 1 tick de simulación (velocidad de cambio es 15V por segundo)
        update_sensor_data(self.sim)
        
        # Debe haber bajado 15V (a 205.0V)
        self.assertEqual(self.sim.sensor_data["voltage"], 205.0)
        
        # Siguiente tick
        update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 190.0)
        
        # Siguiente tick (baja otros 5V para llegar al target 185V)
        update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 185.0)
        
        # Ejecutar más ticks y verificar que se mantiene en 185V
        for _ in range(3):
            update_sensor_data(self.sim)
        self.assertEqual(self.sim.sensor_data["voltage"], 185.0)

    def test_elevator_overload_behavior(self):
        """Si la carga del elevador supera 900kg, se abren puertas, speed=0."""
        self.sim._elev_state = "DOOR_CLOSING"
        self.sim._elev_timer = 0.5
        self.sim.sensor_data["load"] = 1000
        self.sim.manual_overrides["load"] = time.time() + 90.0
        
        _update_elevator(self.sim)
        
        # Debe rebotar el cierre e ir a DOOR_OPENING con puertas abiertas
        self.assertEqual(self.sim._elev_state, "DOOR_OPENING")
        self.assertEqual(self.sim.sensor_data["door_status"], "open")
        self.assertEqual(self.sim.sensor_data["speed"], 0.0)

    def test_door_status_alert_logic(self):
        """Las puertas abiertas en un piso no alertan, pero alertan si se mueve o atasca."""
        self.sim._elev_state = "DOORS_OPEN"
        self.sim.sensor_data["door_status"] = "open"
        self.sim.sensor_data["speed"] = 0.0
        self.sim.door_close_attempts = 0
        
        # 1. Puerta abierta en parada normal -> Sin alerta
        _handle_enum_alert(self.sim, "door_status", "open")
        self.assertNotIn("door_status", self.sim.active_alerts)
        
        # 2. Puerta abierta en movimiento -> Alerta crítica
        self.sim.sensor_data["speed"] = 1.0
        _handle_enum_alert(self.sim, "door_status", "open")
        self.assertIn("door_status", self.sim.active_alerts)
        self.assertEqual(self.sim.active_alerts["door_status"], RISK_CRITICO)
        
        # 3. Puerta atascada (intentos de cierre >= 2) -> Alerta crítica
        self.sim.sensor_data["speed"] = 0.0
        self.sim.door_close_attempts = 2
        _handle_enum_alert(self.sim, "door_status", "open")
        self.assertIn("door_status", self.sim.active_alerts)

    @patch("apps.alerts.alerts.engine.threading.Thread")
    def test_email_cooldown_per_variable(self, mock_thread):
        """Verifica que el cooldown de correos funcione de forma independiente por variable."""
        # Configurar un destinatario mockeado para evitar emails reales
        with patch("apps.alerts.services.alert_service.get_building_emails") as mock_emails:
            mock_emails.return_value = ["juanp@example.com"]
            
            # Limpiar estado del simulador
            self.sim.last_email_sent_time_per_var.clear()
            self.sim.active_alerts.clear()
            
            from apps.alerts.alerts.engine import send_alert
            
            # 1. Disparar primera alerta crítica (motor_stuck) -> Debe llamar a Thread para enviar email
            send_alert("motor_stuck", True, "Crítico", "Revisar motor", sim=self.sim)
            self.assertEqual(mock_thread.call_count, 1)
            
            # 2. Disparar segunda alerta de otra variable (door_status) -> Debe enviar también (cooldown independiente)
            send_alert("door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
            # Debió haber llamado de nuevo, sumando 2 llamadas en total
            self.assertEqual(mock_thread.call_count, 2)
            
            # 3. Disparar misma alerta otra vez inmediatamente -> Omitida por cooldown
            self.sim.active_alerts.pop("door_status", None)  # Forzar re-emisión
            send_alert("door_status", "open", "Crítico", "Puerta abierta", sim=self.sim)
            # El conteo se debe mantener en 2 (no incrementa)
            self.assertEqual(mock_thread.call_count, 2)

    def test_dynamic_equipment_status(self):
        """Verifica que el estado de los equipos cambie dinámicamente y se sincronice con la DB."""
        from apps.sensors.services.payload_service import _fetch_equipment_status
        from apps.buildings.models import MonitoringEquipment
        
        # Estado inicial en DB: operativo
        self.equipment_pump.status = "operativo"
        self.equipment_pump.save()
        
        # 1. Sin fallas ni alertas -> Debe retornar "operativo"
        pump_s, elev_s = _fetch_equipment_status(
            django_connected=True,
            active_edificio_id=self.building.id,
            sim_faults={},
            active_alerts={},
            protection_ends={}
        )
        self.assertEqual(pump_s, "operativo")
        
        # 2. Con falla inyectada en la bomba -> Debe retornar "falla" y actualizar DB
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
        
        # 3. Con protección activa -> Debe retornar "mantenimiento"
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
