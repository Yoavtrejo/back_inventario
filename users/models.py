from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def normalizar_clave(clave):
    """'isc ' -> 'ISC'; vacía -> None."""
    if clave is None:
        return None
    clave = ''.join(str(clave).split()).upper()
    return clave or None


class Carrera(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    # Clave para el nombre de los grupos escolares, ej. ISC -> ISC34
    clave = models.CharField(max_length=10, unique=True, null=True, blank=True)

    class Meta:
        ordering = ['nombre']

    def save(self, *args, **kwargs):
        self.clave = normalizar_clave(self.clave)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class UserProfile(models.Model):
    """Datos del alumno. Los usuarios creados antes del registro público pueden no tener perfil."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    matricula = models.CharField(max_length=20, unique=True)
    carrera = models.ForeignKey(Carrera, on_delete=models.PROTECT, null=True, blank=True, related_name='alumnos')
    # Grupo escolar: carrera + cuatrimestre (1-9) + grupo (1-6), ej. ISC34
    cuatrimestre = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(9)]
    )
    grupo = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(6)]
    )

    @property
    def cohorte(self):
        """(carrera_id, cuatrimestre, grupo) o None si falta algún dato."""
        if self.carrera_id and self.cuatrimestre and self.grupo:
            return (self.carrera_id, self.cuatrimestre, self.grupo)
        return None

    def __str__(self):
        return f"{self.matricula} - {self.user.get_full_name() or self.user.username}"
