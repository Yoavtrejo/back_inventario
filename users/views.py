from django.db.models import ProtectedError, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView
from core.throttling import LoginIPThrottle, LoginUsernameThrottle
from rest_framework import filters, viewsets, permissions, generics, serializers
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from core.json_api_mixin import WrappedStandardApiMixin
from core.permissions import IsSuperUser
from .models import Carrera
from .serializers import (UserSerializer, ProfileSerializer, RegisterSerializer, CarreraSerializer,
                          PasswordResetRequestSerializer, PasswordResetConfirmSerializer)
from core.mail import send_in_background
from .utils import enviar_correo_bienvenida, enviar_correo_recuperacion
from academic.enrollment import enroll_student

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
        # Una falla del correo nunca debe convertir el alta en error
        send_in_background(enviar_correo_bienvenida, user, raw_password)
    
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
        # Inscripción automática en los grupos de su cohorte del cuatrimestre activo
        enroll_student(user)
        # Un fallo del correo no debe impedir el registro
        send_in_background(enviar_correo_bienvenida, user, origen='registro')


class ReadOnlyPublicOrSuperUser(permissions.BasePermission):
    """Lectura pública (formulario de registro); escritura solo superusuario."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class CarreraViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """Catálogo de carreras: lectura pública, escritura solo admin."""
    queryset = Carrera.objects.all()
    serializer_class = CarreraSerializer
    permission_classes = [ReadOnlyPublicOrSuperUser]
    pagination_class = None

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise serializers.ValidationError({'non_field_errors': [
                f'No se puede eliminar la carrera {instance.nombre}: tiene alumnos o grupos asociados.'
            ]})


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
        # En segundo plano: la respuesta tarda lo mismo exista o no la cuenta
        for user in users:
            send_in_background(enviar_correo_recuperacion, user)
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


class LoginView(TokenObtainPairView):
    """Login JWT con límite de intentos por IP y por usuario."""
    throttle_classes = [LoginIPThrottle, LoginUsernameThrottle]


class LogoutView(WrappedStandardApiMixin, TokenBlacklistView):
    """Cierra la sesión invalidando el refresh token recibido: {"refresh": "..."}."""
