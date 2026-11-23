from django.core.management.base import BaseCommand

from slg.mtoa_queue import process_queue


class Command(BaseCommand):
    help = 'Arbeitet ausstehende MTOA-Aktualisierungen ab (Fallback nach Worker-Neustart; z.B. per Cron).'

    def handle(self, *args, **options):
        done = process_queue()
        self.stdout.write(self.style.SUCCESS(f'{done} MTOA-Aktualisierung(en) erledigt.'))
