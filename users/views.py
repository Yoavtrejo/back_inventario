from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets, permissions, generics
from django.contrib.auth import get_user_model
from core.permissions import IsSuperUser
from .serializers import UserSerializer, ProfileSerializer
from .utils import enviar_correo_bienvenida

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

class UserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.all().order_by('-date_joined')
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
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['date_joined', 'username']


 