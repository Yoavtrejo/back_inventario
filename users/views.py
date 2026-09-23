import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets, permissions, generics
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from core.json_api_mixin import WrappedStandardApiMixin
from core.permissions import IsSuperUser
from .models import Carrera
from .serializers import UserSerializer, ProfileSerializer, RegisterSerializer, CarreraSerializer
from .utils import enviar_correo_bienvenida

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
            enviar_correo_bienvenida(user)
        except Exception:
            logger.exception('No se pudo enviar el correo de bienvenida a %s', user.email)


class CarreraViewSet(WrappedStandardApiMixin, viewsets.ReadOnlyModelViewSet):
    """Catálogo de carreras para el formulario de registro (público)."""
    queryset = Carrera.objects.all()
    serializer_class = CarreraSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    pagination_class = None
