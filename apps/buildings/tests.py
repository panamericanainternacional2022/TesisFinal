from django.test import TestCase
from django.urls import reverse
from apps.buildings.validators import validate_unique_rif, validate_building_form
from apps.buildings.models import Building, MonitoringEquipment
from apps.users.models import Persona, Usuario


class ValidateBuildingFormTests(TestCase):
    def test_valid_data_returns_empty(self) -> None:
        data = {
            "nombreEdificio": "Edificio Principal",
            "direccion": "Av. Principal, Urb. Centro, calle 1",
            "rif": "J-12345678-0",
            "cantidadPisos": "10",
        }
        errores = validate_building_form(data)
        self.assertEqual(errores, {})

    def test_nombre_too_short(self) -> None:
        data = {
            "nombreEdificio": "AB",
            "direccion": "Av. Principal, Urb. Centro, calle 1",
            "rif": "J-12345678-0",
            "cantidadPisos": "10",
        }
        errores = validate_building_form(data)
        self.assertIn("nombreEdificio_min", errores)

    def test_invalid_rif(self) -> None:
        data = {
            "nombreEdificio": "Edificio",
            "direccion": "Av. Principal, Urb. Centro, calle 1",
            "rif": "invalid",
            "cantidadPisos": "10",
        }
        errores = validate_building_form(data)
        self.assertIn("rif", errores)

    def test_direccion_too_short(self) -> None:
        data = {
            "nombreEdificio": "Edificio",
            "direccion": "Corta",
            "rif": "J-12345678-0",
            "cantidadPisos": "10",
        }
        errores = validate_building_form(data)
        self.assertIn("direccion_min", errores)

    def test_rif_duplicate(self) -> None:
        Building.objects.create(name="Existente", rif="J-11111111-0", address="Dir 1", floors=10)
        data = {
            "nombreEdificio": "Nuevo",
            "direccion": "Av. Principal, Urb. Centro, calle 1",
            "rif": "J-11111111-0",
            "cantidadPisos": "10",
        }
        errores = validate_building_form(data)
        self.assertIn("rif_unico", errores)


class ValidateUniqueRifTests(TestCase):
    def test_unique_rif_returns_empty(self) -> None:
        self.assertIsNone(validate_unique_rif("J-99999999-0"))

    def test_duplicate_rif_raises_error(self) -> None:
        Building.objects.create(name="Test", rif="J-88888888-0", address="Dir", floors=10)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_unique_rif("J-88888888-0")

    def test_empty_rif_returns_empty(self) -> None:
        self.assertIsNone(validate_unique_rif(""))

    def test_exclude_self(self) -> None:
        building = Building.objects.create(name="Test", rif="J-77777777-0", address="Dir", floors=10)
        self.assertIsNone(validate_unique_rif("J-77777777-0", exclude_building_id=building.id))


class BuildingViewTestBase(TestCase):
    def setUp(self) -> None:
        self.persona = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="User", email="a@a.com")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(
            username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True,
        )
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})


class RegisterBuildingViewTests(BuildingViewTestBase):
    def test_get_returns_form(self) -> None:
        response = self.client.get(reverse("register_building"))
        self.assertEqual(response.status_code, 200)

    def test_post_creates_building(self) -> None:
        response = self.client.post(reverse("register_building"), {
            "nombreEdificio": "Edificio Test",
            "direccion": "Av. Principal, Urb. Centro",
            "rif": "J-11111111-0",
            "cantidadPisos": "10",
            "con_bomba": "true",
            "con_elevador": "true",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Building.objects.filter(rif="J-11111111-0").exists())

    def test_post_missing_fields_shows_error(self) -> None:
        response = self.client.post(reverse("register_building"), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete el nombre")


class BuildingListViewTests(BuildingViewTestBase):
    def test_lists_buildings(self) -> None:
        Building.objects.create(name="Test Edificio", rif="J-22222222-0", address="Dir", floors=10)
        response = self.client.get(reverse("building_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Edificio")

    def test_search_by_name(self) -> None:
        Building.objects.create(name="Buscado", rif="J-33333333-0", address="Dir", floors=10)
        Building.objects.create(name="Otro", rif="J-44444444-0", address="Dir", floors=10)
        response = self.client.get(reverse("building_list"), {"q": "Buscado"})
        self.assertContains(response, "Buscado")
        self.assertNotContains(response, "Otro")


class DeleteBuildingViewTests(BuildingViewTestBase):
    def test_delete_building(self) -> None:
        building = Building.objects.create(name="Test", rif="J-55555555-0", address="Dir", floors=10)
        response = self.client.post(reverse("delete_building", args=[building.id]), {"confirmed": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Building.objects.filter(id=building.id).exists())

    def test_cascade_deletes_equipment(self) -> None:
        building = Building.objects.create(name="Test", rif="J-66666666-0", address="Dir", floors=10)
        equipo = MonitoringEquipment.objects.create(name="Bomba 1", building=building, equipment_type="bomba")
        self.client.post(reverse("delete_building", args=[building.id]), {"confirmed": "1"})
        self.assertFalse(MonitoringEquipment.objects.filter(id=equipo.id).exists())


class ConfigurationViewTests(BuildingViewTestBase):
    def test_get_config_page(self) -> None:
        response = self.client.get(reverse("configuration"))
        self.assertEqual(response.status_code, 200)

    def test_update_email(self) -> None:
        response = self.client.post(reverse("configuration"), {
            "action": "update_profile",
            "email": "nuevo@test.com",
            "username": "",
            "current_password": "admin123",
            "new_password": "",
            "confirm_password": "",
        })
        self.assertEqual(response.status_code, 302)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.email, "nuevo@test.com")

    def test_wrong_current_password(self) -> None:
        response = self.client.post(reverse("configuration"), {
            "action": "change_password",
            "email": "",
            "username": "",
            "current_password": "wrong",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no es correcta")
