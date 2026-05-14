"""
Domain models for material loans (laboratory equipment / consumables).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class MaterialLoan(models.Model):
    """
    Tracks a material loan from request through optional approval and return.

    - Any authenticated user may create a request (requested_by is enforced server-side).
    - Only a superuser may set ``approved_by`` (authorization).
    """

    material_name = models.CharField(max_length=255)
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-loan_date", "-id")

    def __str__(self) -> str:
        return f"{self.material_name} ({self.quantity}) — {self.loan_date}"
