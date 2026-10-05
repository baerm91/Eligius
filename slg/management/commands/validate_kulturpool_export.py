from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from slg.models import Obj, Slg
from slg.oai.edm import PERSON_AUTHORITY_FIELDS, authority_uri, has_descriptive_title, images, typology_uris, valid_uri
from slg.oai.querysets import CONTROLLED, eligible_objects, export_rows, objects_for_rows, with_metadata_relations
from slg.oai.readiness import collection_readiness


class Command(BaseCommand):
    help = 'Prüft Kulturpool-Freigaben, Objektqualität und getrennte Rechteangaben, ohne Daten zu ändern.'

    def add_arguments(self, parser):
        parser.add_argument('--slg', type=int, help='Nur diese freigegebene Sammlung prüfen.')
        parser.add_argument('--strict', action='store_true', help='Fehlende Rechte oder Qualitätslücken ergeben einen Fehlerstatus.')

    def handle(self, *args, **options):
        collections = Slg.objects.filter(kulturpool_export_erlaubt=True).order_by('pk')
        if options['slg']:
            collections = collections.filter(pk=options['slg'])
        request = RequestFactory().get('/oai/', HTTP_HOST='localhost')
        failures = False
        for slg in collections.iterator():
            all_objects = Obj.objects.filter(Slg=slg)
            controlled = all_objects.filter(workflow__name__iexact=CONTROLLED)
            counts = {
                'grundsätzlich exportfähig': eligible_objects().filter(Slg=slg).count(),
                'wegen Objektkontrolle ausgeschlossen': all_objects.exclude(workflow__name__iexact=CONTROLLED).count(),
                'wegen Typkontrolle ausgeschlossen': controlled.filter(Typ__isnull=False).exclude(Typ__workflow__name__iexact=CONTROLLED).count(),
                'über OAI verfügbar': 0, 'ohne Bild': 0, 'ohne sinnvollen Titel': 0, 'ohne externe Normdaten': 0,
            }
            rows = export_rows().filter(slg_fk=slg)
            after = 0
            while True:
                page = list(with_metadata_relations(rows.filter(obj_id__gt=after))[:200])
                if not page:
                    break
                objects = objects_for_rows(page)
                for row in page:
                    obj = objects.get(row.obj_id)
                    if obj is None:
                        continue
                    counts['über OAI verfügbar'] += 1
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
            counts['fehlende/veraltete MTOA'] = counts['grundsätzlich exportfähig'] - counts['über OAI verfügbar']
            issues = collection_readiness(slg)
            counts['ohne ausreichende Rights-Konfiguration'] = counts['über OAI verfügbar'] if issues else 0
            self.stdout.write(f'{slg.name} (eligius:collection-{slg.pk}):')
            for label, count in counts.items():
                self.stdout.write(f'  {label}: {count}')
            for issue in issues:
                self.stdout.write(self.style.WARNING('  ' + issue))
            failures |= bool(issues or counts['ohne Bild'] or counts['ohne sinnvollen Titel'] or counts['fehlende/veraltete MTOA'])
        if options['strict'] and failures:
            raise CommandError('Kulturpool-Export noch nicht bereit; gemeldete Rechte-/Qualitätslücken beheben.')
