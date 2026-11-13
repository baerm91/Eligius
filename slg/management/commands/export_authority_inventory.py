import json
from datetime import datetime, timezone

from django.apps import apps
from django.core.management.base import BaseCommand

from slg.services.authority_inventory import inventory


class Command(BaseCommand):
    help = 'Exportiert Normdatenverweise lesend als JSON; keine Netzwerkaufrufe oder DB-Schreibzugriffe.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        records, coverage = [], []
        for model in apps.get_app_config('slg').get_models():
            fields = {f.name for f in model._meta.concrete_fields}
            authority_fields = sorted(fields & {
                'name_nom_id', 'DNB', 'WikiDe', 'WikiEn', 'nomisma_collection_uri', 'uri_reference',
            })
            if not authority_fields:
                continue
            label = next((f for f in ('name', 'zitat', 'abk') if f in fields), None)
            columns = ['pk', *authority_fields] + ([label] if label else [])
            total, populated = 0, dict.fromkeys(authority_fields, 0)
            for row in model.objects.using(options['database']).values(*columns).iterator(chunk_size=1000):
                total += 1
                for field in authority_fields:
                    if row[field] and str(row[field]).strip():
                        populated[field] += 1
                        records.append({'model': model._meta.label, 'id': row['pk'],
                                        'label': row.get(label, ''), 'field': field, 'value': row[field]})
            coverage.append({'model': model._meta.label, 'rows': total, 'populated_fields': populated})
        report = inventory(records)
        report.update(generated_at=datetime.now(timezone.utc).isoformat(),
                      scope='All authority-table rows, including unused entries; not public-object counts.',
                      database_alias=options['database'], coverage=coverage)
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
