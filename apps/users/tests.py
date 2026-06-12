from django.test import TestCase
from django.urls import reverse

from apps.users.models import Persona, Usuario
from apps.users.services import (
    build_beneficiary_data,
    build_random_username,
    generate_random_password,
)
from apps.users.validators import (
    _validate_field,
    _validate_min_length,
    _validate_max_length,
    _validate_phone,
    _validate_rif,
    _validate_email,
    _validate_unique_email,
    _validate_unique_ci,
    validate_user_form,
    REGEX_ONLY_LETTERS,
    REGEX_ONLY_NUMBERS,
    REGEX_EMAIL,
    REGEX_USERNAME,
)

# ─── VALIDATOR TESTS (pure logic, no DB) ────────────────────────────────


class ValidateFieldTests(TestCase):
    def test_valid_value_returns_empty(self):
        self.assertEqual(_validate_field("Juan", REGEX_ONLY_LETTERS, "error"), "")

    def test_invalid_value_returns_message(self):
        msg = _validate_field("Juan123", REGEX_ONLY_LETTERS, "Solo letras")
        self.assertEqual(msg, "Solo letras")

    def test_empty_value_returns_empty(self):
        self.assertEqual(_validate_field("", REGEX_ONLY_LETTERS, "error"), "")


class ValidateLengthTests(TestCase):
    def test_min_ok(self):
        self.assertEqual(_validate_min_length("abc", 3, "Campo"), "")

    def test_min_fail(self):
        msg = _validate_min_length("ab", 3, "Campo")
        self.assertIn("al menos 3", msg)

    def test_min_empty_ok(self):
        self.assertEqual(_validate_min_length("", 3, "Campo"), "")

    def test_max_ok(self):
        self.assertEqual(_validate_max_length("abc", 3, "Campo"), "")

    def test_max_fail(self):
        msg = _validate_max_length("abcd", 3, "Campo")
        self.assertIn("no puede tener más de 3", msg)


class ValidatePhoneTests(TestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(_validate_phone(""), "")

    def test_valid_with_spaces_and_plus(self):
        self.assertEqual(_validate_phone("+58 412 1234567"), "")

    def test_invalid_characters(self):
        msg = _validate_phone("abc123")
        self.assertNotEqual(msg, "")

    def test_too_few_digits(self):
        msg = _validate_phone("123")
        self.assertNotEqual(msg, "")


class ValidateRifTests(TestCase):
    def test_empty_rif_returns_error(self):
        self.assertNotEqual(_validate_rif(""), "")

    def test_valid_j_rif(self):
        self.assertEqual(_validate_rif("J-12345678-0"), "")

    def test_valid_v_rif(self):
        self.assertEqual(_validate_rif("V123456780"), "")

    def test_invalid_format(self):
        self.assertNotEqual(_validate_rif("ABC123"), "")


class ValidateEmailTests(TestCase):
    def test_empty_returns_error(self):
        self.assertNotEqual(_validate_email(""), "")

    def test_valid_email(self):
        self.assertEqual(_validate_email("test@example.com"), "")

    def test_invalid_email(self):
        self.assertNotEqual(_validate_email("not-an-email"), "")

    def test_local_part_too_long(self):
        local = "a" * 31
        self.assertNotEqual(_validate_email(f"{local}@example.com"), "")

    def test_too_short_email(self):
        self.assertNotEqual(_validate_email("a@b.c"), "")


# ─── VALIDATOR TESTS (DB required) ────────────────────────────────────


class ValidateUniqueEmailDBTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="12345678", name="Test", last_name="User",
            email="existing@test.com", phone="04121234567",
        )

    def test_duplicate_email_returns_error(self):
        msg = _validate_unique_email("existing@test.com")
        self.assertNotEqual(msg, "")

    def test_unique_email_returns_empty(self):
        self.assertEqual(_validate_unique_email("new@test.com"), "")

    def test_exclude_self(self):
        msg = _validate_unique_email(
            "existing@test.com", exclude_persona_id=self.persona.id_persona
        )
        self.assertEqual(msg, "")


class ValidateUniqueCiDBTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="87654321", name="Test", last_name="User",
            email="t@t.com", phone="04121234567",
        )

    def test_duplicate_ci_returns_error(self):
        msg = _validate_unique_ci("87654321")
        self.assertNotEqual(msg, "")

    def test_unique_ci_returns_empty(self):
        self.assertEqual(_validate_unique_ci("11111111"), "")


class ValidateFormTests(TestCase):
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
        errors = validate_user_form(data)
        self.assertEqual(errors, {})

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
        errors = validate_user_form(data)
        self.assertIn("primerNombre", errors)
        self.assertIn("primerApellido", errors)
        self.assertIn("email", errors)
        self.assertIn("cedula", errors)
        self.assertIn("telefono", errors)


# ─── SERVICE TESTS ─────────────────────────────────────────────────────


class BuildBeneficiaryDataTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="12345678", name="Juan", last_name="Pérez",
            email="juan@test.com", phone="04121234567",
        )
        self.user = Usuario.objects.create(
            username="jperez", password="abc123",
            id_persona=self.persona, rol="US",
        )

    def test_build_with_persona(self):
        data = build_beneficiary_data(self.user)
        self.assertEqual(data["cedula"], "12345678")
        self.assertEqual(data["nombre"], "Juan")
        self.assertEqual(data["last_name"], "Pérez")
        self.assertEqual(data["email"], "juan@test.com")
        self.assertEqual(data["phone"], "04121234567")

    def test_build_without_persona_uses_username(self):
        p = Persona.objects.create(
            ci="11111111", name="", last_name="",
            email="np@test.com", phone="",
        )
        user = Usuario.objects.create(
            username="nopersona", password="abc123",
            id_persona=p, rol="US",
        )
        data = build_beneficiary_data(user)
        self.assertEqual(data["nombre"], "nopersona")


class BuildRandomUsernameTests(TestCase):
    def test_generates_username(self):
        username = build_random_username("Juan", "Pérez")
        self.assertIsNotNone(username)
        self.assertTrue(REGEX_USERNAME.match(username))

    def test_raises_on_empty_names(self):
        with self.assertRaises(ValueError):
            build_random_username("", "")
        with self.assertRaises(ValueError):
            build_random_username("Juan", "")

    def test_increments_on_collision(self):
        p = Persona.objects.create(
            ci="22222222", name="Col", last_name="Lis",
            email="col@test.com", phone="",
        )
        Usuario.objects.create(
            username="JPérez", password="abc",
            id_persona=p, rol="US",
        )
        username = build_random_username("Juan", "Pérez")
        self.assertNotEqual(username, "JPérez")


class GenerateRandomPasswordTests(TestCase):
    def test_default_length(self):
        pwd = generate_random_password()
        self.assertEqual(len(pwd), 10)

    def test_custom_length(self):
        pwd = generate_random_password(20)
        self.assertEqual(len(pwd), 20)

    def test_contains_valid_chars(self):
        pwd = generate_random_password()
        self.assertTrue(pwd.isascii())


# ─── VIEW TESTS ────────────────────────────────────────────────────────


class LoginViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="12345678", name="Admin", last_name="User",
            email="admin@test.com", phone="04121234567",
        )
        from django.contrib.auth.hashers import make_password
        self.user = Usuario.objects.create(
            username="admin", password=make_password("admin123"),
            id_persona=self.persona, rol="SA", registered=True,
        )

    def test_login_get_renders_form(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/login.html")

    def test_login_post_success(self):
        response = self.client.post(
            reverse("login"), {"username": "admin", "password": "admin123"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session.get("usuario_id"), self.user.id_usuario
        )

    def test_login_post_invalid(self):
        response = self.client.post(
            reverse("login"), {"username": "admin", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "incorrectos")

    def test_logout(self):
        self.client.post(
            reverse("login"), {"username": "admin", "password": "admin123"}
        )
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get("usuario_id"))


class BeneficiaryListViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="12345678", name="Admin", last_name="User",
            email="admin@test.com", phone="04121234567",
        )
        from django.contrib.auth.hashers import make_password
        self.user = Usuario.objects.create(
            username="admin", password=make_password("admin123"),
            id_persona=self.persona, rol="SA", registered=True,
        )
        self.client.post(
            reverse("login"), {"username": "admin", "password": "admin123"}
        )

    def test_lista_requires_admin(self):
        self.client.get(reverse("logout"))
        p = Persona.objects.create(
            ci="87654321", name="Normal", last_name="User",
            email="n@n.com", phone="04120000000",
        )
        from django.contrib.auth.hashers import make_password
        us_user = Usuario.objects.create(
            username="us", password=make_password("abc"),
            id_persona=p, rol="US",
        )
        self.client.post(reverse("login"), {"username": "us", "password": "abc"})
        response = self.client.get(reverse("lista_usuario"))
        self.assertEqual(response.status_code, 302)

    def test_lista_shows_beneficiarios(self):
        Persona.objects.create(
            ci="87654321", name="Test", last_name="User",
            email="t@t.com", phone="04121234567",
        )
        response = self.client.get(reverse("lista_usuario"))
        self.assertEqual(response.status_code, 200)


class BeneficiaryCreateViewTests(TestCase):
    def setUp(self):
        self.persona = Persona.objects.create(
            ci="12345678", name="Admin", last_name="User",
            email="admin@test.com", phone="04121234567",
        )
        from django.contrib.auth.hashers import make_password
        self.user = Usuario.objects.create(
            username="admin", password=make_password("admin123"),
            id_persona=self.persona, rol="SA", registered=True,
        )
        self.client.post(
            reverse("login"), {"username": "admin", "password": "admin123"}
        )

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
