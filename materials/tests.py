from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Material

User = get_user_model()


class MaterialApiTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.docente = User.objects.create_user(username="docente", password="x", is_staff=True)
        self.alumno = User.objects.create_user(username="alumno", password="x")
        self.material = Material.objects.create(name="Switch", quantity=1, min_stock=2)
        self.payload = {"name": "Router", "quantity": 5}

    def test_anonymous_cannot_read_or_write(self) -> None:
        self.assertEqual(self.client.get(reverse("material-list")).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.post(reverse("material-list"), data=self.payload, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        detail = reverse("material-detail", kwargs={"pk": self.material.pk})
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(Material.objects.filter(pk=self.material.pk).exists())

    def test_non_admin_can_read_but_not_write(self) -> None:
        detail = reverse("material-detail", kwargs={"pk": self.material.pk})
        for user in (self.alumno, self.docente):
            self.client.force_authenticate(user=user)
            response = self.client.get(reverse("material-list"))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.data["success"])
            self.assertEqual(
                self.client.post(reverse("material-list"), data=self.payload, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.client.patch(detail, data={"quantity": 99}, format="json").status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(self.client.delete(detail).status_code, status.HTTP_403_FORBIDDEN)
        self.material.refresh_from_db()
        self.assertEqual(self.material.quantity, 1)

    def test_admin_can_write(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(reverse("material-list"), data=self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["name"], "Router")

    def test_low_stock_and_by_status_actions(self) -> None:
        self.client.force_authenticate(user=self.alumno)
        response = self.client.get(reverse("material-available"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([m["id"] for m in response.data["data"]], [self.material.id])
        response = self.client.get(reverse("material-by-status"), {"status": "Disponible"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
