from rest_framework import permissions, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from core.json_api_mixin import WrappedStandardApiMixin
from .models import Resource
from .serializers import ResourceSerializer


class ResourcePermission(permissions.BasePermission):
    """
    - Lectura: cualquier usuario autenticado.
    - Crear: docente (is_staff) o admin.
    - Editar/borrar: el autor o un admin.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return user.is_staff or user.is_superuser

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_superuser or obj.created_by_id == request.user.id


class ResourceViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    queryset = Resource.objects.select_related('created_by')
    serializer_class = ResourceSerializer
    permission_classes = (ResourcePermission,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
