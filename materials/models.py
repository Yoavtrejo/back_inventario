from django.db import models
from django.conf import settings

# Create your models here.


class Material(models.Model):
    STATUS_CHOICES = [
        ('Disponible', 'Disponible'),
        ('No disponible', 'No disponible'),
        ('Danado', 'Dañado'),
        ('En reparación', 'En reparación'),
        ('En préstamo', 'En préstamo'),
    ]

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=500, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    min_stock = models.PositiveIntegerField(default=1)
    max_stock = models.PositiveIntegerField(default=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Disponible')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)