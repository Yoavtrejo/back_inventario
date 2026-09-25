from django.contrib import admin  # <--- No olvides este import
from django.urls import path, include
from core.files import protected_file
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from users.views import (UserViewSet, UserProfileView, RegisterView, CarreraViewSet,
                         PasswordResetRequestView, PasswordResetConfirmView, LoginView, LogoutView)
from loans.views import MaterialLoanViewSet,ConditionReportListCreateView
from materials.views import MaterialViewSet
from isla_control.views import IslaViewSet, ReservacionViewSet, HorarioBloqueadoViewSet
from history.views import LoanHistoryViewSet
from resources.views import ResourceViewSet
from academic.views import (CalendarEventViewSet, TermViewSet, SubjectViewSet, ClassGroupViewSet, 
                            ActivityViewSet, WorkTeamViewSet, SubmissionViewSet)


router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'carreras', CarreraViewSet, basename='carrera')
router.register(r'material-loans', MaterialLoanViewSet, basename='material-loan')
router.register(r'materials', MaterialViewSet, basename='material')
router.register(r'islas', IslaViewSet, basename='isla')
router.register(r'reservaciones', ReservacionViewSet, basename='reservacion')
router.register(r'history', LoanHistoryViewSet, basename='history')
router.register(r'academic/terms', TermViewSet, basename='term')
router.register(r'calendar-events', CalendarEventViewSet, basename='calendar-event')
router.register(r'academic/subjects', SubjectViewSet, basename='subject')
router.register(r'academic/classgroups', ClassGroupViewSet, basename='classgroup')
router.register(r'academic/activities', ActivityViewSet, basename='activity')
router.register(r'academic/workteams', WorkTeamViewSet, basename='workteam')
router.register(r'academic/submissions', SubmissionViewSet, basename='submission')
router.register(r'resources', ResourceViewSet, basename='resource')
router.register(r'horarios-bloqueados', HorarioBloqueadoViewSet, basename='horario-bloqueado')

urlpatterns = [
    # Panel de Administración de Django
    path('admin/', admin.site.urls), 

    # Endpoints de API
    path('api/material-loans/condition-reports/', ConditionReportListCreateView.as_view(), name='condition-reports-list'),
    path('api/', include(router.urls)), 
    
    # Perfil del usuario autenticado
    path('api/profile/', UserProfileView.as_view(), name='user-profile'),
    path('api/register/', RegisterView.as_view(), name='register'),
    path('api/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('api/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    
    # Autenticación JWT
    path('api/token/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/logout/', LogoutView.as_view(), name='logout'),
    
    # Documentación con drf-spectacular
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Descarga de archivos subidos con enlace firmado (MEDIA_ROOT no se sirve públicamente)
    path('api/files/<str:token>/<str:filename>', protected_file, name='protected-file'),
]