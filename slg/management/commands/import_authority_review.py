import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from slg.services.authority_display import MODELS, clear_display_cache
from slg.services.authority_review import REFERENCE_FIELDS, SCHEMA, original_hash, record_hash, reviewed_path


def read_json(path):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('JSON-Objekt erwartet.')
    return data


class Command(BaseCommand):
    help = 'Prüft und installiert ausdrücklich bestätigte englische Normdatenlabels.'

    def add_arguments(self, parser):
        parser.add_argument('proposals', type=Path)
        parser.add_argument('review', type=Path)
        parser.add_argument('--apply', action='store_true', help='Geprüfte Entscheidungen installieren.')

    def handle(self, *args, **options):
        try:
            proposals = read_json(options['proposals'])
            review = read_json(options['review'])
            entries = self.entries(proposals, review)
            if options['apply']:
                if entries:
                    self.install(entries)
                self.stdout.write(f'{len(entries)} bestätigte Labels installiert.')
            else:
                self.stdout.write(f'{len(entries)} bestätigte Labels geprüft. Vorschau ohne Schreibzugriff.')
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise CommandError(f'Import abgebrochen: {error}') from error

    def entries(self, proposals, review):
        source_hash = proposals['inventory_sha256']
        if (review.get('schema') != 'eligius-authority-review-v1'
                or not source_hash or review.get('inventory_sha256') != source_hash):
            raise CommandError('Prüfstand und Vorschlagsbestand gehören nicht zusammen.')
        by_key = {(row['model'], row['id']): row for row in proposals['proposals']}
        result = {}
        for decision in review['decisions']:
            if decision['status'] != 'approved':
                continue
            model_label, pk = decision['model'], decision['id']
            key = f'{model_label}:{pk}'
            if key in result or type(pk) is not int or pk < 1:
                raise CommandError(f'Ungültige oder doppelte bestätigte Entscheidung: {key}')
            row = by_key.get((model_label, pk))
            if not row or not model_label.startswith('slg.') or model_label[4:] not in MODELS:
                raise CommandError(f'Kein verwendbarer Vorschlagsdatensatz: {key}')
            expected = decision['original_sha256']
            if expected != row['original_sha256'] or expected != original_hash(row['references']):
                raise CommandError(f'Originaldaten im Prüfstand stimmen nicht überein: {key}')
            model = apps.get_model(model_label)
            fields = {field.name for field in model._meta.concrete_fields}
            values = model.objects.filter(pk=pk).values('name', *(fields & set(REFERENCE_FIELDS))).first()
            if values is None or record_hash(model_label, pk, values) != expected:
                raise CommandError(f'Originalname oder Normdatenverweise inzwischen geändert: {key}')
            label = decision['value'].strip()
            if not label or len(label) > 500:
                raise CommandError(f'Ungültige Bezeichnung: {key}')
            reviewed_at = parse_datetime(decision['updated_at'])
            if reviewed_at is None or not is_aware(reviewed_at):
                raise CommandError(f'Ungültiger Prüfzeitpunkt: {key}')
            result[key] = {
                'label': label, 'original_sha256': expected, 'inventory_sha256': source_hash,
                'original': row['original'], 'references': row['references'],
                'candidates': row['candidates'], 'note': decision.get('note', ''),
                'reviewed_at': decision['updated_at'],
            }
        return result

    def install(self, entries):
        output = reviewed_path()
        output.parent.mkdir(parents=True, exist_ok=True)
        lock = output.with_suffix(output.suffix + '.lock')
        lock.touch(exist_ok=False)
        temporary = None
        try:
            previous = read_json(output) if output.exists() else {'schema': SCHEMA, 'labels': {}}
            if previous['schema'] != SCHEMA:
                raise CommandError('Unbekanntes Format des bestehenden Freigabebestands.')
            for key, entry in entries.items():
                installed = previous['labels'].get(key)
                if installed and entry != installed and (
                    parse_datetime(installed['reviewed_at']) >= parse_datetime(entry['reviewed_at'])
                ):
                    raise CommandError(f'Eine gleichzeitige oder neuere Freigabe ist bereits installiert: {key}')
            previous['labels'].update(entries)
            with NamedTemporaryFile('w', encoding='utf-8', dir=output.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(previous, handle, ensure_ascii=False)
            os.replace(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            lock.unlink()
        clear_display_cache()
