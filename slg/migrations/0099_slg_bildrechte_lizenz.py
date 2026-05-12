from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slg', '0098_alter_fund_zusammen_gefundene_muenzen_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='slg',
            name='bildrechte_lizenz',
            field=models.TextField(blank=True, verbose_name='Copyrightlizenz der Bilder'),
        ),
    ]
