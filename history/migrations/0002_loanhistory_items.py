from django.db import migrations, models


def fill_items(apps, schema_editor):
    LoanHistory = apps.get_model('history', 'LoanHistory')
    for history in LoanHistory.objects.all():
        history.items = [{"material_name": history.material_name, "quantity": history.quantity}]
        history.save(update_fields=['items'])


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='loanhistory',
            name='items',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='loanhistory',
            name='material_name',
            field=models.TextField(),
        ),
        migrations.RunPython(fill_items, migrations.RunPython.noop),
    ]
