"""
Estados de préstamo y ajustes de stock: todo el stock lo maneja el backend.
"""

from __future__ import annotations

import datetime as dt
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from loans.models import MaterialLoan
from materials.models import Material

User = get_user_model()


def mock_image() -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, "png")
    return SimpleUploadedFile("estado.png", buffer.getvalue(), content_type="image/png")


class LoanStatusStockTests(APITestCase):
    def setUp(self) -> None:
        self.requester = User.objects.create_user(username="alumno", password="x")
        self.other = User.objects.create_user(username="otro", password="x")
        self.admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.material = Material.objects.create(name="Router", quantity=3, status="Disponible")

    def stock(self) -> int:
        self.material.refresh_from_db()
        return self.material.quantity

    def create_loan(self, quantity: int = 2):
        self.client.force_authenticate(user=self.requester)
        response = self.client.post(
            reverse("material-loan-list"),
            data={
                "items": [{"material": self.material.id, "quantity": quantity}],
                "loan_period_days": 3,
                "loan_date": dt.date.today().isoformat(),
                "return_date": (dt.date.today() + dt.timedelta(days=3)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["status"], "Pendiente")
        return MaterialLoan.objects.get(pk=response.data["data"]["id"])

    def approve(self, loan: MaterialLoan) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            reverse("material-loan-detail", kwargs={"pk": loan.pk}),
            data={"approved_by_user_id": self.admin.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "Autorizado")

    def test_create_deducts_and_approve_keeps_stock(self) -> None:
        loan = self.create_loan()
        self.assertEqual(self.stock(), 1)
        self.approve(loan)
        self.assertEqual(self.stock(), 1)

    def test_finalize_with_condition_report_returns_stock(self) -> None:
        loan = self.create_loan()
        self.approve(loan)
        self.client.force_authenticate(user=self.requester)
        response = self.client.post(
            reverse("material-loan-condition-report", kwargs={"pk": loan.pk}),
            data={"description": "Todo bien", "photo": mock_image()},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        loan.refresh_from_db()
        self.assertEqual(loan.status, "Finalizado")
        self.assertEqual(self.stock(), 3)

    def test_admin_reject_returns_stock(self) -> None:
        loan = self.create_loan()
        url = reverse("material-loan-reject", kwargs={"pk": loan.pk})
        self.client.force_authenticate(user=self.requester)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "Rechazado")
        self.assertEqual(self.stock(), 3)
        # No se puede rechazar dos veces (no devuelve stock de más)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.stock(), 3)

    def test_requester_cancel_returns_stock(self) -> None:
        loan = self.create_loan()
        url = reverse("material-loan-cancel", kwargs={"pk": loan.pk})
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.requester)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "Cancelado")
        self.assertEqual(self.stock(), 3)

    def test_cannot_cancel_or_reject_authorized_loan(self) -> None:
        loan = self.create_loan()
        self.approve(loan)
        self.client.force_authenticate(user=self.requester)
        self.assertEqual(
            self.client.post(reverse("material-loan-cancel", kwargs={"pk": loan.pk})).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(
            self.client.post(reverse("material-loan-reject", kwargs={"pk": loan.pk})).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(self.stock(), 1)

    def test_delete_returns_stock_even_with_return_date(self) -> None:
        pending = self.create_loan(quantity=1)
        self.client.force_authenticate(user=self.requester)
        response = self.client.delete(reverse("material-loan-detail", kwargs={"pk": pending.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.stock(), 3)

        authorized = self.create_loan(quantity=2)
        self.approve(authorized)
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(reverse("material-loan-detail", kwargs={"pk": authorized.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.stock(), 3)

    def test_delete_closed_loan_does_not_return_stock_twice(self) -> None:
        loan = self.create_loan()
        self.client.force_authenticate(user=self.requester)
        self.client.post(reverse("material-loan-cancel", kwargs={"pk": loan.pk}))
        self.assertEqual(self.stock(), 3)
        self.client.force_authenticate(user=self.admin)
        self.client.delete(reverse("material-loan-detail", kwargs={"pk": loan.pk}))
        self.assertEqual(self.stock(), 3)

    def test_requester_cannot_change_items(self) -> None:
        loan = self.create_loan(quantity=1)
        self.client.force_authenticate(user=self.requester)
        response = self.client.patch(
            reverse("material-loan-detail", kwargs={"pk": loan.pk}),
            data={"items": [{"material": self.material.id, "quantity": 3}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "Para cambiar los materiales cancela la solicitud y crea una nueva")
        self.assertEqual(self.stock(), 2)
        self.assertEqual(loan.items.get().quantity, 1)

    def test_closed_loan_cannot_be_modified(self) -> None:
        loan = self.create_loan(quantity=1)
        self.client.force_authenticate(user=self.admin)
        self.client.post(reverse("material-loan-reject", kwargs={"pk": loan.pk}))
        response = self.client.patch(
            reverse("material-loan-detail", kwargs={"pk": loan.pk}),
            data={"approved_by_user_id": self.admin.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        loan.refresh_from_db()
        self.assertEqual(loan.status, "Rechazado")

    def test_material_status_follows_stock(self) -> None:
        loan = self.create_loan(quantity=3)
        self.material.refresh_from_db()
        self.assertEqual(self.material.status, "No disponible")
        self.client.force_authenticate(user=self.requester)
        self.client.post(reverse("material-loan-cancel", kwargs={"pk": loan.pk}))
        self.material.refresh_from_db()
        self.assertEqual(self.material.status, "Disponible")

    def test_filter_by_status(self) -> None:
        pending = self.create_loan(quantity=1)
        cancelled = self.create_loan(quantity=1)
        self.client.post(reverse("material-loan-cancel", kwargs={"pk": cancelled.pk}))
        response = self.client.get(reverse("material-loan-list"), {"status": "Pendiente"})
        self.assertEqual([item["id"] for item in response.data["data"]], [pending.id])
