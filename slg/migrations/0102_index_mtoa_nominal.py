from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slg', '0101_slg_nomisma_export'),
    ]

    operations = [
        migrations.AlterField(
            model_name='muenztypobjektanzeige',
            name='nominal',
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True, verbose_name='Nominal'),
        ),
    ]
