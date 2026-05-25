from django.conf import settings
from django.db import models

class MaterialLoan(models.Model):
    """
    Tracks a material loan from request through optional approval and return.

    - Any authenticated user may create a request (requested_by is enforced server-side).
    - Only a superuser may set ``approved_by`` (authorization).
    """
    material = models.ForeignKey(
        'materials.Material',
        on_delete=models.PROTECT,
        related_name="loans",
    )
    quantity = models.PositiveIntegerField()
    loan_period_days = models.PositiveIntegerField()
    loan_date = models.DateField()
    return_date = models.DateField(blank=True, null=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="material_loans_requested",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="material_loans_approved",
        blank=True,
        null=True,
    )
    has_condition_report = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-loan_date", "-id")

    def __str__(self) -> str:
        return f"{self.material.name if self.material else 'Unnamed'} ({self.quantity}) — {self.loan_date}"

class ConditionReport(models.Model):
    """Reporte de condición asociado a un préstamo de material.

    Cada préstamo puede tener un único reporte que incluye una descripción opcional
    y una foto que muestra el estado del material (daños, defectos, etc.).
    """
    loan = models.OneToOneField(
        MaterialLoan,
        on_delete=models.CASCADE,
        related_name="condition_report",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="condition_reports",
    )
    description = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='condition_reports/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Reporte de condición para préstamo {self.loan.id}"
