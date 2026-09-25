"""Registro del historial de préstamos autorizados."""

from .models import LoanHistory


def loan_items_snapshot(loan):
    return [
        {"material_name": item.material.name, "quantity": item.quantity}
        for item in loan.items.select_related('material').order_by('id')
    ]


def items_summary(items):
    """'2 × Cable Ethernet, 1 × Pinzas para ponchar'."""
    return ", ".join(f"{item['quantity']} × {item['material_name']}" for item in items)


def sync_loan_history(loan):
    """
    Crea el historial del préstamo al autorizarlo, o actualiza su fecha de devolución.
    No hace nada si el préstamo no está autorizado o aún no tiene renglones.
    """
    if not loan.approved_by_id:
        return None
    history = LoanHistory.objects.filter(original_loan_id=loan.id).first()
    if history:
        if history.return_date != loan.return_date:
            history.return_date = loan.return_date
            history.save(update_fields=['return_date'])
        return history

    items = loan_items_snapshot(loan)
    if not items:
        return None
    return LoanHistory.objects.create(
        original_loan_id=loan.id,
        items=items,
        material_name=items_summary(items),
        quantity=sum(item['quantity'] for item in items),
        requested_by_username=loan.requested_by.username if loan.requested_by_id else 'Desconocido',
        approved_by_username=loan.approved_by.username,
        loan_date=loan.loan_date,
        return_date=loan.return_date,
        loan_period_days=loan.loan_period_days,
    )
