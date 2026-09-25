from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from core.files import ProtectedFilesMixin
from users.serializers import UserProfileInfoMixin
from .models import Term, Subject, ClassGroup, Activity, WorkTeam, Submission, CalendarEvent

User = get_user_model()

class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = ('id', 'name', 'description', 'start_date', 'end_date', 'is_active')
        # Sin el validador de unique_active_term: al activar uno, Term.save desactiva el anterior
        extra_kwargs = {'is_active': {'validators': []}}

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end <= start:
            raise serializers.ValidationError({'end_date': 'La fecha de fin debe ser posterior a la de inicio.'})
        return attrs

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = '__all__'

class GroupStudentSerializer(UserProfileInfoMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'email', 'matricula', 'carrera')

class ClassGroupSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source='term.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.username', read_only=True)
    students_detail = serializers.SerializerMethodField()

    class Meta:
        model = ClassGroup
        fields = ['id', 'name', 'term', 'term_name', 'subject', 'subject_name', 'teacher', 'teacher_name', 'students',
                  'students_detail']
        extra_kwargs = {
            'students': {'required': False}
        }

    @extend_schema_field(GroupStudentSerializer(many=True))
    def get_students_detail(self, obj):
        # Datos de los alumnos solo para el docente del grupo o un admin; vacío para alumnos
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not (user.is_superuser or obj.teacher_id == user.id):
            return []
        return GroupStudentSerializer(obj.students.all(), many=True).data

class ActivitySerializer(ProtectedFilesMixin, serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'

class WorkTeamSerializer(serializers.ModelSerializer):
    MAX_MEMBERS = 7

    class Meta:
        model = WorkTeam
        fields = '__all__'

    def validate(self, attrs):
        group = attrs.get('group') or self.instance.group
        if 'members' in attrs:
            members = attrs['members']
        else:
            members = list(self.instance.members.all())

        if len(members) > self.MAX_MEMBERS:
            raise serializers.ValidationError(
                {'members': f'Un equipo no puede tener más de {self.MAX_MEMBERS} integrantes.'}
            )

        member_ids = {member.id for member in members}
        enrolled_ids = set(group.students.filter(id__in=member_ids).values_list('id', flat=True))
        not_enrolled = sorted(m.username for m in members if m.id not in enrolled_ids)
        if not_enrolled:
            raise serializers.ValidationError(
                {'members': f'No están inscritos en el grupo: {", ".join(not_enrolled)}.'}
            )

        other_teams = WorkTeam.objects.filter(group=group)
        if self.instance:
            other_teams = other_teams.exclude(pk=self.instance.pk)
        already_in_team = sorted(
            User.objects.filter(id__in=member_ids, work_teams__in=other_teams)
            .values_list('username', flat=True).distinct()
        )
        if already_in_team:
            raise serializers.ValidationError(
                {'members': f'Ya pertenecen a otro equipo del grupo: {", ".join(already_in_team)}.'}
            )
        return attrs

class SubmissionSerializer(ProtectedFilesMixin, serializers.ModelSerializer):
    # Las entregas tardías se aceptan, solo se marcan
    is_late = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = '__all__'
        # grade y status solo los cambia el docente del grupo (SubmissionGradeSerializer)
        read_only_fields = ('student', 'status', 'grade', 'created_at', 'updated_at')

    def get_is_late(self, obj) -> bool:
        due_date = obj.activity.due_date
        return bool(due_date and obj.created_at and obj.created_at > due_date)

class SubmissionGradeSerializer(serializers.ModelSerializer):
    """Calificación de una entrega por el docente del grupo o un admin."""

    class Meta:
        model = Submission
        fields = ('grade', 'status')
        extra_kwargs = {
            'grade': {'min_value': 0, 'max_value': 10},
        }

class SubmissionFileSerializer(serializers.ModelSerializer):
    """Reemplazo del archivo de una entrega por el alumno."""

    class Meta:
        model = Submission
        fields = ('student_file',)
        extra_kwargs = {
            'student_file': {'required': True, 'allow_null': False},
        }


class CalendarEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarEvent
        fields = ('id', 'title', 'description', 'start_date', 'end_date', 'kind', 'term', 'created_at')
        read_only_fields = ('id', 'created_at')

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'La fecha de fin no puede ser anterior a la de inicio.'})
        return attrs
