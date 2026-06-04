from django.db import models

class LoanHistory(models.Model):
    original_loan_id = models.IntegerField(null=True, blank=True)
    material_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
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
