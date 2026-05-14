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
        base_queryset = MaterialLoan.objects.select_related("requested_by", "approved_by").all()
        request_user = self.request.user
        if request_user.is_superuser:
            return base_queryset
        return base_queryset.filter(requested_by=request_user)

    def perform_create(self, serializer: MaterialLoanSerializer) -> None:
        serializer.save(requested_by=self.request.user)

    def perform_destroy(self, instance: MaterialLoan) -> None:
        request_user = self.request.user
        if request_user.is_superuser:
            instance.delete()
            return
        if instance.requested_by_id != request_user.id:
            raise PermissionDenied("You can only delete your own loan requests.")
        if instance.approved_by_id is not None:
            raise PermissionDenied("Approved loans cannot be deleted by the requester.")
        instance.delete()

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        loan_primary_key = instance.pk
        self.perform_destroy(instance)
        return Response(status=200, data={"id": loan_primary_key, "deleted": True})
