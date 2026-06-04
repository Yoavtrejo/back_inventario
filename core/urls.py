from django.contrib import admin  # <--- No olvides este import
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from users.views import UserViewSet, UserProfileView
from loans.views import MaterialLoanViewSet
from materials.views import MaterialViewSet
from isla_control.views import IslaViewSet, ReservacionViewSet
from history.views import LoanHistoryViewSet
from academic.views import (TermViewSet, SubjectViewSet, ClassGroupViewSet, 
                            ActivityViewSet, WorkTeamViewSet, SubmissionViewSet)

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'material-loans', MaterialLoanViewSet, basename='material-loan')
router.register(r'materials', MaterialViewSet, basename='material')
router.register(r'islas', IslaViewSet, basename='isla')
router.register(r'reservaciones', ReservacionViewSet, basename='reservacion')
router.register(r'history', LoanHistoryViewSet, basename='history')
router.register(r'academic/terms', TermViewSet, basename='term')
router.register(r'academic/subjects', SubjectViewSet, basename='subject')
router.register(r'academic/classgroups', ClassGroupViewSet, basename='classgroup')
router.register(r'academic/activities', ActivityViewSet, basename='activity')
router.register(r'academic/workteams', WorkTeamViewSet, basename='workteam')
router.register(r'academic/submissions', SubmissionViewSet, basename='submission')

urlpatterns = [
    # Panel de Administración de Django
    path('admin/', admin.site.urls), 

    # Endpoints de API
    path('api/', include(router.urls)), 
    
    # Perfil del usuario autenticado
    path('api/profile/', UserProfileView.as_view(), name='user-profile'),
    
    # Autenticación JWT
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Documentación con drf-spectacular
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)