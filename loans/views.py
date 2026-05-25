"""
API endpoints for material loans.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from django.db import transaction, models as django_models
from core.json_api_mixin import WrappedStandardApiMixin

from .models import MaterialLoan
from .serializers import MaterialLoanSerializer


class MaterialLoanViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """
    Full CRUD for material loans.

    - Any authenticated user may create a loan for themselves.
    - Non-superusers only see and mutate their own loans (until approved, then no edits).
    - Superusers see all loans and may set ``approved_by_user_id`` to authorize.
    """

    serializer_class = MaterialLoanSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self) -> QuerySet[MaterialLoan]:
        base_queryset = MaterialLoan.objects.select_related("requested_by", "approved_by", "material").all()
        request_user = self.request.user
        if request_user.is_superuser:
            return base_queryset
        return base_queryset.filter(requested_by=request_user)

    def perform_create(self, serializer: MaterialLoanSerializer) -> None:
        with transaction.atomic():
            instance = serializer.save(requested_by=self.request.user)
            # Deduct stock when request is created
            material = instance.material
            material.quantity -= instance.quantity
            material.save()

    def perform_update(self, serializer: MaterialLoanSerializer) -> None:
        with transaction.atomic():
            old_instance = self.get_object()
            old_quantity = old_instance.quantity
            old_returned = old_instance.return_date is not None

            instance = serializer.save()

            # Update stock
            material = instance.material
            new_returned = instance.return_date is not None

            if not old_returned and new_returned:
                # Returned: Add back to stock
                material.quantity += instance.quantity
                material.save()
            elif old_returned and not new_returned:
                # Return date removed: Deduct from stock
                material.quantity -= instance.quantity
                material.save()
            elif not new_returned:
                # Still active, quantity might have changed
                qty_diff = instance.quantity - old_quantity
                if qty_diff != 0:
                    material.quantity -= qty_diff
                    material.save()

    def perform_destroy(self, instance: MaterialLoan) -> None:
        request_user = self.request.user
        if not request_user.is_superuser:
            if instance.requested_by_id != request_user.id:
                raise PermissionDenied("You can only delete your own loan requests.")
            if instance.approved_by_id is not None:
                raise PermissionDenied("Approved loans cannot be deleted by the requester.")
        
        with transaction.atomic():
            # If the loan was active (not returned), return the items to stock
            if instance.return_date is None:
                material = instance.material
                material.quantity += instance.quantity
                material.save()
            instance.delete()

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        loan_primary_key = instance.pk
        self.perform_destroy(instance)
        return Response(status=200, data={"id": loan_primary_key, "deleted": True})
