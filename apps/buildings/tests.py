from django.test import TestCase
from django.urls import reverse
from apps.buildings.validators import _validate_unique_rif, validate_building_form
from apps.buildings.models import Edificio, EquipoMonitoreo, UsuarioEdificio
from apps.users.models import Persona, Usuario


# ─── VALIDATOR TESTS ──────────────────────────────────────────────────

class ValidateBuildingFormTests(TestCase):
    def test_valid_data_returns_empty(self):
        data = {"nombreEdificio": "Edificio Principal", "direccion": "Av. Principal, Urb. Centro, calle 1", "rif": "J-12345678-0"}
        errores = validate_building_form(data)
        self.assertEqual(errores, {})

    def test_nombre_too_short(self):
        data = {"nombreEdificio": "AB", "direccion": "Av. Principal, Urb. Centro, calle 1", "rif": "J-12345678-0"}
        errores = validate_building_form(data)
        self.assertIn("nombreEdificio_min", errores)

    def test_invalid_rif(self):
        data = {"nombreEdificio": "Edificio", "direccion": "Av. Principal, Urb. Centro, calle 1", "rif": "invalid"}
        errores = validate_building_form(data)
        self.assertIn("rif", errores)

    def test_direccion_too_short(self):
        data = {"nombreEdificio": "Edificio", "direccion": "Corta", "rif": "J-12345678-0"}
        errores = validate_building_form(data)
        self.assertIn("direccion_min", errores)

    def test_rif_duplicate(self):
        Edificio.objects.create(nb_edificio="Existente", rif="J-11111111-0", direccion="Dir 1")
        data = {"nombreEdificio": "Nuevo", "direccion": "Av. Principal, Urb. Centro, calle 1", "rif": "J-11111111-0"}
        errores = validate_building_form(data)
        self.assertIn("rif_unico", errores)


class ValidateUniqueRifTests(TestCase):
    def test_unique_rif_returns_empty(self):
        self.assertEqual(_validate_unique_rif("J-99999999-0"), "")

    def test_duplicate_rif_returns_error(self):
        Edificio.objects.create(nb_edificio="Test", rif="J-88888888-0", direccion="Dir")
        msg = _validate_unique_rif("J-88888888-0")
        self.assertNotEqual(msg, "")

    def test_empty_rif_returns_empty(self):
        self.assertEqual(_validate_unique_rif(""), "")

    def test_exclude_self(self):
        edif = Edificio.objects.create(nb_edificio="Test", rif="J-77777777-0", direccion="Dir")
        self.assertEqual(_validate_unique_rif("J-77777777-0", exclude_edificio_id=edif.id_edificio), "")


# ─── VIEW TESTS ──────────────────────────────────────────────────────

class BuildingViewTestBase(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", last_name="User", email="a@a.com", phone="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(
            username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True,
        )
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})


class RegistroEdificioViewTests(BuildingViewTestBase):
    def test_get_returns_form(self):
        response = self.client.get(reverse("registro_edificio"))
        self.assertEqual(response.status_code, 200)

    def test_post_creates_edificio(self):
        response = self.client.post(reverse("registro_edificio"), {
            "nombreEdificio": "Edificio Test",
            "parroquia": "Av. Principal, Urb. Centro",
            "rif": "J-11111111-0",
            "con_bomba": "true",
            "con_elevador": "true",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Edificio.objects.filter(rif="J-11111111-0").exists())

    def test_post_missing_fields_shows_error(self):
        response = self.client.post(reverse("registro_edificio"), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Complete el nombre")


class ListaEdificiosViewTests(BuildingViewTestBase):
    def test_lists_edificios(self):
        Edificio.objects.create(nb_edificio="Test Edificio", rif="J-22222222-0", direccion="Dir")
        response = self.client.get(reverse("lista_edificios"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Edificio")

    def test_search_by_name(self):
        Edificio.objects.create(nb_edificio="Buscado", rif="J-33333333-0", direccion="Dir")
        Edificio.objects.create(nb_edificio="Otro", rif="J-44444444-0", direccion="Dir")
        response = self.client.get(reverse("lista_edificios"), {"q": "Buscado"})
        self.assertContains(response, "Buscado")
        self.assertNotContains(response, "Otro")


class EliminarEdificioViewTests(BuildingViewTestBase):
    def test_delete_edificio(self):
        edif = Edificio.objects.create(nb_edificio="Test", rif="J-55555555-0", direccion="Dir")
        response = self.client.post(reverse("eliminar_edificio", args=[edif.id_edificio]))
        self.assertFalse(Edificio.objects.filter(id_edificio=edif.id_edificio).exists())

    def test_cascade_deletes_equipos(self):
        edif = Edificio.objects.create(nb_edificio="Test", rif="J-66666666-0", direccion="Dir")
        equipo = EquipoMonitoreo.objects.create(nb_equipo="Bomba 1", id_edificio=edif, tipo="bomba")
        self.client.post(reverse("eliminar_edificio", args=[edif.id_edificio]))
        self.assertFalse(EquipoMonitoreo.objects.filter(id_equipo_monitoreo=equipo.id_equipo_monitoreo).exists())


class ConfiguracionViewTests(BuildingViewTestBase):
    def test_get_config_page(self):
        response = self.client.get(reverse("configuracion"))
        self.assertEqual(response.status_code, 200)

    def test_update_email(self):
        response = self.client.post(reverse("configuracion"), {
            "email": "nuevo@test.com",
            "username": "",
            "current_password": "admin123",
            "new_password": "",
            "confirm_password": "",
        })
        self.assertEqual(response.status_code, 302)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.email, "nuevo@test.com")

    def test_wrong_current_password(self):
        response = self.client.post(reverse("configuracion"), {
            "email": "",
            "username": "",
            "current_password": "wrong",
            "new_password": "",
            "confirm_password": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no es correcta")
