from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from history import models
from .models import Material
from .serializers import MaterialSerializer
# Create your views here.

class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer

    @action(detail=False, methods=['get'])
    def available(self, request):
        low_stock_materials = Material.objects.filter(quantity__lte=models.F('min_stock'))
        serializer = self.get_serializer(low_stock_materials, many=True)
        return Response(serializer.data)

    # Endpoint extra: /api/materiales/by_status/?status=damaged
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        status_param = request.query_params.get('status')
        if status_param:
            materials = Material.objects.filter(status=status_param)
            serializer = self.get_serializer(materials, many=True)
            return Response(serializer.data)
        return Response({"error": "Debe proporcionar un status"}, status=status.HTTP_400_BAD_REQUEST)
