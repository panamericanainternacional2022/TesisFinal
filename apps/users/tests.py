import re
from django.test import TestCase
from django.urls import reverse
from django.contrib import messages
from unittest.mock import patch, Mock

from apps.users.validators import (
    _validar_campo, _validar_longitud_min, _validar_longitud_max,
    _validar_telefono, _validar_rif, _validar_email,
    _validar_unico_email, _validar_unico_ci, _validar_unico_telefono,
    _validaciones_formulario_usuario,
    REGEX_SOLO_LETRAS, REGEX_SOLO_NUMEROS, REGEX_EMAIL, REGEX_USERNAME,
)
from apps.users.models import Persona, Usuario
from apps.users.services import _build_beneficiario_data, _build_random_username, _generate_random_password


# ─── VALIDATOR TESTS (pure logic, no DB) ────────────────────────────────

class ValidarCampoTests(TestCase):
    def test_valid_value_returns_none(self):
        self.assertIsNone(_validar_campo("Juan", REGEX_SOLO_LETRAS, "error"))

    def test_invalid_value_returns_message(self):
        msg = _validar_campo("Juan123", REGEX_SOLO_LETRAS, "Solo letras")
        self.assertEqual(msg, "Solo letras")

    def test_empty_value_returns_none(self):
        self.assertIsNone(_validar_campo("", REGEX_SOLO_LETRAS, "error"))


class ValidarLongitudTests(TestCase):
    def test_min_ok(self):
        self.assertIsNone(_validar_longitud_min("abc", 3, "Campo"))

    def test_min_fail(self):
        msg = _validar_longitud_min("ab", 3, "Campo")
        self.assertIn("al menos 3", msg)

    def test_min_empty_ok(self):
        self.assertIsNone(_validar_longitud_min("", 3, "Campo"))

    def test_max_ok(self):
        self.assertIsNone(_validar_longitud_max("abc", 3, "Campo"))

    def test_max_fail(self):
        msg = _validar_longitud_max("abcd", 3, "Campo")
        self.assertIn("no puede tener más de 3", msg)


class ValidarTelefonoTests(TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(_validar_telefono(""))

    def test_valid_with_spaces_and_plus(self):
        self.assertIsNone(_validar_telefono("+58 412 1234567"))

    def test_invalid_characters(self):
        msg = _validar_telefono("abc123")
        self.assertIsNotNone(msg)

    def test_too_few_digits(self):
        msg = _validar_telefono("123")
        self.assertIsNotNone(msg)


class ValidarRifTests(TestCase):
    def test_empty_rif_returns_error(self):
        self.assertIsNotNone(_validar_rif(""))

    def test_valid_j_rif(self):
        self.assertIsNone(_validar_rif("J-12345678-0"))

    def test_valid_v_rif(self):
        self.assertIsNone(_validar_rif("V123456780"))

    def test_invalid_format(self):
        self.assertIsNotNone(_validar_rif("ABC123"))


class ValidarEmailTests(TestCase):
    def test_empty_returns_error(self):
        self.assertIsNotNone(_validar_email(""))

    def test_valid_email(self):
        self.assertIsNone(_validar_email("test@example.com"))

    def test_invalid_email(self):
        self.assertIsNotNone(_validar_email("not-an-email"))

    def test_local_part_too_long(self):
        local = "a" * 31
        self.assertIsNotNone(_validar_email(f"{local}@example.com"))

    def test_too_short_email(self):
        self.assertIsNotNone(_validar_email("a@b.c"))


# ─── VALIDATOR TESTS (DB required) ────────────────────────────────────

class ValidarUnicoEmailDBTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Test", apellido="User", email="existing@test.com", telefono="04121234567")

    def test_duplicate_email_returns_error(self):
        msg = _validar_unico_email("existing@test.com")
        self.assertIsNotNone(msg)

    def test_unique_email_returns_none(self):
        self.assertIsNone(_validar_unico_email("new@test.com"))

    def test_exclude_self(self):
        msg = _validar_unico_email("existing@test.com", exclude_persona_id=self.persona.id_persona)
        self.assertIsNone(msg)


class ValidarUnicoCiDBTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="87654321", name="Test", apellido="User", email="t@t.com", telefono="04121234567")

    def test_duplicate_ci_returns_error(self):
        msg = _validar_unico_ci("87654321")
        self.assertIsNotNone(msg)

    def test_unique_ci_returns_none(self):
        self.assertIsNone(_validar_unico_ci("11111111"))


