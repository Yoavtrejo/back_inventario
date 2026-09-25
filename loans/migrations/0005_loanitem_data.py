from django.db import migrations


def loans_to_items(apps, schema_editor):
    """Cada préstamo existente queda con un renglón (su material y cantidad)."""
    MaterialLoan = apps.get_model('loans', 'MaterialLoan')
    LoanItem = apps.get_model('loans', 'LoanItem')
    LoanItem.objects.bulk_create(
        LoanItem(loan_id=loan.id, material_id=loan.material_id, quantity=loan.quantity)
        for loan in MaterialLoan.objects.exclude(material=None)
    )


def items_to_loans(apps, schema_editor):
    """Reversa: el préstamo toma el primer renglón. Los préstamos con varios renglones pierden los demás."""
    MaterialLoan = apps.get_model('loans', 'MaterialLoan')
    LoanItem = apps.get_model('loans', 'LoanItem')
    for loan in MaterialLoan.objects.all():
        item = LoanItem.objects.filter(loan_id=loan.id).order_by('id').first()
        if item:
            loan.material_id = item.material_id
            loan.quantity = item.quantity
            loan.save(update_fields=['material', 'quantity'])


class Migration(migrations.Migration):
    """Paso 2: migra los datos de material/quantity a LoanItem."""

    dependencies = [
        ('loans', '0004_loanitem'),
    ]

    operations = [
        migrations.RunPython(loans_to_items, items_to_loans),
    ]
