import uuid
from datetime import datetime, timedelta
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class Isla(models.Model):
    """
    Representa una isla de trabajo en el laboratorio.
    """
    ESTADO_CHOICES = [
        ('Disponible', 'Disponible'),
        ('Reservada', 'Reservada'),
    ]

    numero_isla = models.PositiveIntegerField(unique=True)
    equipos_computo = models.PositiveIntegerField()
    switches = models.PositiveIntegerField(default=0)
    routers = models.PositiveIntegerField(default=0)
    otros_componentes = models.JSONField(default=dict, blank=True)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='Disponible'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['numero_isla']

    def actualizar_estado(self):
        """
        Actualiza el estado de la isla basado en si tiene reservaciones activas.
        """
        reservaciones_model = self.reservaciones.model
        reservaciones_model.actualizar_reservaciones_expiradas()
        tiene_activas = self.reservaciones.filter(
            completada=False,
            cancelada=False
        ).exists()
        self.estado = 'Reservada' if tiene_activas else 'Disponible'
        Isla.objects.filter(id=self.id).update(estado=self.estado)

    def __str__(self):
        return f"Isla {self.numero_isla} ({self.estado})"


class Reservacion(models.Model):
    """
    Representa el préstamo o apartado de una isla por un alumno.
    """
    isla = models.ForeignKey(
        Isla,
        on_delete=models.CASCADE,
        related_name='reservaciones'
    )
    alumno = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservaciones'
    )
    fecha_reserva = models.DateField()
    hora_inicio = models.TimeField()
    duracion_horas = models.PositiveIntegerField(default=1)
    hora_escaneo_inicio = models.DateTimeField(null=True, blank=True)
    completada = models.BooleanField(default=False)
    cancelada = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_reserva', '-hora_inicio']

    def clean(self):
        super().clean()
        if self.duracion_horas > 4:
            raise ValidationError("La duración de la reservación no puede ser mayor a 4 horas.")
        if self.duracion_horas < 1:
            raise ValidationError("La duración de la reservación debe ser de al menos 1 hora.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.isla.actualizar_estado()

    def delete(self, *args, **kwargs):
        isla = self.isla
        super().delete(*args, **kwargs)
        isla.actualizar_estado()

    @classmethod
    def actualizar_reservaciones_expiradas(cls):
        """
        Cancela automáticamente las reservaciones que pasaron de su hora de inicio
        hace más de 10 minutos y no registraron escaneo de QR.
        """
        ahora = timezone.now()
        # Traer reservaciones que no se han escaneado, ni completado, ni cancelado
        reservas_pendientes = cls.objects.filter(
            hora_escaneo_inicio__isnull=True,
            completada=False,
            cancelada=False
        )
        for reserva in reservas_pendientes:
            inicio_reserva = timezone.make_aware(
                datetime.combine(reserva.fecha_reserva, reserva.hora_inicio),
                timezone.get_current_timezone()
            )
            if ahora > inicio_reserva + timedelta(minutes=10):
                reserva.cancelada = True
                reserva.save()

    def __str__(self):
        return f"Reserva Isla {self.isla.numero_isla} - {self.alumno.username} ({self.fecha_reserva})"
