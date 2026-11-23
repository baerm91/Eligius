import json
from datetime import datetime, timezone

from django.apps import apps
from django.core.management.base import BaseCommand

from slg.services.identifier_enrichment import INVENTORY_SCHEMA, TARGETS


class Command(BaseCommand):
    help = ('Exportiert Münzstätten und Personen mit Nomisma-ID sowie GeoNames/GND/VIAF lesend als JSON '
            '(Grundlage für build_identifier_proposals.py); keine Schreibzugriffe.')

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        records = []
        for label, targets in TARGETS.items():
            model = apps.get_model(label)
            columns = ['pk', 'name', 'name_nom_id', *targets]
            for row in model.objects.using(options['database']).order_by('pk').values(*columns).iterator(chunk_size=1000):
                records.append({'model': label, 'id': row['pk'], 'label': row['name'] or '',
                                'name_nom_id': row['name_nom_id'] or '',
                                **{field: row[field] or '' for field in targets}})
        self.stdout.write(json.dumps({
            'schema': INVENTORY_SCHEMA, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'database_alias': options['database'], 'records': records,
        }, ensure_ascii=False, indent=1))
