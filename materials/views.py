from django.db.models import F
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.json_api_mixin import WrappedStandardApiMixin
from core.permissions import IsSuperUserOrReadOnly
from .models import Material
from .serializers import MaterialSerializer


class MaterialViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """
    - Lectura: cualquier usuario autenticado.
    - Escritura: solo superusuarios. El stock por préstamos lo ajusta el backend (app loans).
    """
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer
    permission_classes = (IsSuperUserOrReadOnly,)

    # Materiales con stock bajo (cantidad <= stock mínimo)
    @action(detail=False, methods=['get'])
    def available(self, request):
        low_stock_materials = Material.objects.filter(quantity__lte=F('min_stock'))
        serializer = self.get_serializer(low_stock_materials, many=True)
        return Response(serializer.data)

    # Endpoint extra: /api/materials/by_status/?status=Danado
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        status_param = request.query_params.get('status')
        if status_param:
            materials = Material.objects.filter(status=status_param)
            serializer = self.get_serializer(materials, many=True)
            return Response(serializer.data)
        return Response({"detail": "Debe proporcionar un status"}, status=status.HTTP_400_BAD_REQUEST)
