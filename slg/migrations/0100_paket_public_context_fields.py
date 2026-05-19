from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slg', '0099_slg_bildrechte_lizenz'),
    ]

    operations = [
        migrations.AddField(
            model_name='paket',
            name='bekannte_objektanzahl',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Bekannte Anzahl der Objekte'),
        ),
        migrations.AddField(
            model_name='paket',
            name='darstellungsart',
            field=models.CharField(choices=[('frontcover', 'Frontcover'), ('karte', 'Karte'), ('objekt', 'Objekt'), ('diagramm', 'Diagramm')], default='objekt', max_length=20, verbose_name='Darstellungsart'),
        ),
        migrations.AddField(
            model_name='paket',
            name='frontcover',
            field=models.FileField(blank=True, null=True, upload_to='pakete/frontcover/', verbose_name='Frontcover'),
        ),
        migrations.AddField(
            model_name='paket',
            name='fund_lat',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='Fundkoordinate Breite'),
        ),
        migrations.AddField(
            model_name='paket',
            name='fund_lng',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name='Fundkoordinate Länge'),
        ),
        migrations.AddField(
            model_name='paket',
            name='fundplatz_kontext',
            field=models.CharField(blank=True, choices=[('canabae', 'Canabae'), ('amphitheater', 'Amphitheater')], max_length=20, verbose_name='Fundplatz Kontext'),
        ),
        migrations.AddField(
            model_name='paket',
            name='fundzeitpunkt_verbal',
            field=models.CharField(blank=True, max_length=200, verbose_name='Fundzeitpunkt (verbal)'),
        ),
        migrations.AddField(
            model_name='paket',
            name='kontexttyp',
            field=models.CharField(blank=True, choices=[('hortfund', 'Hortfund'), ('fundkontext', 'Fundkontext'), ('grabung', 'Grabung'), ('thema', 'Thema')], max_length=20, verbose_name='Kontexttyp'),
        ),
        migrations.AddField(
            model_name='paket',
            name='literatur',
            field=models.ManyToManyField(blank=True, to='slg.ref', verbose_name='Literatur'),
        ),
        migrations.AddField(
            model_name='paket',
            name='titel_oeffentlich',
            field=models.CharField(blank=True, max_length=200, verbose_name='Titel öffentlich'),
        ),
        migrations.AddField(
            model_name='paket',
            name='vergleichspakete',
            field=models.ManyToManyField(blank=True, related_name='vergleichende_pakete', symmetrical=False, to='slg.paket', verbose_name='Vergleichsdiagramme mit Paketen'),
        ),
    ]
