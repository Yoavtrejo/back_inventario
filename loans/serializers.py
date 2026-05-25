"""
Serializers for material loan APIs.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from materials.models import Material
from .models import MaterialLoan

User = get_user_model()


class LoanActorUserSerializer(serializers.ModelSerializer):
    """Compact user representation for loan actors (requester / approver)."""

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name")


class MaterialLoanSerializer(serializers.ModelSerializer):
    """CRUD serializer with approval rules enforced via fields and validation."""

    requested_by = LoanActorUserSerializer(read_only=True)
    approved_by = LoanActorUserSerializer(read_only=True)

    class Meta:
        model = MaterialLoan
        fields = (
            "id",
            "material",
            "quantity",
            "loan_period_days",
            "loan_date",
            "return_date",
            "requested_by",
            "approved_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "requested_by", "approved_by", "created_at", "updated_at")

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

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        loan_date = attrs.get("loan_date")
        return_date = attrs.get("return_date")
        material = attrs.get("material")
        quantity = attrs.get("quantity")

        if self.instance is not None:
            if loan_date is None:
                loan_date = self.instance.loan_date
            if "return_date" not in attrs:
                return_date = self.instance.return_date
            if material is None:
                material = self.instance.material
            if quantity is None:
                quantity = self.instance.quantity

        if loan_date is not None and return_date is not None and return_date < loan_date:
            raise serializers.ValidationError(
                {"return_date": "Return date must be on or after the loan date."},
            )

        if material is not None and quantity is not None:
            if self.instance is None:
                # Stock validation during creation
                if quantity > material.quantity:
                    raise serializers.ValidationError(
                        {"quantity": f"No hay suficiente stock. Disponible: {material.quantity}"}
                    )
            else:
                # Stock validation during update (adjusting difference)
                qty_diff = quantity - self.instance.quantity
                if qty_diff > 0:
                    if qty_diff > material.quantity:
                        raise serializers.ValidationError(
                            {"quantity": f"No hay suficiente stock. Disponible: {material.quantity}"}
                        )

        return attrs

    def update(self, instance: MaterialLoan, validated_data: dict[str, Any]) -> MaterialLoan:
        request_user = self.context["request"].user
        if not request_user.is_superuser and instance.approved_by_id is not None:
            raise serializers.ValidationError(
                {"approved_by": "Approved loans cannot be modified by the requester."},
            )
        return super().update(instance, validated_data)
