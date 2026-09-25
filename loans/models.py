from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

class MaterialLoan(models.Model):
    """
    Tracks a material loan from request through optional approval and return.

    - Any authenticated user may create a request (requested_by is enforced server-side).
    - Only a superuser may set ``approved_by`` (authorization).

    Flujo de estados y stock:
    Pendiente (descuenta stock) -> Autorizado -> Finalizado (devuelve stock)
    Pendiente -> Rechazado | Cancelado (devuelven stock)
    """

    class Status(models.TextChoices):
        PENDIENTE = 'Pendiente', 'Pendiente'
        AUTORIZADO = 'Autorizado', 'Autorizado'
        FINALIZADO = 'Finalizado', 'Finalizado'
        RECHAZADO = 'Rechazado', 'Rechazado'
        CANCELADO = 'Cancelado', 'Cancelado'

    # Estados en los que el material sigue descontado del stock
    ACTIVE_STATUSES = (Status.PENDIENTE, Status.AUTORIZADO)

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
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDIENTE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-loan_date", "-id")

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    def save(self, *args, **kwargs):
        # Mientras está activo, el estado refleja si ya fue autorizado
        if self.is_active:
            self.status = self.Status.AUTORIZADO if self.approved_by_id else self.Status.PENDIENTE
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Préstamo {self.pk} — {self.loan_date}"


class LoanItem(models.Model):
    """Renglón de un préstamo: un material y la cantidad solicitada."""
    loan = models.ForeignKey(MaterialLoan, on_delete=models.CASCADE, related_name="items")
    material = models.ForeignKey('materials.Material', on_delete=models.PROTECT, related_name="loan_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        unique_together = ("loan", "material")
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.quantity} × {self.material.name}"

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
    photo = models.ImageField(upload_to='condition_reports/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Reporte de condición para préstamo {self.loan.id}"
