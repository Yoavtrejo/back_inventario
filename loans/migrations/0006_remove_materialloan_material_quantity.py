from django.db import migrations


class Migration(migrations.Migration):
    """Paso 3: quita material y quantity del préstamo (ahora viven en LoanItem)."""

    dependencies = [
        ('loans', '0005_loanitem_data'),
    ]

    operations = [
        migrations.RemoveField(model_name='materialloan', name='material'),
        migrations.RemoveField(model_name='materialloan', name='quantity'),
    ]
