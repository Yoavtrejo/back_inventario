from django.db.models import Avg, Q
from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .models import Term, Subject, ClassGroup, Activity, WorkTeam, Submission
from .serializers import (TermSerializer, SubjectSerializer, ClassGroupSerializer,
                          ActivitySerializer, WorkTeamSerializer, SubmissionSerializer,
                          SubmissionGradeSerializer, SubmissionFileSerializer)
from core.json_api_mixin import WrappedStandardApiMixin

# Roles: admin = is_superuser, docente = is_staff, alumno = ninguno de los dos.

def is_alumno(user):
    return not (user.is_staff or user.is_superuser)

def visible_groups(user, queryset=None):
    """Grupos que el usuario puede ver: admin todos, docente los suyos, alumno donde está inscrito."""
    queryset = ClassGroup.objects.all() if queryset is None else queryset
    if user.is_superuser:
        return queryset
    if user.is_staff:
        return queryset.filter(teacher=user)
    return queryset.filter(students=user)

def can_manage_group(user, group):
    return user.is_superuser or group.teacher_id == user.id

def check_can_manage_group(user, group):
    if not can_manage_group(user, group):
        raise PermissionDenied('Solo el docente del grupo o un administrador puede realizar esta acción.')

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
    """
    - Admin: todos los grupos. Docente: los que imparte. Alumno: en los que está inscrito.
    - ?disponibles=true (alumno): grupos en los que aún no está inscrito, para unirse.
    - Crear: docente (queda como teacher) o admin. Editar/borrar: el teacher del grupo o un admin.
    """
    serializer_class = ClassGroupSerializer
    permission_classes = [IsTeacherOrReadOnly]

    def get_permissions(self):
        if self.action == 'join_group':
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ClassGroup.objects.none()
        user = self.request.user
        queryset = ClassGroup.objects.select_related('term', 'subject', 'teacher').prefetch_related('students')
        if self.action == 'join_group':
            return queryset
        disponibles = self.request.query_params.get('disponibles', '').lower() in ('1', 'true')
        if self.action == 'list' and disponibles and is_alumno(user):
            return queryset.exclude(students=user)
        return visible_groups(user, queryset)

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_superuser:
            serializer.save()
        else:
            serializer.save(teacher=user)

    def perform_update(self, serializer):
        user = self.request.user
        check_can_manage_group(user, serializer.instance)
        if user.is_superuser:
            serializer.save()
        else:
            serializer.save(teacher=serializer.instance.teacher)

    def perform_destroy(self, instance):
        check_can_manage_group(self.request.user, instance)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='join')
    def join_group(self, request, pk=None):
        if not is_alumno(request.user):
            raise PermissionDenied('Solo los alumnos pueden unirse a un grupo.')
        group = self.get_object()
        group.students.add(request.user)
        return Response({'detail': 'Te has unido al grupo exitosamente.'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='grades/(?P<partial>[^/.]+)')
    def get_grades(self, request, pk=None, partial=None):
        """
        Calcula el promedio de un alumno en un parcial específico.
        El alumno solo puede consultar su propio promedio.
        """
        group = self.get_object()
        student_id = request.query_params.get('student_id') or request.user.id
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            raise serializers.ValidationError({'student_id': 'Debe ser un número.'})
        if is_alumno(request.user) and student_id != request.user.id:
            raise PermissionDenied('Solo puedes consultar tus propias calificaciones.')

        # Entregas calificadas del alumno: individuales o de alguno de sus equipos
        submission_ids = Submission.objects.filter(
            Q(student_id=student_id) | Q(work_team__members=student_id),
            activity__group=group,
            activity__partial_period=partial,
            status='Calificado',
        ).values('id')
        submissions = Submission.objects.filter(id__in=submission_ids).aggregate(Avg('grade'))

        avg_grade = submissions['grade__avg']
        return Response({'student_id': student_id, 'partial': partial, 'average_grade': avg_grade})

class ActivityViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """Actividades de los grupos visibles. Escritura: el teacher del grupo o un admin."""
    serializer_class = ActivitySerializer
    permission_classes = [IsTeacherOrReadOnly]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Activity.objects.none()
        return Activity.objects.select_related('group').filter(
            group__in=visible_groups(self.request.user)
        )

    def perform_create(self, serializer):
        check_can_manage_group(self.request.user, serializer.validated_data['group'])
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        check_can_manage_group(user, serializer.instance.group)
        if 'group' in serializer.validated_data:
            check_can_manage_group(user, serializer.validated_data['group'])
        serializer.save()

    def perform_destroy(self, instance):
        check_can_manage_group(self.request.user, instance.group)
        instance.delete()

class WorkTeamViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """
    - Admin: todos. Docente: equipos de sus grupos. Alumno: solo sus equipos.
    - Escritura: el teacher del grupo o un admin.
    """
    serializer_class = WorkTeamSerializer
    permission_classes = [IsTeacherOrReadOnly]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return WorkTeam.objects.none()
        user = self.request.user
        queryset = WorkTeam.objects.select_related('group').prefetch_related('members')
        if user.is_superuser:
            return queryset
        if user.is_staff:
            return queryset.filter(group__teacher=user)
        return queryset.filter(members=user)

    def perform_create(self, serializer):
        check_can_manage_group(self.request.user, serializer.validated_data['group'])
        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        check_can_manage_group(user, serializer.instance.group)
        if 'group' in serializer.validated_data:
            check_can_manage_group(user, serializer.validated_data['group'])
        serializer.save()

    def perform_destroy(self, instance):
        check_can_manage_group(self.request.user, instance.group)
        instance.delete()

class SubmissionViewSet(WrappedStandardApiMixin, viewsets.ModelViewSet):
    """
    - Admin: todas. Docente: entregas de sus grupos. Alumno: las suyas y las de sus equipos.
    - Crear: alumno inscrito en el grupo; en actividades por equipo, con un equipo al que pertenezca.
      Una entrega por alumno (o por equipo) por actividad.
    - Editar: el docente del grupo o un admin califican (grade 0-10, status); el alumno solo
      reemplaza student_file mientras no esté calificada, y la entrega regresa a 'Entregado'.
    - Borrar: el docente del grupo o un admin.
    """
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Submission.objects.none()
        user = self.request.user
        queryset = Submission.objects.select_related('activity__group', 'student', 'work_team')
        if user.is_superuser:
            return queryset
        if user.is_staff:
            return queryset.filter(activity__group__teacher=user)
        return queryset.filter(Q(student=user) | Q(work_team__members=user)).distinct()

    def perform_create(self, serializer):
        user = self.request.user
        if not is_alumno(user):
            raise PermissionDenied('Solo los alumnos pueden entregar actividades.')

        activity = serializer.validated_data['activity']
        group = activity.group
        if not group.students.filter(pk=user.pk).exists():
            raise PermissionDenied('No estás inscrito en el grupo de esta actividad.')

        work_team = serializer.validated_data.get('work_team')
        if activity.is_team_activity:
            if work_team is None:
                raise serializers.ValidationError({'work_team': 'Esta actividad es por equipo: indica tu equipo.'})
            if work_team.group_id != group.id or not work_team.members.filter(pk=user.pk).exists():
                raise serializers.ValidationError({'work_team': 'No perteneces a ese equipo de este grupo.'})
            if Submission.objects.filter(activity=activity, work_team=work_team).exists():
                raise serializers.ValidationError({'activity': 'Tu equipo ya entregó esta actividad.'})
        else:
            work_team = None
            if Submission.objects.filter(activity=activity, student=user, work_team__isnull=True).exists():
                raise serializers.ValidationError({'activity': 'Ya entregaste esta actividad.'})

        serializer.save(student=user, work_team=work_team)

    def update(self, request, *args, **kwargs):
        kwargs.pop('partial', None)
        instance = self.get_object()
        user = request.user

        if can_manage_group(user, instance.activity.group):
            data = {key: request.data[key] for key in ('grade', 'status') if key in request.data}
            serializer = SubmissionGradeSerializer(instance, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        elif self._is_owner(user, instance):
            if 'grade' in request.data or 'status' in request.data:
                raise PermissionDenied('Solo el docente del grupo puede calificar la entrega.')
            if instance.status == 'Calificado':
                raise PermissionDenied('La entrega ya fue calificada y no puede modificarse.')
            serializer = SubmissionFileSerializer(
                instance, data={'student_file': request.data.get('student_file')}, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save(status='Entregado')
        else:
            raise PermissionDenied('No tienes permiso para modificar esta entrega.')

        instance.refresh_from_db()
        return Response(SubmissionSerializer(instance, context=self.get_serializer_context()).data)

    def perform_destroy(self, instance):
        check_can_manage_group(self.request.user, instance.activity.group)
        instance.delete()

    @staticmethod
    def _is_owner(user, submission):
        if submission.student_id == user.id:
            return True
        return bool(submission.work_team_id) and submission.work_team.members.filter(pk=user.pk).exists()
