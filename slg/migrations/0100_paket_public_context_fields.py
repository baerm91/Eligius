from django.db import migrations, models
from django.utils.text import slugify


def populate_paket_slugs(apps, schema_editor):
    Paket = apps.get_model('slg', 'Paket')
    used_slugs = set(Paket.objects.exclude(slug__isnull=True).exclude(slug='').values_list('slug', flat=True))

    for paket in Paket.objects.all().order_by('id'):
        base_slug = slugify(paket.titel_oeffentlich or paket.name) or 'paket'
        slug = base_slug[:220]
        counter = 2
        while slug in used_slugs:
            suffix = f'-{counter}'
            slug = f'{base_slug[:220 - len(suffix)]}{suffix}'
            counter += 1
        paket.slug = slug
        paket.save(update_fields=['slug'])


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
            field=models.CharField(choices=[('frontcover', 'Frontcover'), ('karte', 'Karte'), ('objekt', 'Objekt'), ('diagramm', 'Diagramm')], default='objekt', help_text='Legt fest, ob auf der Startseite Frontcover, Karte, Objektthumbnails oder Diagramm gezeigt werden.', max_length=20, verbose_name='Startseiten-Darstellung'),
        ),
        migrations.AddField(
            model_name='paket',
            name='frontcover',
            field=models.FileField(blank=True, null=True, upload_to='pakete/frontcover/', verbose_name='Frontcover'),
        ),
        migrations.AddField(
            model_name='paket',
            name='fund_lat',
            field=models.DecimalField(blank=True, decimal_places=6, help_text='Dezimalgrad in WGS84, z. B. 48.116000', max_digits=9, null=True, verbose_name='Fundkoordinate Breite'),
        ),
        migrations.AddField(
            model_name='paket',
            name='fund_lng',
            field=models.DecimalField(blank=True, decimal_places=6, help_text='Dezimalgrad in WGS84, z. B. 16.867000', max_digits=9, null=True, verbose_name='Fundkoordinate Länge'),
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
            name='slug',
            field=models.SlugField(blank=True, max_length=220, null=True, unique=True, verbose_name='Slug'),
        ),
        migrations.RunPython(populate_paket_slugs, migrations.RunPython.noop),
        migrations.AddField(
            model_name='paket',
            name='vergleichspakete',
            field=models.ManyToManyField(blank=True, related_name='vergleichende_pakete', symmetrical=False, to='slg.paket', verbose_name='Vergleichsdiagramme mit Paketen'),
        ),
    ]
