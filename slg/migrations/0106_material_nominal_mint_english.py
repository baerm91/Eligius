from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('slg', '0105_vocabulary_english')]
    operations = [
        migrations.AddField(model_name=model, name='name_en',
            field=models.CharField(max_length=200, blank=True, default='', verbose_name='Englische Übersetzung'))
        for model in ('metall', 'nominal', 'mzstaette')
    ]
