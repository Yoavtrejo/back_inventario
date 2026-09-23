from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Term, Subject, ClassGroup, Activity, WorkTeam, Submission

User = get_user_model()

class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = '__all__'

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = '__all__'

class ClassGroupSerializer(serializers.ModelSerializer):
    term_name = serializers.CharField(source='term.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.username', read_only=True)

    class Meta:
        model = ClassGroup
        fields = ['id', 'name', 'term', 'term_name', 'subject', 'subject_name', 'teacher', 'teacher_name', 'students']
        extra_kwargs = {
            'students': {'required': False}
        }

class ActivitySerializer(serializers.ModelSerializer):
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

class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = '__all__'
        # grade y status solo los cambia el docente del grupo (SubmissionGradeSerializer)
        read_only_fields = ('student', 'status', 'grade', 'created_at', 'updated_at')

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
