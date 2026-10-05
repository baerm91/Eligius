from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('slg', '0102_index_mtoa_nominal')]

    operations = [
        migrations.AddField(
            model_name='slg', name='kulturpool_export_erlaubt',
            field=models.BooleanField(default=False, verbose_name='Kulturpool-Export erlauben'),
        ),
        migrations.AddField(
            model_name='slg', name='kulturpool_metadata_rights_uri',
            field=models.URLField(blank=True, max_length=500, verbose_name='Kulturpool: Rechte-URI der Metadaten',
                                  help_text='Separat von den Bildrechten; nur nach Vereinbarung ausfüllen.'),
        ),
        migrations.AddField(
            model_name='slg', name='kulturpool_rights_uri',
            field=models.URLField(blank=True, max_length=500, verbose_name='Kulturpool: Rechte-URI der Bilder',
                                  help_text='Nur eine bestätigte HTTP(S)-Rechte-URI eintragen. Keine Lizenz wird vorausgesetzt.'),
        ),
        migrations.AddIndex(
            model_name='muenztypobjektanzeige',
            index=models.Index(fields=['last_modified', 'obj_id'], name='mtoa_oai_modified_obj_idx'),
        ),
    ]
