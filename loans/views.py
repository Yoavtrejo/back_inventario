"""
API endpoints for material loans.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from rest_framework import generics, permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from django.db import transaction, models as django_models
from core.json_api_mixin import WrappedStandardApiMixin

from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from .models import MaterialLoan, ConditionReport
from .serializers import MaterialLoanSerializer, ConditionReportSerializer
from .stock import adjust_material_stock


class MaterialLoanViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """
    Full CRUD for material loans.

    - Any authenticated user may create a loan for themselves.
    - Non-superusers only see and mutate their own loans (until approved, then no edits).
    - Superusers see all loans and may set ``approved_by_user_id`` to authorize.
    """

    serializer_class = MaterialLoanSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filterset_fields = ("status", "material")

    def get_queryset(self) -> QuerySet[MaterialLoan]:
        if getattr(self, "swagger_fake_view", False):
            return MaterialLoan.objects.none()
            
        base_queryset = MaterialLoan.objects.select_related("requested_by__profile__carrera", "approved_by__profile__carrera", "material").all()
        request_user = self.request.user
        
        if request_user.is_anonymous:
            return MaterialLoan.objects.none()
            
        if request_user.is_superuser:
            return base_queryset
        return base_queryset.filter(requested_by=request_user)

    def get_serializer_class(self) -> Any:
        if self.action == 'condition_report':
            return ConditionReportSerializer
        return super().get_serializer_class()


    def perform_create(self, serializer: MaterialLoanSerializer) -> None:
        with transaction.atomic():
            # El stock se descuenta al crear la solicitud (queda Pendiente)
            adjust_material_stock(
                serializer.validated_data["material"].pk, -serializer.validated_data["quantity"]
            )
            serializer.save(requested_by=self.request.user)

    def perform_update(self, serializer: MaterialLoanSerializer) -> None:
        with transaction.atomic():
            # serializer.instance tiene el objeto ANTES de guardar
            instance = serializer.instance
            old_material_id = instance.material_id
            old_held = instance.quantity if instance.is_active else 0

            updated = serializer.save()

            new_held = updated.quantity if updated.is_active else 0
            if updated.material_id == old_material_id:
                if new_held != old_held:
                    adjust_material_stock(updated.material_id, old_held - new_held)
            else:
                adjust_material_stock(old_material_id, old_held)
                adjust_material_stock(updated.material_id, -new_held)

    def perform_destroy(self, instance: MaterialLoan) -> None:
        request_user = self.request.user
        if not request_user.is_superuser:
            if instance.requested_by_id != request_user.id:
                raise PermissionDenied("You can only delete your own loan requests.")
            if instance.approved_by_id is not None:
                raise PermissionDenied("Approved loans cannot be deleted by the requester.")
        
        with transaction.atomic():
            loan = MaterialLoan.objects.select_for_update().get(pk=instance.pk)
            # Si el préstamo seguía activo (Pendiente o Autorizado), el material regresa al stock
            if loan.is_active:
                adjust_material_stock(loan.material_id, loan.quantity)
            loan.delete()

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
            
            if loan.status == MaterialLoan.Status.PENDIENTE:
                return Response({"detail": "No se puede reportar la condición de un préstamo que aún no ha sido aprobado."}, status=400)
            if loan.status != MaterialLoan.Status.AUTORIZADO:
                return Response({"detail": f"El préstamo está {loan.status} y no puede finalizarse."}, status=400)

            serializer = ConditionReportSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                with transaction.atomic():
                    loan = MaterialLoan.objects.select_for_update().get(pk=loan.pk)
                    if loan.status != MaterialLoan.Status.AUTORIZADO:
                        return Response({"detail": f"El préstamo está {loan.status} y no puede finalizarse."}, status=400)
                    serializer.save(loan=loan, user=request.user)
                    # El reporte de condición finaliza el préstamo y devuelve el material al stock
                    adjust_material_stock(loan.material_id, loan.quantity)
                    loan.has_condition_report = True
                    loan.status = MaterialLoan.Status.FINALIZADO
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

    @extend_schema(request=None, responses=MaterialLoanSerializer)
    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request: Request, pk: Any = None) -> Response:
        """Rechaza un préstamo Pendiente (solo admin) y devuelve el material al stock."""
        if not request.user.is_superuser:
            raise PermissionDenied("Solo un administrador puede rechazar préstamos.")
        return self._close_pending_loan(self.get_object(), MaterialLoan.Status.RECHAZADO, "rechazar")

    @extend_schema(request=None, responses=MaterialLoanSerializer)
    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request: Request, pk: Any = None) -> Response:
        """Cancela un préstamo Pendiente (solo el solicitante) y devuelve el material al stock."""
        loan = self.get_object()
        if loan.requested_by_id != request.user.id:
            raise PermissionDenied("Solo el solicitante puede cancelar su préstamo.")
        return self._close_pending_loan(loan, MaterialLoan.Status.CANCELADO, "cancelar")

    def _close_pending_loan(self, loan: MaterialLoan, new_status: str, verb: str) -> Response:
        with transaction.atomic():
            loan = MaterialLoan.objects.select_for_update().get(pk=loan.pk)
            if loan.status != MaterialLoan.Status.PENDIENTE:
                return Response(
                    {"detail": f"Solo se pueden {verb} préstamos pendientes. Estado actual: {loan.status}."},
                    status=400,
                )
            adjust_material_stock(loan.material_id, loan.quantity)
            loan.status = new_status
            loan.save()
        return Response(MaterialLoanSerializer(loan, context=self.get_serializer_context()).data)


class ConditionReportListCreateView(generics.ListCreateAPIView):
    serializer_class   = ConditionReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False): 
            return ConditionReport.objects.none()

        user = self.request.user
        if user.is_superuser:
            return ConditionReport.objects.select_related('loan', 'user').all()
        return ConditionReport.objects.select_related('loan', 'user').filter(user=user)