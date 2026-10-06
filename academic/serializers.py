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
        fields = ('id', 'username', 'first_name', 'last_name', 'email', 'matricula', 'carrera',
                  'cuatrimestre', 'grupo', 'grupo_escolar')

class ClassGroupSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source='term.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.username', read_only=True)
    carrera_clave = serializers.CharField(source='carrera.clave', read_only=True, default=None)
    students_count = serializers.SerializerMethodField()
    students_detail = serializers.SerializerMethodField()

    COHORT_FIELDS = ('carrera', 'cuatrimestre', 'grupo')

    class Meta:
        model = ClassGroup
        fields = ['id', 'name', 'term', 'term_name', 'subject', 'subject_name', 'teacher', 'teacher_name',
                  'carrera', 'carrera_clave', 'cuatrimestre', 'grupo', 'students', 'students_count',
                  'students_detail']
        extra_kwargs = {
            'students': {'required': False},
            # Con carrera, cuatrimestre y grupo el name se arma solo; term por defecto = term activo
            'name': {'required': False},
            'term': {'required': False},
            'teacher': {'required': False},
        }
        # unique_together (name, term, subject) se valida en validate() con el name ya armado
        validators = []

    def validate(self, attrs):
        instance = self.instance
        cohort = {
            field: attrs[field] if field in attrs else getattr(instance, field, None)
            for field in self.COHORT_FIELDS
        }
        provided = [value is not None for value in cohort.values()]
        if any(provided) and not all(provided):
            raise serializers.ValidationError('Indica carrera, cuatrimestre y grupo juntos.')
        if all(provided):
            carrera = cohort['carrera']
            if not carrera.clave:
                raise serializers.ValidationError(
                    f'La carrera {carrera.nombre} no tiene clave; pídele al administrador que la registre.'
                )
            attrs['name'] = f"{carrera.clave}{cohort['cuatrimestre']}{cohort['grupo']}"
        elif not (attrs.get('name') or getattr(instance, 'name', None)):
            raise serializers.ValidationError({'name': 'Indica el nombre o carrera, cuatrimestre y grupo.'})

        if instance is None and 'term' not in attrs:
            term = Term.objects.filter(is_active=True).first()
            if term is None:
                raise serializers.ValidationError({'term': 'No hay un cuatrimestre activo; indica term.'})
            attrs['term'] = term

        name = attrs.get('name', getattr(instance, 'name', None))
        term = attrs.get('term', getattr(instance, 'term', None))
        subject = attrs.get('subject', getattr(instance, 'subject', None))
        duplicates = ClassGroup.objects.filter(name=name, term=term, subject=subject)
        if instance is not None:
            duplicates = duplicates.exclude(pk=instance.pk)
        if subject is not None and duplicates.exists():
            raise serializers.ValidationError(f'Ya existe el grupo {name} de {subject.name} en {term.name}.')
        return attrs

    def get_students_count(self, obj) -> int:
        return len(obj.students.all())

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
