"""Fill empty GeoNames/GND/VIAF fields from build_identifier_proposals.py output.

Never overwrites: a row is only written if the target field is still empty and the
Nomisma ID is unchanged since the inventory export. Without --apply nothing is
written. With --apply a JSON log of old/new values is stored for rollback.
"""
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from slg.services.authority_display import clear_display_cache
from slg.services.authority_review import REFERENCE_FIELDS, record_hash, reviewed_path
from slg.services.authority_review import SCHEMA as REVIEWED_SCHEMA
from slg.services.identifier_enrichment import (
    PARSERS,
    PROPOSAL_SCHEMA,
    TARGETS,
    stored_value,
)
from slg.signals import touch_oai_datestamps


def _empty(field):
    return Q(**{field + '__isnull': True}) | Q(**{field: ''})


def _nom_filter(value):
    return Q(name_nom_id=value) if value else (Q(name_nom_id__isnull=True) | Q(name_nom_id=''))


class Command(BaseCommand):
    help = 'Füllt leere GeoNames-/GND-/VIAF-Felder aus geprüften Vorschlägen (ohne --apply: nur Vorschau).'

    def add_arguments(self, parser):
        parser.add_argument('proposals', type=Path)
        parser.add_argument('--decisions', type=Path,
                            help='review.csv mit ausgefüllter Spalte "Entscheidung" (ID oder URI; "-" = auslassen).')
        parser.add_argument('--apply', action='store_true', help='Tatsächlich schreiben.')
        parser.add_argument('--log', type=Path, help='Protokolldatei (Standard: neben proposals.json).')

    def handle(self, *args, **options):
        try:
            report = json.loads(options['proposals'].read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as error:
            raise CommandError(f'Vorschläge nicht lesbar: {error}') from error
        if not isinstance(report, dict) or report.get('schema') != PROPOSAL_SCHEMA:
            raise CommandError('Unbekanntes Vorschlagsformat.')
        planned = self.plan(report['proposals'], options['decisions'])
        changes, skipped = self.check(planned)
        for reason, count in sorted(skipped.items()):
            self.stdout.write(f'Übersprungen ({reason}): {count}')
        by_field = {}
        for change in changes:
            key = f"{change['model']}.{change['field']}"
            by_field[key] = by_field.get(key, 0) + 1
        for key, count in sorted(by_field.items()):
            self.stdout.write(f'{key}: {count}')
        if not options['apply']:
            self.stdout.write(f'{len(changes)} Felder würden gefüllt. Vorschau ohne Schreibzugriff.')
            return
        written = self.write(changes)
        log = options['log'] or options['proposals'].with_name(
            'applied-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
        log.write_text(json.dumps({'applied_at': datetime.now(timezone.utc).isoformat(),
                                   'proposals': str(options['proposals']),
                                   'inventory_sha256': report.get('inventory_sha256'),
                                   'changes': written}, ensure_ascii=False, indent=1), encoding='utf-8')
        self.stdout.write(f'{len(written)} Felder gefüllt. Protokoll: {log}')

    def plan(self, proposals, decisions_path):
        planned = [dict(p) for p in proposals if p['status'] == 'auto']
        if not decisions_path:
            return planned
        review = {(p['model'], str(p['id']), p['field']): p for p in proposals if p['status'] == 'review'}
        try:
            with decisions_path.open(encoding='utf-8-sig', newline='') as stream:
                sample = stream.read(4096)
                stream.seek(0)
                rows = list(csv.DictReader(stream, delimiter=';' if sample.count(';') >= sample.count(',') else ','))
        except OSError as error:
            raise CommandError(f'Entscheidungen nicht lesbar: {error}') from error
        for row in rows:
            decision = (row.get('Entscheidung') or '').strip()
            if not decision or decision == '-':
                continue
            key = ((row.get('Modell') or '').strip(), (row.get('ID') or '').strip().lstrip("'"), (row.get('Feld') or '').strip())
            proposal = review.get(key)
            if not proposal:
                raise CommandError(f'Entscheidung ohne passenden Prüffall: {":".join(key)}')
            identifier = PARSERS[proposal['kind']](decision)
            if not identifier:
                raise CommandError(f'Ungültige {proposal["kind"]}-Kennung "{decision}": {":".join(key)}')
            planned.append(dict(proposal, value=stored_value(proposal['kind'], identifier), status='decided'))
        return planned

    def check(self, planned):
        changes, skipped, seen = [], {}, set()
        for p in planned:
            model_label, field = p['model'], p['field']
            if field not in TARGETS.get(model_label, {}):
                raise CommandError(f'Nicht unterstütztes Feld: {model_label}.{field}')
            key = (model_label, p['id'], field)
            if key in seen:
                raise CommandError(f'Doppelter Eintrag: {key}')
            seen.add(key)
            kind = TARGETS[model_label][field][0]
            if not PARSERS[kind](p['value'] or ''):
                raise CommandError(f'Ungültiger Wert {p["value"]!r}: {key}')
            model = apps.get_model(model_label)
            row = model.objects.filter(pk=p['id']).values('name_nom_id', field).first()
            if row is None:
                reason = 'Datensatz gelöscht'
            elif (row['name_nom_id'] or '') != (p['name_nom_id'] or ''):
                reason = 'Nomisma-ID geändert'
            elif (row[field] or '').strip():
                reason = 'Feld inzwischen befüllt'
            else:
                changes.append({'model': model_label, 'id': p['id'], 'field': field, 'old': row[field],
                                'new': p['value'], 'name_nom_id': p['name_nom_id'], 'origin': p['status'],
                                'candidates': p['candidates']})
                continue
            skipped[reason] = skipped.get(reason, 0) + 1
        return changes, skipped

    def write(self, changes):
        written = []
        person_before = {}
        with transaction.atomic():
            Person = apps.get_model('slg.Person')
            person_ids = {c['id'] for c in changes if c['model'] == 'slg.Person' and c['field'] in REFERENCE_FIELDS}
            fields = {f.name for f in Person._meta.concrete_fields} & set(REFERENCE_FIELDS)
            for row in Person.objects.filter(pk__in=person_ids).values('pk', 'name', *fields):
                person_before[row['pk']] = row
            for change in changes:
                model = apps.get_model(change['model'])
                # Queryset update: atomic fill-only guard, no per-row MTOA resync.
                updated = model.objects.filter(
                    _nom_filter(change['name_nom_id']), _empty(change['field']), pk=change['id'],
                ).update(**{change['field']: change['new']})
                if updated:
                    written.append(change)
            for model_label in TARGETS:
                pks = {c['id'] for c in written if c['model'] == model_label}
                if pks:
                    touch_oai_datestamps(apps.get_model(model_label)._meta.model_name, pks)
        self.carry_reviewed_labels(person_before, written)
        return written

    def carry_reviewed_labels(self, before, written):
        """A newly filled DNB changes the reference hash of approved English labels; keep them valid."""
        changed = {c['id'] for c in written if c['model'] == 'slg.Person' and c['field'] in REFERENCE_FIELDS}
        output = reviewed_path()
        if not changed or not output.exists():
            return
        lock = output.with_suffix(output.suffix + '.lock')
        try:
            lock.touch(exist_ok=False)
        except FileExistsError as error:
            raise CommandError(f'Freigabebestand gesperrt ({lock}); Felder sind geschrieben, Label-Hashes nicht '
                               'übertragen. Später erneut mit gleicher Protokolldatei prüfen.') from error
        temporary = None
        try:
            data = json.loads(output.read_text(encoding='utf-8'))
            if data.get('schema') != REVIEWED_SCHEMA:
                raise CommandError('Unbekanntes Format des Freigabebestands.')
            Person = apps.get_model('slg.Person')
            fields = {f.name for f in Person._meta.concrete_fields} & set(REFERENCE_FIELDS)
            after = {row['pk']: row for row in Person.objects.filter(pk__in=changed).values('pk', 'name', *fields)}
            carried = 0
            for pk in changed:
                entry = data['labels'].get(f'slg.Person:{pk}')
                if entry and pk in before and entry.get('original_sha256') == record_hash('slg.Person', pk, before[pk]):
                    entry['original_sha256'] = record_hash('slg.Person', pk, after[pk])
                    entry['identifier_enrichment'] = datetime.now(timezone.utc).isoformat()
                    carried += 1
            if carried:
                with NamedTemporaryFile('w', encoding='utf-8', dir=output.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    json.dump(data, handle, ensure_ascii=False)
                os.replace(temporary, output)
                temporary = None
                clear_display_cache()
                self.stdout.write(f'{carried} freigegebene englische Personenlabels auf neue GND übertragen.')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            lock.unlink()
