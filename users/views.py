from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets, permissions, generics
from .serializers import UserSerializer
from django.contrib.auth import get_user_model

class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

class UserViewSet(viewsets.ModelViewSet):
    queryset = get_user_model().objects.all().order_by('-date_joined')
    serializer_class = UserSerializer   
    permission_classes = [permissions.IsAdminUser]
    
    # Añadimos los backends de filtrado
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    # Configuramos por qué campos se puede filtrar/buscar
    filterset_fields = ['is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['date_joined', 'username']   