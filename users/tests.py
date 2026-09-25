import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class ProfileApiTests(APITestCase):
    def setUp(self) -> None:
        self.alumno = User.objects.create_user(
            username="alumno", email="alumno@example.com", password="Prueba123!x"
        )
        self.url = reverse("user-profile")

    def test_alumno_cannot_escalate_privileges_via_profile(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        response = self.client.patch(
            self.url,
            data={"is_superuser": True, "is_staff": True, "is_active": False, "username": "hacker"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.alumno.refresh_from_db()
        self.assertFalse(self.alumno.is_superuser)
        self.assertFalse(self.alumno.is_staff)
        self.assertTrue(self.alumno.is_active)
        self.assertEqual(self.alumno.username, "alumno")

    def test_profile_updates_allowed_fields_and_hashes_password(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        response = self.client.patch(
            self.url,
            data={"first_name": "Ana", "last_name": "López", "email": "ana@example.com",
                  "password": "OtraClave456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("password", response.data)
        self.alumno.refresh_from_db()
        self.assertEqual(self.alumno.first_name, "Ana")
        self.assertEqual(self.alumno.email, "ana@example.com")
        self.assertTrue(self.alumno.check_password("OtraClave456!"))

    def test_profile_rejects_email_of_another_user(self) -> None:
        User.objects.create_user(username="otro", email="otro@example.com", password="x")
        self.client.force_authenticate(user=self.alumno)
        response = self.client.patch(self.url, data={"email": "OTRO@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_cannot_read_profile(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserAdminApiTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="x"
        )
        self.docente = User.objects.create_user(
            username="docente", email="docente@example.com", password="x", is_staff=True
        )
        self.alumno = User.objects.create_user(
            username="alumno", email="alumno@example.com", password="x"
        )
        self.payload = {"username": "nuevo", "email": "nuevo@example.com", "password": "Clave123!x"}

    def test_admin_can_create_users(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(reverse("user-list"), data=self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_docente_cannot_manage_users(self) -> None:
        self.client.force_authenticate(user=self.docente)
        response = self.client.post(
            reverse("user-list"), data={**self.payload, "is_superuser": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(reverse("user-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_alumno_cannot_manage_users(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        response = self.client.post(reverse("user-list"), data=self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RegisterApiTests(APITestCase):
    def setUp(self) -> None:
        from users.models import Carrera

        self.carrera = Carrera.objects.create(nombre="Ingeniería en Sistemas")
        self.url = reverse("register")
        self.payload = {
            "first_name": "Luis", "last_name": "Pérez", "matricula": "2230001",
            "email": "luis@example.com", "password": "Segura#2026", "password_confirm": "Segura#2026",
            "carrera": self.carrera.id,
        }

    def test_register_creates_alumno_with_profile(self) -> None:
        from django.core import mail

        response = self.client.post(
            self.url, data={**self.payload, "is_staff": True, "is_superuser": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertEqual(data["username"], "2230001")
        self.assertEqual(data["matricula"], "2230001")
        self.assertEqual(data["carrera"], "Ingeniería en Sistemas")
        self.assertNotIn("password", data)
        self.assertNotIn("password_confirm", data)
        user = User.objects.get(username="2230001")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("Segura#2026"))
        self.assertEqual(len(mail.outbox), 1)

    def test_register_validations(self) -> None:
        response = self.client.post(self.url, data={**self.payload, "password_confirm": "Otra#2026x"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(
            self.url, data={**self.payload, "password": "123", "password_confirm": "123"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(self.client.post(self.url, data=self.payload, format="json").status_code, 201)
        response = self.client.post(self.url, data={**self.payload, "email": "otro@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # matrícula repetida
        response = self.client.post(
            self.url, data={**self.payload, "matricula": "2230002", "email": "LUIS@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # email repetido

    def test_register_survives_email_failure(self) -> None:
        from unittest import mock

        with mock.patch("users.views.enviar_correo_bienvenida", side_effect=OSError("SMTP caído")):
            response = self.client.post(self.url, data=self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_carreras_are_public(self) -> None:
        response = self.client.get(reverse("carrera-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"], [{"id": self.carrera.id, "nombre": "Ingeniería en Sistemas"}])

    def test_profile_fields_are_null_without_profile(self) -> None:
        user = User.objects.create_user(username="viejo", password="x")
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse("user-profile"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["matricula"])
        self.assertIsNone(response.data["carrera"])


class RegisterEmailTests(APITestCase):
    def setUp(self) -> None:
        from users.models import Carrera

        self.payload = {
            "first_name": "Luis", "last_name": "Pérez", "matricula": "2230001",
            "email": "luis@example.com", "password": "Segura#2026", "password_confirm": "Segura#2026",
            "carrera": Carrera.objects.create(nombre="ISC").id,
        }

    @override_settings(FRONTEND_URL="http://front.test")
    def test_register_email_has_matricula_and_no_password(self) -> None:
        response = self.client.post(reverse("register"), data=self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        html = message.alternatives[0][0]
        for content in (message.body, html):
            self.assertIn("2230001", content)
            self.assertIn("la contraseña que elegiste al registrarte", content)
            self.assertIn("http://front.test/login", content)
            self.assertIn("http://front.test/recuperar", content)
            self.assertNotIn("Segura#2026", content)

    def test_admin_created_user_email_is_unchanged(self) -> None:
        admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.client.force_authenticate(user=admin)
        self.client.post(
            reverse("user-list"),
            data={"username": "nuevo", "email": "nuevo@example.com", "password": "Temporal#123"},
            format="json",
        )
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Contraseña temporal", html)
        self.assertIn("Temporal#123", html)


class PasswordResetTests(APITestCase):
    MESSAGE = "Si la cuenta existe, enviamos un enlace de recuperación al correo registrado."

    def setUp(self) -> None:
        cache.clear()  # el throttle guarda su estado en la caché
        self.user = User.objects.create_user(
            username="2230001", email="Luis@Example.com", password="Vieja#2026x", first_name="Luis"
        )
        self.url = reverse("password-reset")
        self.confirm_url = reverse("password-reset-confirm")

    def request_reset(self, identificador):
        response = self.client.post(self.url, data={"identificador": identificador}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"success": True, "data": {"detail": self.MESSAGE}})
        return response

    def link_params(self, message):
        match = re.search(r"http://front\.test/restablecer\?uid=([\w-]+)&token=([\w-]+)", message.body)
        self.assertIsNotNone(match)
        return {"uid": match.group(1), "token": match.group(2)}

    @override_settings(FRONTEND_URL="http://front.test")
    def test_reset_by_matricula_and_email_sends_link(self) -> None:
        self.request_reset("2230001")
        self.request_reset("luis@example.com")
        self.assertEqual(len(mail.outbox), 2)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "SIDERED · Recupera tu contraseña")
        self.assertEqual(message.to, [self.user.email])
        self.assertIn("vence en 1 hora", message.body)
        params = self.link_params(message)
        self.assertIn(params["token"], message.alternatives[0][0])

    def test_unknown_or_inactive_account_gets_same_response_and_no_email(self) -> None:
        User.objects.create_user(username="inactivo", email="in@example.com", password="x", is_active=False)
        self.request_reset("noexiste")
        self.request_reset("inactivo")
        self.assertEqual(mail.outbox, [])

    def test_missing_identificador_is_400(self) -> None:
        response = self.client.post(self.url, data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")

    def test_reset_request_is_throttled(self) -> None:
        for _ in range(5):
            self.request_reset("noexiste")
        response = self.client.post(self.url, data={"identificador": "noexiste"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertFalse(response.data["success"])
        self.assertTrue(response.data["message"])

    @override_settings(FRONTEND_URL="http://front.test")
    def test_confirm_changes_password_and_token_cannot_be_reused(self) -> None:
        self.request_reset("2230001")
        params = self.link_params(mail.outbox[0])
        payload = {**params, "password": "Nueva#2026x", "password_confirm": "Nueva#2026x"}

        response = self.client.post(self.confirm_url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["detail"], "Tu contraseña se actualizó. Ya puedes iniciar sesión.")
        login = self.client.post(
            reverse("token_obtain_pair"), data={"username": "2230001", "password": "Nueva#2026x"}, format="json"
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

        response = self.client.post(
            self.confirm_url, data={**payload, "password": "Otra#2026xy", "password_confirm": "Otra#2026xy"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")
        self.assertEqual(response.data["message"], "El enlace no es válido o ya venció. Solicita uno nuevo.")

    def valid_params(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        return {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
        }

    def test_invalid_token_or_uid_is_400(self) -> None:
        params = self.valid_params()
        for bad in ({**params, "token": "abc-123"}, {**params, "uid": "@@@"}, {**params, "uid": "OTk5OTk"}):
            response = self.client.post(
                self.confirm_url, data={**bad, "password": "Nueva#2026x", "password_confirm": "Nueva#2026x"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data["message"], "El enlace no es válido o ya venció. Solicita uno nuevo.")

    def test_mismatched_and_weak_passwords_are_400(self) -> None:
        params = self.valid_params()
        response = self.client.post(
            self.confirm_url, data={**params, "password": "Nueva#2026x", "password_confirm": "Otra#2026x"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "Las contraseñas no coinciden.")

        response = self.client.post(
            self.confirm_url, data={**params, "password": "123", "password_confirm": "123"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Vieja#2026x"))


class LoginThrottleTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        User.objects.create_user(username="victima", password="Correcta#2026")
        User.objects.create_user(username="otro", password="Otro#2026x")
        self.url = reverse("token_obtain_pair")

    def login(self, username, password):
        return self.client.post(self.url, data={"username": username, "password": password}, format="json")

    def test_brute_force_on_one_account_is_throttled(self) -> None:
        for _ in range(10):
            self.assertEqual(self.login("victima", "mala").status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.login("VICTIMA", "Correcta#2026")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("detail", response.data)
        # Otra cuenta desde la misma IP sigue pudiendo entrar
        response = self.login("otro", "Otro#2026x")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_login_is_throttled_per_ip(self) -> None:
        for i in range(60):
            self.login(f"usuario{i}", "mala")
        self.assertEqual(self.login("otro", "Otro#2026x").status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class TokenRotationTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(username="alumno", email="alumno@example.com", password="Clave#2026x")

    def login(self):
        response = self.client.post(
            reverse("token_obtain_pair"), data={"username": "alumno", "password": "Clave#2026x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["refresh"]

    def refresh(self, token):
        return self.client.post(reverse("token_refresh"), data={"refresh": token}, format="json")

    def test_refresh_rotates_and_old_token_is_rejected(self) -> None:
        old = self.login()
        response = self.refresh(old)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        new = response.data["refresh"]
        self.assertNotEqual(new, old)
        self.assertEqual(self.refresh(old).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.refresh(new).status_code, status.HTTP_200_OK)

    def test_logout_blacklists_refresh(self) -> None:
        token = self.login()
        response = self.client.post(reverse("logout"), data={"refresh": token}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(self.refresh(token).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_closes_existing_sessions(self) -> None:
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        token = self.login()
        self.user.refresh_from_db()  # el login actualiza last_login, que forma parte del token
        response = self.client.post(
            reverse("password-reset-confirm"),
            data={
                "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": default_token_generator.make_token(self.user),
                "password": "Nueva#2026x", "password_confirm": "Nueva#2026x",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.refresh(token).status_code, status.HTTP_401_UNAUTHORIZED)
