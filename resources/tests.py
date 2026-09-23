from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Resource

User = get_user_model()


class ResourceApiTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.docente = User.objects.create_user(username="docente", password="x", is_staff=True)
        self.otro_docente = User.objects.create_user(username="docente2", password="x", is_staff=True)
        self.alumno = User.objects.create_user(username="alumno", password="x")

    def create(self, user, **extra):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("resource-list"),
            data={"title": "Guía VLAN", "description": "Configuración básica", **extra},
            format="multipart",
        )

    def test_docente_creates_resource_with_file(self) -> None:
        pdf = SimpleUploadedFile("guia.pdf", b"%PDF-1.4", content_type="application/pdf")
        response = self.create(self.docente, file=pdf)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertTrue(data["file"].startswith("http://testserver/media/resources/"))
        self.assertEqual(data["created_by"], self.docente.id)
        for field in ("id", "title", "description", "created_at"):
            self.assertIn(field, data)

    def test_resource_without_file_and_required_fields(self) -> None:
        response = self.create(self.admin)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["data"]["file"])
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(reverse("resource-list"), data={"title": "Sin descripción"}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_alumno_reads_but_cannot_create(self) -> None:
        self.create(self.docente)
        self.assertEqual(self.create(self.alumno).status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(reverse("resource-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)

    def test_anonymous_cannot_read(self) -> None:
        self.assertEqual(self.client.get(reverse("resource-list")).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_author_or_admin_can_edit_or_delete(self) -> None:
        resource_id = self.create(self.docente).data["data"]["id"]
        url = reverse("resource-detail", kwargs={"pk": resource_id})

        self.client.force_authenticate(user=self.otro_docente)
        self.assertEqual(self.client.patch(url, data={"title": "X"}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.docente)
        self.assertEqual(self.client.patch(url, data={"title": "Nueva"}).status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Resource.objects.exists())
