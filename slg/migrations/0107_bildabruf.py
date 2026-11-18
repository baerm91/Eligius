import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('slg', '0106_material_nominal_mint_english')]
    operations = [
        migrations.CreateModel(
            name='Bildabruf',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('herkunft', models.CharField(blank=True, default='', help_text='Domain der Seite, die das Bild angezeigt hat; leer = unbekannt/direkt', max_length=100, verbose_name='Herkunft')),
                ('ansicht', models.CharField(choices=[('av', 'Vorderseite'), ('rv', 'Rückseite'), ('av-vorschau', 'Vorschau Vorderseite'), ('rv-vorschau', 'Vorschau Rückseite')], max_length=20, verbose_name='Ansicht')),
                ('datum', models.DateField(verbose_name='Datum')),
                ('automatisiert', models.BooleanField(default=False, help_text='Harvester, Crawler und Bildverarbeitung (nach User-Agent erkannt)', verbose_name='Automatisierter Abruf')),
                ('anzahl', models.PositiveIntegerField(default=0, verbose_name='Abrufe')),
                ('obj', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='slg.obj', verbose_name='Objekt')),
            ],
            options={
                'verbose_name': 'Bildabruf',
                'verbose_name_plural': 'Bildabrufe (Weiterleitung)',
                'indexes': [models.Index(fields=['datum', 'herkunft'], name='bildabruf_datum_herkunft')],
                'constraints': [models.UniqueConstraint(fields=('obj', 'ansicht', 'datum', 'herkunft', 'automatisiert'), name='bildabruf_tag_unique')],
            },
        ),
    ]
