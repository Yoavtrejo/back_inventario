"""
Tests for ConditionReport model and API endpoints.
"""

from __future__ import annotations

import io
import datetime as dt
from PIL import Image

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from loans.models import MaterialLoan, ConditionReport
from materials.models import Material

User = get_user_model()


def get_mock_image(size_bytes: int = 100, filename: str = 'test.png') -> SimpleUploadedFile:
    """Genera una imagen mock en memoria para pruebas."""
    file = io.BytesIO()
    image = Image.new('RGB', (10, 10), 'red')
    image.save(file, 'png')
    file.seek(0)
    
    # Si queremos simular un tamaño específico superior al generado
    if size_bytes > len(file.getvalue()):
        content = file.read() + b'0' * (size_bytes - len(file.getvalue()))
    else:
        content = file.read()
        
    return SimpleUploadedFile(filename, content, content_type='image/png')


class ConditionReportTests(APITestCase):
    """Pruebas para creación, lectura, actualización y validación de Reportes de Condición."""

    def setUp(self) -> None:
        self.requester = User.objects.create_user(
            username="requester",
            email="requester@example.com",
            password="pass-requester-123",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="pass-other-456",
        )
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="pass-admin-789",
        )
        self.material = Material.objects.create(
            name="Cable UTP Cat6 10m",
            quantity=5,
            min_stock=1,
            max_stock=20,
            status="Disponible"
        )
        
        # Préstamo aprobado listo para reporte
        self.approved_loan = MaterialLoan.objects.create(
            material=self.material,
            quantity=1,
            loan_period_days=5,
            loan_date=dt.date.today(),
            requested_by=self.requester,
            approved_by=self.superuser,
        )

        # Préstamo pendiente (sin aprobación)
        self.pending_loan = MaterialLoan.objects.create(
            material=self.material,
            quantity=1,
            loan_period_days=5,
            loan_date=dt.date.today(),
            requested_by=self.requester,
        )

    def test_create_report_success_and_payload_structure(self) -> None:
        """El solicitante puede reportar la condición de un préstamo aprobado con éxito."""
        self.client.force_authenticate(user=self.requester)
        mock_photo = get_mock_image()
        
        url = reverse("material-loan-condition-report", kwargs={"pk": self.approved_loan.pk})
        response = self.client.post(
            url,
            data={
                "description": "El cable viene con el conector RJ45 flojo.",
                "photo": mock_photo,
            },
            format="multipart",
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        
        report_data = response.data["data"]
        self.assertEqual(report_data["description"], "El cable viene con el conector RJ45 flojo.")
        self.assertIn("photo", report_data)
        
        # Validar que se actualizó la bandera en el modelo Loan
        self.approved_loan.refresh_from_db()
        self.assertTrue(self.approved_loan.has_condition_report)
        self.assertTrue(ConditionReport.objects.filter(loan=self.approved_loan).exists())

    def test_cannot_create_report_for_unapproved_loan(self) -> None:
        """No se puede reportar la condición de un préstamo que no esté aprobado."""
        self.client.force_authenticate(user=self.requester)
        mock_photo = get_mock_image()
        
        url = reverse("material-loan-condition-report", kwargs={"pk": self.pending_loan.pk})
        response = self.client.post(
            url,
            data={
                "description": "Está dañado.",
                "photo": mock_photo,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(
            response.data["message"], 
            "No se puede reportar la condición de un préstamo que aún no ha sido aprobado."
        )

    def test_cannot_create_duplicate_report(self) -> None:
        """No se puede crear más de un reporte de condición para un mismo préstamo."""
        # Creamos el primer reporte
        ConditionReport.objects.create(
            loan=self.approved_loan,
            user=self.requester,
            description="Primer reporte",
            photo=get_mock_image()
        )
        self.approved_loan.has_condition_report = True
        self.approved_loan.save()

        self.client.force_authenticate(user=self.requester)
        url = reverse("material-loan-condition-report", kwargs={"pk": self.approved_loan.pk})
        response = self.client.post(
            url,
            data={
                "description": "Segundo reporte",
                "photo": get_mock_image(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Ya existe un reporte de condición para este préstamo.")

    def test_only_requester_or_superuser_can_create_report(self) -> None:
        """Un usuario ajeno al préstamo no puede reportar la condición."""
        self.client.force_authenticate(user=self.other_user)
        url = reverse("material-loan-condition-report", kwargs={"pk": self.approved_loan.pk})
        response = self.client.post(
            url,
            data={"description": "Intruso", "photo": get_mock_image()},
            format="multipart",
        )
        # Debería dar 404 porque no puede acceder al objeto en su queryset filtrado
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_report_details(self) -> None:
        """El solicitante y el admin pueden ver el reporte de condición."""
        report = ConditionReport.objects.create(
            loan=self.approved_loan,
            user=self.requester,
            description="Tiene raspones",
            photo=get_mock_image()
        )
        
        # Test requester GET
        self.client.force_authenticate(user=self.requester)
        url = reverse("material-loan-condition-report", kwargs={"pk": self.approved_loan.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["description"], "Tiene raspones")

        # Test admin GET
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test other user GET -> 404 Not Found (filtered out of queryset)
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_put_updates_description_but_ignores_photo(self) -> None:
        """PUT actualiza la descripción pero ignora cambios de foto."""
        initial_photo = get_mock_image(filename="initial.png")
        report = ConditionReport.objects.create(
            loan=self.approved_loan,
            user=self.requester,
            description="Inicial",
            photo=initial_photo
        )
        initial_photo_url = report.photo.url

        self.client.force_authenticate(user=self.requester)
        new_photo = get_mock_image(filename="new.png")
        url = reverse("material-loan-condition-report", kwargs={"pk": self.approved_loan.pk})
        
        response = self.client.put(
            url,
            data={
                "description": "Actualizado",
                "photo": new_photo,
            },
            format="multipart",
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["description"], "Actualizado")
        
        # El endpoint de actualización debe ignorar la foto o no cambiarla
        report.refresh_from_db()
        self.assertEqual(report.photo.url, initial_photo_url)

    def test_photo_size_validation(self) -> None:
        """La foto no debe superar los 5MB de tamaño."""
        self.client.force_authenticate(user=self.requester)
        # 6MB mock file
        huge_photo = get_mock_image(size_bytes=6 * 1024 * 1024)
        
        url = reverse("material-loan-condition-report", kwargs={"pk": self.approved_loan.pk})
        response = self.client.post(
            url,
            data={
                "description": "Foto muy grande",
                "photo": huge_photo,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")
        self.assertIn("La imagen no debe pesar más de 5MB.", response.data["message"])