class ValidarFormularioUsuarioTests(TestCase):
    def test_valid_data_returns_empty_dict(self):
        data = {
            "primerNombre": "Juan",
            "segundoNombre": "Carlos",
            "primerApellido": "Pérez",
            "segundoApellido": "Gómez",
            "email": "juan@test.com",
            "cedula": "12345678",
            "telefono": "04121234567",
        }
        errores = _validaciones_formulario_usuario(data)
        self.assertEqual(errores, {})

    def test_invalid_data_returns_errors(self):
        data = {
            "primerNombre": "A1@",
            "segundoNombre": "",
            "primerApellido": "B2#",
            "segundoApellido": "",
            "email": "bad-email",
            "cedula": "abc",
            "telefono": "12",
        }
        errores = _validaciones_formulario_usuario(data)
        self.assertIn("primerNombre", errores)
        self.assertIn("primerApellido", errores)
        self.assertIn("email", errores)
        self.assertIn("cedula", errores)
        self.assertIn("telefono", errores)


# ─── SERVICE TESTS ─────────────────────────────────────────────────────

class BuildBeneficiarioDataTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Juan", apellido="Pérez", email="juan@test.com", telefono="04121234567")
        self.usuario = Usuario.objects.create(username="jperez", password="abc123", id_persona=self.persona, rol="US")

    def test_build_with_persona(self):
        data = _build_beneficiario_data(self.usuario)
        self.assertEqual(data["cedula"], "12345678")
        self.assertEqual(data["nombre"], "Juan")
        self.assertEqual(data["apellido"], "Pérez")
        self.assertEqual(data["email"], "juan@test.com")
        self.assertEqual(data["telefono"], "04121234567")

    def test_build_without_persona_uses_username(self):
        p = Persona.objects.create(ci="11111111", name="", apellido="", email="np@test.com", telefono="")
        usuario = Usuario.objects.create(username="nopersona", password="abc123", id_persona=p, rol="US")
        data = _build_beneficiario_data(usuario)
        self.assertEqual(data["nombre"], "nopersona")


class BuildRandomUsernameTests(TestCase):
    def test_generates_username(self):
        username = _build_random_username("Juan", "Pérez")
        self.assertIsNotNone(username)
        self.assertTrue(REGEX_USERNAME.match(username))

    def test_none_on_empty_names(self):
        self.assertIsNone(_build_random_username("", ""))
        self.assertIsNone(_build_random_username("Juan", ""))

    def test_increments_on_collision(self):
        p = Persona.objects.create(ci="22222222", name="Col", apellido="Lis", email="col@test.com", telefono="")
        Usuario.objects.create(username="JPérez", password="abc", id_persona=p, rol="US")
        username = _build_random_username("Juan", "Pérez")
        self.assertNotEqual(username, "JPérez")
        self.assertTrue(username.startswith("JPérez"))


class GenerateRandomPasswordTests(TestCase):
    def test_default_length(self):
        pwd = _generate_random_password()
        self.assertEqual(len(pwd), 10)

    def test_custom_length(self):
        pwd = _generate_random_password(20)
        self.assertEqual(len(pwd), 20)

    def test_contains_valid_chars(self):
        pwd = _generate_random_password()
        self.assertTrue(pwd.isascii())


# ─── VIEW TESTS ────────────────────────────────────────────────────────

class LoginViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", apellido="User", email="admin@test.com", telefono="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(
            username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registrado=True,
        )

    def test_login_get_renders_form(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/login.html")

    def test_login_post_success(self):
        response = self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("usuario_id"), self.usuario.id_usuario)

    def test_login_post_invalid(self):
        response = self.client.post(reverse("login"), {"username": "admin", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "incorrectos")

    def test_logout(self):
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get("usuario_id"))


class ListaUsuarioViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", apellido="User", email="admin@test.com", telefono="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(
            username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registrado=True,
        )
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_lista_requires_admin(self):
        self.client.get(reverse("logout"))
        us_persona = Persona.objects.create(ci="87654321", name="Normal", apellido="User", email="n@n.com", telefono="04120000000")
        from django.contrib.auth.hashers import make_password
        us_user = Usuario.objects.create(username="us", password=make_password("abc"), id_persona=us_persona, rol="US")
        self.client.post(reverse("login"), {"username": "us", "password": "abc"})
        response = self.client.get(reverse("lista_usuario"))
        self.assertEqual(response.status_code, 302)

    def test_lista_shows_beneficiarios(self):
        Persona.objects.create(ci="87654321", name="Test", apellido="User", email="t@t.com", telefono="04121234567")
        response = self.client.get(reverse("lista_usuario"))
        self.assertEqual(response.status_code, 200)


class RegistroBeneficiarioViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(ci="12345678", name="Admin", apellido="User", email="admin@test.com", telefono="04121234567")
        from django.contrib.auth.hashers import make_password
        self.usuario = Usuario.objects.create(
            username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registrado=True,
        )
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_get_returns_form(self):
        response = self.client.get(reverse("registro_beneficiario"))
        self.assertEqual(response.status_code, 200)

    def test_post_requires_edificio_first(self):
        response = self.client.post(reverse("registro_beneficiario"), {
            "primerNombre": "Test", "primerApellido": "User",
            "email": "test@test.com", "cedula": "99999999",
            "telefono": "04121234567", "id_edificio": "1",
        })
        self.assertContains(response, "Debe registrar al menos un edificio")
