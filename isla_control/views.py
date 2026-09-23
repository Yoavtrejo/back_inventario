import io
from datetime import datetime
import qrcode
from django.http import HttpResponse
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from core.json_api_mixin import WrappedStandardApiMixin

from .models import Isla, Reservacion, HorarioBloqueado
from datetime import timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .serializers import IslaSerializer, ReservacionSerializer, HorarioBloqueadoSerializer, OcupacionSerializer


class IsSuperUserOrReadOnly(permissions.BasePermission):
    """
    Permiso personalizado: solo superusuarios pueden editar (POST, PUT, DELETE).
    Usuarios normales autenticados solo pueden leer (GET).
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_superuser


class IslaViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """
    Controlador para la gestión de las Islas de trabajo.
    - Operaciones de escritura: Solo Superusuarios.
    - Operaciones de lectura: Cualquier usuario autenticado.
    """
    serializer_class = IslaSerializer
    permission_classes = (IsSuperUserOrReadOnly,)

    def get_queryset(self):
        Reservacion.actualizar_reservaciones_expiradas()
        return Isla.objects.all()

    @action(detail=True, methods=['get'], url_path='qr')
    def generar_qr(self, request, pk=None):
        """
        Genera y devuelve la imagen PNG del código QR de la isla.
        """
        isla = self.get_object()
        
        # El código QR contendrá el token de la isla para validación
        qr_data = str(isla.qr_token)
        
        # Generar código QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        
        # Guardar en memoria
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        return HttpResponse(buffer.getvalue(), content_type="image/png")


class ReservacionViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """
    Controlador para la gestión de Reservaciones.
    - Usuarios normales solo ven y gestionan sus propias reservaciones.
    - Superusuarios ven y gestionan todas las reservaciones.
    """
    serializer_class = ReservacionSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Reservacion.objects.none()
        Reservacion.actualizar_reservaciones_expiradas()
        base_queryset = Reservacion.objects.select_related('isla', 'alumno__profile__carrera').all()
        if self.request.user.is_superuser:
            return base_queryset
        return base_queryset.filter(alumno=self.request.user)

    def perform_create(self, serializer):
        serializer.save(alumno=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            old_isla = self.get_object().isla
            reservacion = serializer.save()
            if old_isla != reservacion.isla:
                old_isla.actualizar_estado()

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=False, methods=['post'], url_path='escanear')
    def escanear_qr(self, request):
        """
        Escanea el QR para iniciar el temporizador de la reserva.
        Se espera: {"qr_token": "..."}
        """
        qr_token = request.data.get('qr_token')
        if not qr_token:
            raise ValidationError({"qr_token": "Este campo es requerido."})

        try:
            isla = Isla.objects.get(qr_token=qr_token)
        except (Isla.DoesNotExist, ValueError, ValidationError):
            raise ValidationError({"qr_token": "Código QR inválido o isla no encontrada."})

        # Buscar una reservación activa del alumno para hoy en esta isla que no haya iniciado aún
        hoy = timezone.localdate()
        reservacion = Reservacion.objects.filter(
            isla=isla,
            alumno=request.user,
            fecha_reserva=hoy,
            hora_escaneo_inicio__isnull=True,
            completada=False,
            cancelada=False
        ).first()

        if not reservacion:
            return Response(
                {"detail": "No tienes una reservación programada para hoy en esta isla que esté lista para iniciar."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Iniciar el temporizador
        reservacion.hora_escaneo_inicio = timezone.now()
        reservacion.save()

        return Response(
            {
                "detail": "Código QR escaneado con éxito. Su tiempo de reserva ha comenzado.",
                "reservacion_id": reservacion.id,
                "hora_inicio_real": reservacion.hora_escaneo_inicio
            },
            status=status.HTTP_200_OK
        )

    OCUPACION_MAX_DIAS = 31

    @extend_schema(
        parameters=[
            OpenApiParameter('desde', str, required=True, description='YYYY-MM-DD'),
            OpenApiParameter('hasta', str, required=True, description='YYYY-MM-DD (máximo 31 días después de desde)'),
        ],
        responses=OcupacionSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='ocupacion')
    def ocupacion(self, request):
        """
        Reservaciones no canceladas de todas las islas en un rango de fechas, sin datos personales.
        Sirve para que el calendario muestre los horarios ocupados por otros alumnos.
        """
        fechas = {}
        for param in ('desde', 'hasta'):
            valor = request.query_params.get(param)
            try:
                fechas[param] = datetime.strptime(valor or '', '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError({param: 'Requerido con formato YYYY-MM-DD.'})
        desde, hasta = fechas['desde'], fechas['hasta']
        if hasta < desde:
            raise ValidationError({'hasta': 'Debe ser igual o posterior a desde.'})
        if hasta - desde > timedelta(days=self.OCUPACION_MAX_DIAS):
            raise ValidationError({'hasta': f'El rango máximo es de {self.OCUPACION_MAX_DIAS} días.'})

        Reservacion.actualizar_reservaciones_expiradas()
        reservaciones = Reservacion.objects.filter(
            fecha_reserva__range=(desde, hasta), cancelada=False
        ).order_by('fecha_reserva', 'hora_inicio')
        serializer = OcupacionSerializer(reservaciones, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        """Cancela una reservación activa."""
        reservacion = self.get_object()

        if reservacion.cancelada:
            return Response(
                {"detail":"Esta reservación ya está cancelada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if reservacion.completada:
            return Response(
                {"detail":"No se puede cancelar una reservación completada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not request.user.is_superuser and reservacion.alumno != request.user:
            raise PermissionDenied("No tienes permiso para cancelar está reservación.")

        with transaction.atomic():
            reservacion.cancelada = True
            reservacion.save()

        serializer = self.get_serializer(reservacion)
        return Response(serializer.data)

class HorarioBloqueadoViewSet(viewsets.ModelViewSet):
    """
    Gestión de horarios bloqueados.
    - Lectura: cualquier usuario autenticado
    - Escritura: solo superusuarios
    """

    serializer_class = HorarioBloqueadoSerializer
    permission_classes = (permissions.IsAuthenticated,) 

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return HorarioBloqueado.objects.none()
        return HorarioBloqueado.objects.select_related('isla', 'created_by').all()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied('Solo los administradores pueden bloquear horarios.')
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied('Solo los administradores pueden modificar bloqueos.')
        serializer.save()

    def perform_destroy(self, instance):
        if not self.request.user.is_superuser:
            raise PermissionDenied('Solo los administradores pueden eliminar bloqueos.')
        instance.delete()