import logging

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework import filters, viewsets, permissions, generics, serializers
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from core.json_api_mixin import WrappedStandardApiMixin
from core.permissions import IsSuperUser
from .models import Carrera
from .serializers import (UserSerializer, ProfileSerializer, RegisterSerializer, CarreraSerializer,
                          PasswordResetRequestSerializer, PasswordResetConfirmSerializer)
from .utils import enviar_correo_bienvenida, enviar_correo_recuperacion

logger = logging.getLogger(__name__)

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

class UserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.select_related('profile__carrera').order_by('-date_joined')
    serializer_class = UserSerializer   
    # IsAdminUser solo valida is_staff (docentes); la gestión de usuarios es solo para admins
    permission_classes = [IsSuperUser]

    def perform_create(self, serializer):
        raw_password = self.request.data.get('password', None)
        user = serializer.save()
        enviar_correo_bienvenida(user, raw_password)
    
    # Añadimos los backends de filtrado
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Configuramos por qué campos se puede filtrar/buscar
    filterset_fields = ['is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'profile__matricula']
    ordering_fields = ['date_joined', 'username']


@extend_schema(responses={201: ProfileSerializer})
class RegisterView(WrappedStandardApiMixin, generics.CreateAPIView):
    """Registro público de alumnos (sin sesión)."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def perform_create(self, serializer):
        user = serializer.save()
        # Un fallo del correo no debe impedir el registro
        try:
            enviar_correo_bienvenida(user, origen='registro')
        except Exception:
            logger.exception('No se pudo enviar el correo de bienvenida a %s', user.email)


class CarreraViewSet(WrappedStandardApiMixin, viewsets.ReadOnlyModelViewSet):
    """Catálogo de carreras para el formulario de registro (público)."""
    queryset = Carrera.objects.all()
    serializer_class = CarreraSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    pagination_class = None


class DetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


@extend_schema(responses={200: DetailResponseSerializer})
class PasswordResetRequestView(WrappedStandardApiMixin, generics.GenericAPIView):
    """
    Solicita un enlace de recuperación. Responde siempre lo mismo, exista o no la cuenta,
    para no revelar quién está registrado.
    """
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identificador = serializer.validated_data['identificador'].strip()
        users = get_user_model().objects.filter(
            Q(username__iexact=identificador) | Q(email__iexact=identificador), is_active=True
        ).exclude(email='')
        for user in users:
            try:
                enviar_correo_recuperacion(user)
            except Exception:
                logger.exception('No se pudo enviar el correo de recuperación a %s', user.pk)
        return Response({'detail': 'Si la cuenta existe, enviamos un enlace de recuperación al correo registrado.'})


@extend_schema(responses={200: DetailResponseSerializer})
class PasswordResetConfirmView(WrappedStandardApiMixin, generics.GenericAPIView):
    """Restablece la contraseña con el uid y token del enlace de recuperación."""
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Tu contraseña se actualizó. Ya puedes iniciar sesión.'})
