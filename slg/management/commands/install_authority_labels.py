"""Install explicit English labels, not local descriptions or approval decisions."""
import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from slg.services.authority_display import clear_display_cache
from slg.services.authority_inventory import identify_authority


class Command(BaseCommand):
    help = 'Installiert englische Normdatenlabels aus proposals.json atomar; Originaldaten bleiben unverändert.'

    def add_arguments(self, parser):
        parser.add_argument('proposals', type=Path)
        parser.add_argument('--output', type=Path)

    def handle(self, *args, **options):
        report = json.loads(options['proposals'].read_text(encoding='utf-8'))
        labels = {}
        for row in report['proposals']:
            for candidate in row['candidates']:
                ref = identify_authority(candidate.get('uri'))
                label = candidate.get('label')
                if not ref or not isinstance(label, str) or not label.strip():
                    continue
                # GND-to-Wikidata is accepted only with a reciprocal identity link.
                keys = [':'.join(ref)]
                if candidate.get('via_gnd') and candidate.get('reciprocal_gnd'):
                    gnd = identify_authority(candidate['via_gnd'])
                    if gnd:
                        keys.append(':'.join(gnd))
                for key in keys:
                    entry = dict(label=label, source_url=candidate.get('source_url'),
                                 source_uri=candidate['uri'])
                    if key in labels and labels[key]['label'] != label:
                        raise CommandError('Widersprüchliche englische Labels für dieselbe URI: ' + key)
                    labels[key] = entry
        if not labels:
            raise CommandError('Keine englischen Normdatenlabels enthalten.')
        output = options['output'] or Path(getattr(settings, 'ELIGIUS_AUTHORITY_LABELS_PATH',
                                                  settings.BASE_DIR / 'var/authority-labels.en.json'))
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(schema='eligius-authority-labels-v1', generated_at=report['generated_at'],
                       labels=labels)
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, output)
        clear_display_cache()
        self.stdout.write(f'{len(labels)} URI-Labels installiert: {output}')
