from rest_framework import viewsets, permissions
from .models import LoanHistory
from .serializers import LoanHistorySerializer
from core.json_api_mixin import WrappedStandardApiMixin

class LoanHistoryViewSet(WrappedStandardApiMixin, viewsets.ReadOnlyModelViewSet):
    """
    Vista de solo lectura para el historial de préstamos.
    - Superusuarios pueden ver todo el historial.
    - Usuarios normales solo ven su propio historial.
    """
    serializer_class = LoanHistorySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        base_queryset = LoanHistory.objects.all()
        request_user = self.request.user
        
        if request_user.is_anonymous:
            return LoanHistory.objects.none()
            
        if request_user.is_superuser:
            return base_queryset
            
        return base_queryset.filter(requested_by_username=request_user.username)

