from django.db.models.signals import post_save
from django.dispatch import receiver
from loans.models import MaterialLoan
from .services import sync_loan_history

@receiver(post_save, sender=MaterialLoan)
def create_or_update_loan_history(sender, instance, created, **kwargs):
    # Al autorizar se guarda el historial con los renglones del préstamo. Si el préstamo se crea
    # ya autorizado, sus renglones aún no existen aquí: la vista llama sync_loan_history después.
    sync_loan_history(instance)
