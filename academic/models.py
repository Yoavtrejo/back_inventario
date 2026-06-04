from django.db import models
from django.conf import settings

class Term(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

class ClassGroup(models.Model):
    name = models.CharField(max_length=100) # ej: "Grupo A", "3A"
    term = models.ForeignKey(Term, on_delete=models.PROTECT)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='taught_groups', limit_choices_to={'is_staff': True})
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='enrolled_groups', blank=True)
    
    class Meta:
        unique_together = ('name', 'term', 'subject')
        
    def __str__(self):
        return f"{self.name} - {self.subject.name} ({self.term.name})"

class Activity(models.Model):
    group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name='activities')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    partial_period = models.PositiveIntegerField(help_text="Número de parcial, ej. 1, 2, 3")
    teacher_file = models.FileField(upload_to='activities_teacher/', blank=True, null=True)
    is_team_activity = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.title} (Parcial {self.partial_period}) - {self.group.name}"

class WorkTeam(models.Model):
    group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=100)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='work_teams')
    
    def __str__(self):
        return f"{self.name} - {self.group.name}"

class Submission(models.Model):
    STATUS_CHOICES = [
        ('Entregado', 'Entregado'),
        ('En revisión', 'En revisión'),
        ('Calificado', 'Calificado'),
    ]
    
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='submissions')
    work_team = models.ForeignKey(WorkTeam, on_delete=models.CASCADE, null=True, blank=True, related_name='submissions')
    student_file = models.FileField(upload_to='submissions_student/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Entregado')
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        submitter = self.student.username if self.student else self.work_team.name if self.work_team else "Unknown"
        return f"Entrega: {submitter} -> {self.activity.title} ({self.status})"

