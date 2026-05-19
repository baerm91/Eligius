from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slg', '0100_paket_public_context_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='slg',
            name='nomisma_export_erlaubt',
            field=models.BooleanField(default=False, verbose_name='Nomisma-Export erlauben'),
        ),
        migrations.AddField(
            model_name='slg',
            name='nomisma_collection_uri',
            field=models.URLField(blank=True, max_length=250, verbose_name='Nomisma Collection URI'),
        ),
    ]
