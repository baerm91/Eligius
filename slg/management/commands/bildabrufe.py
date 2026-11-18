from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Sum

from slg.models import Bildabruf


class Command(BaseCommand):
    help = 'Zeigt Abrufe der Bild-Weiterleitung nach Herkunft (z. B. kulturpool.at, europeana.eu).'

    def add_arguments(self, parser):
        parser.add_argument('--von', help='Startdatum JJJJ-MM-TT (Standard: vor 30 Tagen)')
        parser.add_argument('--bis', help='Enddatum JJJJ-MM-TT (Standard: heute)')
        parser.add_argument('--slg', type=int, help='Nur Objekte dieser Sammlung')
        parser.add_argument('--herkunft', help='Nur diese Herkunft, z. B. kulturpool.at (Teilstring)')
        parser.add_argument('--top', type=int, default=20, help='Anzahl der meistabgerufenen Objekte')
        parser.add_argument('--mit-automatisierten', action='store_true',
                            help='Harvester/Crawler-Abrufe in das Objekt-Ranking einbeziehen')

    def handle(self, *args, **options):
        try:
            end = date.fromisoformat(options['bis']) if options['bis'] else date.today()
            start = date.fromisoformat(options['von']) if options['von'] else end - timedelta(days=30)
        except ValueError as error:
            raise CommandError(f'Ungültiges Datum: {error}')
        rows = Bildabruf.objects.filter(datum__range=(start, end))
        if options['slg']:
            rows = rows.filter(obj__Slg_id=options['slg'])
        if options['herkunft']:
            rows = rows.filter(herkunft__icontains=options['herkunft'])
        self.stdout.write(f'Bildabrufe {start} – {end}')
        by_origin = rows.values('herkunft', 'automatisiert').annotate(
            abrufe=Sum('anzahl'), objekte=Count('obj', distinct=True)).order_by('automatisiert', '-abrufe')
        for entry in by_origin:
            kind = 'automatisiert' if entry['automatisiert'] else 'Browser'
            self.stdout.write(f"  {entry['herkunft'] or '(direkt/unbekannt)'} [{kind}]: "
                              f"{entry['abrufe']} Abrufe, {entry['objekte']} Objekte")
        if not options['mit_automatisierten']:
            rows = rows.filter(automatisiert=False)
        top = rows.values('obj_id', 'obj__invnr').annotate(abrufe=Sum('anzahl')).order_by('-abrufe', 'obj_id')
        self.stdout.write('  Meistabgerufene Objekte:')
        for entry in top[:options['top']]:
            self.stdout.write(f"    {entry['abrufe']:>6}  {entry['obj__invnr'] or ''}  /objekt/{entry['obj_id']}/")
