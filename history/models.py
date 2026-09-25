from django.db import models

class LoanHistory(models.Model):
    original_loan_id = models.IntegerField(null=True, blank=True)
    # Resumen legible de los materiales ("2 × Cable, 1 × Pinzas") y total de unidades
    material_name = models.TextField()
    quantity = models.PositiveIntegerField()
    # Detalle por material: [{"material_name": str, "quantity": int}]
    items = models.JSONField(default=list, blank=True)
    requested_by_username = models.CharField(max_length=150)
    approved_by_username = models.CharField(max_length=150)
    approval_date = models.DateTimeField(auto_now_add=True)
    loan_date = models.DateField()
    return_date = models.DateField(blank=True, null=True)
    loan_period_days = models.PositiveIntegerField()
    
    class Meta:
        ordering = ['-approval_date']

    def __str__(self):
        return f"History: {self.material_name} - {self.requested_by_username} (Aprobado por {self.approved_by_username})"
