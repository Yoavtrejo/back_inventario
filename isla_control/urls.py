from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IslaViewSet, ReservacionViewSet

router = DefaultRouter()
router.register(r'islas', IslaViewSet, basename='isla')
router.register(r'reservaciones', ReservacionViewSet, basename='reservacion')

urlpatterns = [
    path('', include(router.urls)),
]
