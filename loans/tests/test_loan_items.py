"""
Préstamos con varios materiales: una solicitud, varios renglones y stock de todos.
"""

from __future__ import annotations

import datetime as dt
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from history.models import LoanHistory
from loans.models import LoanItem, MaterialLoan
from materials.models import Material

User = get_user_model()


def mock_image() -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, "png")
    return SimpleUploadedFile("estado.png", buffer.getvalue(), content_type="image/png")


class LoanItemsApiTests(APITestCase):
    def setUp(self) -> None:
        self.requester = User.objects.create_user(username="alumno", password="x")
        self.admin = User.objects.create_superuser(username="admin", email="a@example.com", password="x")
        self.cable = Material.objects.create(name="Cable Ethernet", quantity=5)
        self.pinzas = Material.objects.create(name="Pinzas para ponchar", quantity=2)
        self.url = reverse("material-loan-list")

    def payload(self, items):
        return {
            "items": items,
            "loan_period_days": 7,
            "loan_date": dt.date.today().isoformat(),
            "return_date": (dt.date.today() + dt.timedelta(days=7)).isoformat(),
        }

    def post(self, items, user=None):
        self.client.force_authenticate(user=user or self.requester)
        return self.client.post(self.url, data=self.payload(items), format="json")

    def stocks(self):
        self.cable.refresh_from_db()
        self.pinzas.refresh_from_db()
        return self.cable.quantity, self.pinzas.quantity

    def create_two_item_loan(self):
        response = self.post([
            {"material": self.cable.id, "quantity": 2},
            {"material": self.pinzas.id, "quantity": 1},
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return MaterialLoan.objects.get(pk=response.data["data"]["id"])

    def approve(self, loan):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            reverse("material-loan-detail", kwargs={"pk": loan.pk}),
            data={"approved_by_user_id": self.admin.id}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_one_loan_with_two_items_deducts_both(self) -> None:
        response = self.post([
            {"material": self.cable.id, "quantity": 2},
            {"material": self.pinzas.id, "quantity": 1},
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertNotIn("material", data)
        self.assertNotIn("quantity", data)
        self.assertEqual(
            [(i["material"], i["material_name"], i["quantity"]) for i in data["items"]],
            [(self.cable.id, "Cable Ethernet", 2), (self.pinzas.id, "Pinzas para ponchar", 1)],
        )
        self.assertTrue(all("id" in i for i in data["items"]))
        self.assertEqual(MaterialLoan.objects.count(), 1)
        self.assertEqual(LoanItem.objects.count(), 2)
        self.assertEqual(self.stocks(), (3, 1))

    def test_insufficient_stock_in_one_item_creates_nothing(self) -> None:
        response = self.post([
            {"material": self.cable.id, "quantity": 2},
            {"material": self.pinzas.id, "quantity": 3},
        ])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "No hay suficiente stock de Pinzas para ponchar. Disponible: 2")
        self.assertFalse(MaterialLoan.objects.exists())
        self.assertEqual(self.stocks(), (5, 2))

    def test_invalid_items(self) -> None:
        response = self.post([
            {"material": self.cable.id, "quantity": 1},
            {"material": self.cable.id, "quantity": 2},
        ])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "Material repetido: Cable Ethernet")

        self.assertEqual(self.post([]).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.post([{"material": self.cable.id, "quantity": 0}]).status_code, 400)
        self.assertEqual(self.post([{"material": 99999, "quantity": 1}]).status_code, 400)

        many = [Material.objects.create(name=f"M{i}", quantity=1) for i in range(21)]
        response = self.post([{"material": m.id, "quantity": 1} for m in many])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MaterialLoan.objects.exists())

    def test_reject_returns_all_items(self) -> None:
        loan = self.create_two_item_loan()
        self.client.force_authenticate(user=self.admin)
        self.client.post(reverse("material-loan-reject", kwargs={"pk": loan.pk}))
        self.assertEqual(self.stocks(), (5, 2))

    def test_cancel_returns_all_items(self) -> None:
        loan = self.create_two_item_loan()
        self.client.post(reverse("material-loan-cancel", kwargs={"pk": loan.pk}))
        self.assertEqual(self.stocks(), (5, 2))

    def test_delete_returns_all_items(self) -> None:
        loan = self.create_two_item_loan()
        response = self.client.delete(reverse("material-loan-detail", kwargs={"pk": loan.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.stocks(), (5, 2))
        self.assertFalse(LoanItem.objects.exists())

    def test_finalize_returns_all_items(self) -> None:
        loan = self.create_two_item_loan()
        self.approve(loan)
        self.client.force_authenticate(user=self.requester)
        response = self.client.post(
            reverse("material-loan-condition-report", kwargs={"pk": loan.pk}),
            data={"description": "Todo bien", "photo": mock_image()}, format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.stocks(), (5, 2))

    def test_stock_zero_marks_material_unavailable(self) -> None:
        loan = self.post([{"material": self.pinzas.id, "quantity": 2}]).data["data"]
        self.pinzas.refresh_from_db()
        self.assertEqual(self.pinzas.status, "No disponible")
        self.client.post(reverse("material-loan-cancel", kwargs={"pk": loan["id"]}))
        self.pinzas.refresh_from_db()
        self.assertEqual(self.pinzas.status, "Disponible")

    def test_filter_by_material_includes_multi_item_loans(self) -> None:
        both = self.create_two_item_loan()
        only_cable = self.post([{"material": self.cable.id, "quantity": 1}]).data["data"]["id"]
        response = self.client.get(self.url, {"material": self.pinzas.id})
        self.assertEqual([loan["id"] for loan in response.data["data"]], [both.id])
        response = self.client.get(self.url, {"material": self.cable.id})
        self.assertEqual(sorted(loan["id"] for loan in response.data["data"]), sorted([both.id, only_cable]))

    def test_history_on_approval_has_items_and_summary(self) -> None:
        loan = self.create_two_item_loan()
        self.approve(loan)
        history = LoanHistory.objects.get(original_loan_id=loan.id)
        self.assertEqual(history.items, [
            {"material_name": "Cable Ethernet", "quantity": 2},
            {"material_name": "Pinzas para ponchar", "quantity": 1},
        ])
        self.assertEqual(history.material_name, "2 × Cable Ethernet, 1 × Pinzas para ponchar")
        self.assertEqual(history.quantity, 3)

        response = self.client.get(reverse("history-list"))
        self.assertEqual(response.data["data"][0]["items"], history.items)

    def test_history_when_admin_creates_loan_already_approved(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            data={**self.payload([{"material": self.cable.id, "quantity": 1}]), "approved_by_user_id": self.admin.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["status"], "Autorizado")
        history = LoanHistory.objects.get(original_loan_id=response.data["data"]["id"])
        self.assertEqual(history.material_name, "1 × Cable Ethernet")


class LoanItemsDataMigrationTests(TransactionTestCase):
    before = [("loans", "0003_materialloan_status"), ("history", "0001_initial")]
    after = [("loans", "0006_remove_materialloan_material_quantity"), ("history", "0002_loanhistory_items")]

    def tearDown(self) -> None:
        # Deja la base de pruebas en el esquema actual para los demás tests
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_existing_loans_get_one_item_and_history_gets_items(self) -> None:
        old_apps = self.migrate(self.before)
        user = old_apps.get_model("auth", "User").objects.create(username="alumno")
        material = old_apps.get_model("materials", "Material").objects.create(name="Router", quantity=4)
        old_apps.get_model("loans", "MaterialLoan").objects.create(
            material=material, quantity=3, loan_period_days=2, loan_date=dt.date.today(), requested_by=user,
        )
        old_apps.get_model("history", "LoanHistory").objects.create(
            original_loan_id=1, material_name="Router", quantity=3, requested_by_username="alumno",
            approved_by_username="admin", loan_date=dt.date.today(), loan_period_days=2,
        )

        new_apps = self.migrate(self.after)
        loan = new_apps.get_model("loans", "MaterialLoan").objects.get()
        items = list(new_apps.get_model("loans", "LoanItem").objects.filter(loan=loan))
        self.assertEqual([(i.material_id, i.quantity) for i in items], [(material.id, 3)])
        history = new_apps.get_model("history", "LoanHistory").objects.get()
        self.assertEqual(history.items, [{"material_name": "Router", "quantity": 3}])

        # La migración es reversible
        old_apps = self.migrate(self.before)
        loan = old_apps.get_model("loans", "MaterialLoan").objects.get()
        self.assertEqual((loan.material_id, loan.quantity), (material.id, 3))
