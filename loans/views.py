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

from rest_framework.decorators import action
from .models import MaterialLoan, ConditionReport
from .serializers import MaterialLoanSerializer, ConditionReportSerializer



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

    @action(detail=True, methods=['get', 'post', 'put'], url_path='condition-report', url_name='condition-report')
    def condition_report(self, request: Request, pk: Any = None) -> Response:
        """
        API endpoints to manage condition reports for a specific loan.
        - GET: retrieve report.
        - POST: create report with photo.
        - PUT: update description (photo cannot be updated).
        """
        loan = self.get_object()
        
        # Permissions check: Only the requester or superuser can access/mutate.
        if not request.user.is_superuser and loan.requested_by_id != request.user.id:
            raise PermissionDenied("No tienes permiso para acceder al reporte de este préstamo.")

        # GET: Retrieve report
        if request.method == 'GET':
            try:
                report = loan.condition_report
                serializer = ConditionReportSerializer(report, context={'request': request})
                return Response(serializer.data)
            except ConditionReport.DoesNotExist:
                return Response({"detail": "No se ha reportado ninguna condición para este préstamo."}, status=404)

        # POST: Create report
        elif request.method == 'POST':
            if hasattr(loan, 'condition_report'):
                return Response({"detail": "Ya existe un reporte de condición para este préstamo."}, status=400)
            
            if loan.approved_by_id is None:
                return Response({"detail": "No se puede reportar la condición de un préstamo que aún no ha sido aprobado."}, status=400)

            serializer = ConditionReportSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                with transaction.atomic():
                    report = serializer.save(loan=loan, user=request.user)
                    loan.has_condition_report = True
                    loan.save()
                return Response(serializer.data, status=201)
            return Response(serializer.errors, status=400)

        # PUT: Update report description
        elif request.method == 'PUT':
            try:
                report = loan.condition_report
            except ConditionReport.DoesNotExist:
                return Response({"detail": "No existe un reporte de condición para este préstamo."}, status=404)
            
            # Only allow updating description, pop photo if present
            data = request.data.copy()
            if 'photo' in data:
                data.pop('photo')

            serializer = ConditionReportSerializer(report, data=data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=400)

