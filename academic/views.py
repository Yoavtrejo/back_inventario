from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Avg
from .models import Term, Subject, ClassGroup, Activity, WorkTeam, Submission
from .serializers import (TermSerializer, SubjectSerializer, ClassGroupSerializer, 
                          ActivitySerializer, WorkTeamSerializer, SubmissionSerializer)
from core.json_api_mixin import WrappedStandardApiMixin

class IsTeacherOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and (request.user.is_staff or request.user.is_superuser)

class TermViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    queryset = Term.objects.all()
    serializer_class = TermSerializer
    permission_classes = [IsTeacherOrReadOnly]

class SubjectViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [IsTeacherOrReadOnly]

class ClassGroupViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    queryset = ClassGroup.objects.all()
    serializer_class = ClassGroupSerializer
    permission_classes = [IsTeacherOrReadOnly]
    
    @action(detail=True, methods=['post'], url_path='join')
    def join_group(self, request, pk=None):
        group = self.get_object()
        group.students.add(request.user)
        return Response({'detail': 'Te has unido al grupo exitosamente.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='grades/(?P<partial>[^/.]+)')
    def get_grades(self, request, pk=None, partial=None):
        """
        Calcula el promedio de un alumno en un parcial específico.
        """
        group = self.get_object()
        student_id = request.query_params.get('student_id')
        if not student_id:
            student_id = request.user.id
            
        # Calcular promedio de actividades individuales calificadas
        submissions = Submission.objects.filter(
            activity__group=group,
            activity__partial_period=partial,
            student_id=student_id,
            status='Calificado'
        ).aggregate(Avg('grade'))
        
        avg_grade = submissions['grade__avg']
        return Response({'student_id': student_id, 'partial': partial, 'average_grade': avg_grade})

class ActivityViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    queryset = Activity.objects.all()
    serializer_class = ActivitySerializer
    permission_classes = [IsTeacherOrReadOnly]

class WorkTeamViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    queryset = WorkTeam.objects.all()
    serializer_class = WorkTeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        team = serializer.save()
        if team.members.count() > 7:
            team.delete()
            raise serializers.ValidationError("Un equipo no puede tener más de 7 integrantes.")

class SubmissionViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    queryset = Submission.objects.all()
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(student=self.request.user)

