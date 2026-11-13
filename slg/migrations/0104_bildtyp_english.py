from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('slg', '0103_kulturpool_oai')]
    operations = [
        migrations.AddField(model_name=model, name='name_en',
            field=models.CharField(max_length=500, blank=True, default='', verbose_name='Englische Übersetzung'))
        for model in ('avbildtyp', 'rvbildtyp')
    ]
