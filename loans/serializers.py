"""
Serializers for material loan APIs.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.files import ProtectedFilesMixin
from users.serializers import UserProfileInfoMixin
from .models import MaterialLoan, LoanItem, ConditionReport
from .stock import hold_items

User = get_user_model()


class LoanActorUserSerializer(UserProfileInfoMixin, serializers.ModelSerializer):
    """Compact user representation for loan actors (requester / approver)."""

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "matricula", "carrera",
                  "cuatrimestre", "grupo", "grupo_escolar")


class LoanItemSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)

    class Meta:
        model = LoanItem
        fields = ("id", "material", "material_name", "quantity")
        read_only_fields = ("id",)
        extra_kwargs = {"quantity": {"min_value": 1}}


class MaterialLoanSerializer(serializers.ModelSerializer):
    """CRUD serializer with approval rules enforced via fields and validation."""

    MAX_ITEMS = 20
    ITEMS_LOCKED_MESSAGE = "Para cambiar los materiales cancela la solicitud y crea una nueva"

    requested_by = LoanActorUserSerializer(read_only=True)
    approved_by = LoanActorUserSerializer(read_only=True)
    items = LoanItemSerializer(many=True, allow_empty=False)

    class Meta:
        model = MaterialLoan
        fields = (
            "id",
            "items",
            "loan_period_days",
            "loan_date",
            "return_date",
            "requested_by",
            "approved_by",
            "has_condition_report",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id", "requested_by", "approved_by", "has_condition_report", "status", "created_at", "updated_at",
        )


    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_superuser:
            self.fields["approved_by_user_id"] = serializers.PrimaryKeyRelatedField(
                source="approved_by",
                queryset=User.objects.all(),
                required=False,
                allow_null=True,
                write_only=True,
            )
        if self.instance is not None:
            # Los materiales solo se definen al crear la solicitud
            self.fields["items"].required = False

    def validate_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(items) > self.MAX_ITEMS:
            raise serializers.ValidationError(f"Máximo {self.MAX_ITEMS} materiales por préstamo.")
        return items

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        loan_date = attrs.get("loan_date")
        return_date = attrs.get("return_date")

        if self.instance is not None:
            if "items" in attrs:
                raise serializers.ValidationError(self.ITEMS_LOCKED_MESSAGE)
            if loan_date is None:
                loan_date = self.instance.loan_date
            if "return_date" not in attrs:
                return_date = self.instance.return_date

        if loan_date is not None and return_date is not None and return_date < loan_date:
            raise serializers.ValidationError(
                {"return_date": "Return date must be on or after the loan date."},
            )

        seen = set()
        for item in attrs.get("items", []):
            material = item["material"]
            if material.pk in seen:
                raise serializers.ValidationError(f"Material repetido: {material.name}")
            seen.add(material.pk)
            # Validación previa; el descuento definitivo se hace con bloqueo en hold_items
            if item["quantity"] > material.quantity:
                raise serializers.ValidationError(
                    f"No hay suficiente stock de {material.name}. Disponible: {material.quantity}"
                )

        return attrs

    def create(self, validated_data: dict[str, Any]) -> MaterialLoan:
        # Se llama dentro de transaction.atomic() (MaterialLoanViewSet.perform_create)
        items = validated_data.pop("items")
        hold_items((item["material"].pk, item["quantity"]) for item in items)
        loan = super().create(validated_data)
        LoanItem.objects.bulk_create(
            LoanItem(loan=loan, material=item["material"], quantity=item["quantity"]) for item in items
        )
        return loan

    def update(self, instance: MaterialLoan, validated_data: dict[str, Any]) -> MaterialLoan:
        request_user = self.context["request"].user
        if not instance.is_active:
            raise serializers.ValidationError(
                {"status": f"El préstamo está {instance.status} y ya no puede modificarse."},
            )
        if not request_user.is_superuser and instance.approved_by_id is not None:
            raise serializers.ValidationError(
                {"approved_by": "Approved loans cannot be modified by the requester."},
            )
        return super().update(instance, validated_data)


class ConditionReportSerializer(ProtectedFilesMixin, serializers.ModelSerializer):
    """Serializer for the material condition report."""

    user = LoanActorUserSerializer(read_only=True)

    class Meta:
        model = ConditionReport
        fields = (
            "id",
            "loan",
            "user",
            "description",
            "photo",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "loan", "user", "created_at", "updated_at")

    def validate_photo(self, value):
        # Validate that the file is an image and is less than 5MB
        if value:
            # Check file size (5MB max)
            max_size = 5 * 1024 * 1024
            if value.size > max_size:
                raise serializers.ValidationError("La imagen no debe pesar más de 5MB.")
        return value

