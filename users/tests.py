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
