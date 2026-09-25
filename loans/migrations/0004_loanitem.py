import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Paso 1: crea LoanItem y vuelve opcionales material/quantity del préstamo (para poder revertir)."""

    dependencies = [
        ('loans', '0003_materialloan_status'),
        ('materials', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoanItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('loan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='loans.materialloan')),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='loan_items', to='materials.material')),
            ],
            options={
                'ordering': ('id',),
                'unique_together': {('loan', 'material')},
            },
        ),
        migrations.AlterField(
            model_name='materialloan',
            name='material',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='loans', to='materials.material'),
        ),
        migrations.AlterField(
            model_name='materialloan',
            name='quantity',
            field=models.PositiveIntegerField(null=True),
        ),
    ]
