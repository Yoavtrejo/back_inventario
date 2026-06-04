import io
import qrcode
from django.http import HttpResponse
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from core.json_api_mixin import WrappedStandardApiMixin

from .models import Isla, Reservacion
from .serializers import IslaSerializer, ReservacionSerializer


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
        Reservacion.actualizar_reservaciones_expiradas()
        base_queryset = Reservacion.objects.select_related('isla', 'alumno').all()
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
