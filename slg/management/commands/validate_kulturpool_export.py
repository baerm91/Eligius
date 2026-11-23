from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from slg.models import Obj, Slg
from slg.oai.edm import PERSON_AUTHORITY_FIELDS, authority_uri, has_descriptive_title, images, typology_uris, valid_uri
from slg.oai.querysets import CONTROLLED, eligible_objects, export_rows, objects_for_rows, with_metadata_relations
from slg.oai.readiness import collection_readiness


class Command(BaseCommand):
    help = 'Prüft Kulturpool-Freigaben, Objektqualität und getrennte Rechteangaben, ohne Daten zu ändern.'

    def add_arguments(self, parser):
        parser.add_argument('--slg', type=int, help='Nur diese Sammlung prüfen.')
        parser.add_argument('--preflight', action='store_true',
                            help='Mit --slg auch vor der Veröffentlichung prüfen.')
        parser.add_argument('--strict', action='store_true', help='Fehlende Rechte oder Qualitätslücken ergeben einen Fehlerstatus.')

    def handle(self, *args, **options):
        collection_id = options['slg']
        preflight = options['preflight']
        if preflight and collection_id is None:
            raise CommandError('--preflight benötigt eine Sammlungs-ID mit --slg.')
        collections = Slg.objects.order_by('pk')
        if not preflight:
            collections = collections.filter(kulturpool_export_erlaubt=True)
        if collection_id is not None:
            collections = collections.filter(pk=collection_id)
        collections = list(collections)
        if not collections:
            message = 'Keine Sammlung zur Prüfung gefunden.'
            if options['strict'] or collection_id is not None:
                raise CommandError(message)
            self.stdout.write(message)
            return
        scope = {'preview_collection_id': collection_id} if preflight else {}
        available_label = 'nach Freigabe exportierbar' if preflight else 'über OAI verfügbar'
        request = RequestFactory().get('/oai/', HTTP_HOST='localhost')
        failures = False
        for slg in collections:
            all_objects = Obj.objects.filter(Slg=slg)
            controlled = all_objects.filter(workflow__name__iexact=CONTROLLED)
            counts = {
                'grundsätzlich exportfähig': eligible_objects(**scope).filter(Slg=slg).count(),
                'wegen Objektkontrolle ausgeschlossen': all_objects.exclude(workflow__name__iexact=CONTROLLED).count(),
                'wegen Typkontrolle ausgeschlossen': controlled.filter(Typ__isnull=False).exclude(Typ__workflow__name__iexact=CONTROLLED).count(),
                available_label: 0, 'ohne Bild': 0, 'ohne sinnvollen Titel': 0, 'ohne externe Normdaten': 0,
            }
            rows = export_rows(**scope).filter(slg_fk=slg)
            after = 0
            while True:
                page = list(with_metadata_relations(rows.filter(obj_id__gt=after))[:200])
                if not page:
                    break
                objects = objects_for_rows(page, **scope)
                for row in page:
                    obj = objects.get(row.obj_id)
                    if obj is None:
                        continue
                    counts[available_label] += 1
                    counts['ohne Bild'] += not bool(images(row, request))
                    counts['ohne sinnvollen Titel'] += not has_descriptive_title(row)
                    models = [row.metall_fk, row.nominal_fk, row.mzstaette_fk, row.objekttyp_fk, row.herstellung_fk, row.region_fk]
                    has_authority = any(authority_uri(model.name_nom_id) for model in models if model)
                    if row.mzstaette_fk:
                        mint = row.mzstaette_fk
                        has_authority |= bool(valid_uri(mint.ndpikmk) or valid_uri(mint.geonames) or
                                              (mint.geonames and mint.geonames.isdigit()))
                    has_authority |= any(authority_uri(rel.person.name_nom_id) or
                                         any(valid_uri(getattr(rel.person, field)) for field in PERSON_AUTHORITY_FIELDS)
                                         for rel in row.mtoaperson_set.all())
                    counts['ohne externe Normdaten'] += not (has_authority or typology_uris(obj))
                after = page[-1].obj_id
            counts['fehlende/veraltete MTOA'] = counts['grundsätzlich exportfähig'] - counts[available_label]
            issues = collection_readiness(slg)
            if not counts[available_label]:
                issues.append('Keine über OAI exportierbaren Objekte vorhanden.')
            counts['ohne ausreichende Rights-Konfiguration'] = counts[available_label] if issues else 0
            mode = 'Vorabprüfung' if preflight else 'Öffentlicher Export'
            self.stdout.write(f'{slg.name} (eligius:collection-{slg.pk}, {mode}):')
            for label, count in counts.items():
                self.stdout.write(f'  {label}: {count}')
            for issue in issues:
                self.stdout.write(self.style.WARNING('  ' + issue))
            failures |= bool(issues or counts['ohne Bild'] or counts['ohne sinnvollen Titel'] or counts['fehlende/veraltete MTOA'])
        if options['strict'] and failures:
            raise CommandError('Kulturpool-Export noch nicht bereit; gemeldete Rechte-/Qualitätslücken beheben.')
