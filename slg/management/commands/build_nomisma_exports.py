from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from slg.models import Obj, Slg
from slg.nomisma_rdf import CONTROLLED_WORKFLOW_NAME, cache_path, cached_dump, nomisma_readiness


class Command(BaseCommand):
    help = ('Erzeugt die Nomisma-Datendumps aller freigegebenen Sammlungen neu (Dateicache) '
            'und meldet, welche Angaben für Nomisma noch fehlen.')

    def add_arguments(self, parser):
        parser.add_argument('--slg', type=int, help='Nur diese Sammlung.')
        parser.add_argument('--strict', action='store_true', help='Fehlende Angaben ergeben einen Fehlerstatus.')

    def handle(self, *args, **options):
        collections = Slg.objects.filter(nomisma_export_erlaubt=True).order_by('pk')
        if options['slg']:
            collections = collections.filter(pk=options['slg'])
        if not settings.ELIGIUS_PUBLIC_BASE_URL:
            raise CommandError('ELIGIUS_PUBLIC_BASE_URL ist nicht gesetzt – Nomisma braucht stabile URIs.')
        request = RequestFactory().get('/', HTTP_HOST='localhost')
        problems = False
        for slg in collections.iterator():
            objects = Obj.objects.filter(Slg=slg)
            controlled = objects.filter(workflow__name__iexact=CONTROLLED_WORKFLOW_NAME)
            path = cached_dump(slg, request, force=True)
            if path is None:
                raise CommandError(f'Cache-Verzeichnis nicht beschreibbar: {cache_path(slg)}')
            exported = path.read_text(encoding='utf-8').count('<nmo:NumismaticObject ')
            self.stdout.write(f'{slg.pk} {slg.name}: {exported} Münzen exportiert '
                              f'(kontrolliert: {controlled.count()}, davon Fälschung/Verdacht: '
                              f'{controlled.filter(faelschung__isnull=False).count()}, Typ unsicher: '
                              f'{controlled.filter(Typ_unsicher=True).count()}) -> {path}')
            for issue in nomisma_readiness(slg):
                problems = True
                self.stdout.write(self.style.WARNING(f'  - {issue}'))
        if problems and options['strict']:
            raise CommandError('Nomisma-Export unvollständig.')
