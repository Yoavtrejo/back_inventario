from django.contrib.auth import get_user_model
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
