from rest_framework import serializers
from .models import Term, Subject, ClassGroup, Activity, WorkTeam, Submission

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
    class Meta:
        model = WorkTeam
        fields = '__all__'

class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = '__all__'
