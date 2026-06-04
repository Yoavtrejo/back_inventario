from django.db.models.signals import post_save
from django.dispatch import receiver
from loans.models import MaterialLoan
from .models import LoanHistory
from django.utils import timezone

@receiver(post_save, sender=MaterialLoan)
def create_or_update_loan_history(sender, instance, created, **kwargs):
    # Solo nos interesa guardar en el historial cuando hay un `approved_by`
    if instance.approved_by:
        # Intentamos obtener un historial existente para este préstamo
        history_entry, created = LoanHistory.objects.get_or_create(
            original_loan_id=instance.id,
            defaults={
                'material_name': instance.material.name if instance.material else 'Desconocido',
                'quantity': instance.quantity,
                'requested_by_username': instance.requested_by.username if instance.requested_by else 'Desconocido',
                'approved_by_username': instance.approved_by.username if instance.approved_by else 'Desconocido',
                'loan_date': instance.loan_date,
                'return_date': instance.return_date,
                'loan_period_days': instance.loan_period_days,
            }
        )
        
        # Si ya existía, actualizamos sus campos en caso de que haya cambios (ej. return_date)
        if not created:
            history_entry.return_date = instance.return_date
            history_entry.save()
