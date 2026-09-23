from django.conf import settings
from django.db import models


class Resource(models.Model):
    """Material de apoyo (archivos, guías) publicado por docentes o administradores."""
    title = models.CharField(max_length=200)
    description = models.TextField()
    file = models.FileField(upload_to='resources/', blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='resources'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
