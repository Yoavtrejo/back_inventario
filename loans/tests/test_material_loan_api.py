"""
Integration tests for material loan CRUD and authorization rules.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from loans.models import MaterialLoan

User = get_user_model()


class MaterialLoanApiTests(APITestCase):
    """Covers happy paths and authorization for material loans."""

    def setUp(self) -> None:
        self.regular_user = User.objects.create_user(
            username="requester",
            email="requester@example.com",
            password="strong-pass-123",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="strong-pass-456",
        )
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="strong-pass-789",
        )

    def test_authenticated_user_can_create_loan_and_payload_is_wrapped(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        loan_date = dt.date.today()
        response = self.client.post(
            reverse("material-loan-list"),
            data={
                "material_name": "Beaker 250ml",
                "quantity": 2,
                "loan_period_days": 7,
                "loan_date": loan_date.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        loan_payload = response.data["data"]
        self.assertEqual(loan_payload["material_name"], "Beaker 250ml")
        self.assertEqual(loan_payload["requested_by"]["id"], self.regular_user.id)

    def test_superuser_can_approve_loan_via_approved_by_user_id(self) -> None:
        loan = MaterialLoan.objects.create(
            material_name="Tripod",
            quantity=1,
            loan_period_days=3,
            loan_date=dt.date.today(),
            requested_by=self.regular_user,
        )
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            reverse("material-loan-detail", kwargs={"pk": loan.pk}),
            data={"approved_by_user_id": self.superuser.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["approved_by"]["id"], self.superuser.id)

    def test_requester_cannot_modify_approved_loan(self) -> None:
        loan = MaterialLoan.objects.create(
            material_name="Burner",
            quantity=1,
            loan_period_days=5,
            loan_date=dt.date.today(),
            requested_by=self.regular_user,
            approved_by=self.superuser,
        )
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.patch(
            reverse("material-loan-detail", kwargs={"pk": loan.pk}),
            data={"quantity": 99},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error_code"], "VALIDATION_ERROR")

    def test_requester_cannot_delete_approved_loan(self) -> None:
        loan = MaterialLoan.objects.create(
            material_name="Lens",
            quantity=1,
            loan_period_days=10,
            loan_date=dt.date.today(),
            requested_by=self.regular_user,
            approved_by=self.superuser,
        )
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.delete(reverse("material-loan-detail", kwargs={"pk": loan.pk}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])

    def test_non_superuser_cannot_access_other_users_loan(self) -> None:
        loan = MaterialLoan.objects.create(
            material_name="Microscope slide",
            quantity=10,
            loan_period_days=2,
            loan_date=dt.date.today(),
            requested_by=self.other_user,
        )
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(reverse("material-loan-detail", kwargs={"pk": loan.pk}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_return_date_must_not_be_before_loan_date(self) -> None:
        self.client.force_authenticate(user=self.regular_user)
        loan_date = dt.date.today()
        response = self.client.post(
            reverse("material-loan-list"),
            data={
                "material_name": "Pipette",
                "quantity": 1,
                "loan_period_days": 1,
                "loan_date": loan_date.isoformat(),
                "return_date": (loan_date - dt.timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
