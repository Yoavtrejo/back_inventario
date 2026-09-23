from django.conf import settings
from django.db import models


class Carrera(models.Model):
    nombre = models.CharField(max_length=150, unique=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class UserProfile(models.Model):
    """Datos del alumno. Los usuarios creados antes del registro público pueden no tener perfil."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    matricula = models.CharField(max_length=20, unique=True)
    carrera = models.ForeignKey(Carrera, on_delete=models.PROTECT, null=True, blank=True, related_name='alumnos')

    def __str__(self):
        return f"{self.matricula} - {self.user.get_full_name() or self.user.username}"
