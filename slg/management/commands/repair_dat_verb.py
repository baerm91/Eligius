"""Korrigiert gespeicherte Datierungstexte wie "-44-14 n. Chr." (Zeitenwende).

Ersetzt nur Texte, die exakt der fehlerhaften automatischen Erzeugung entsprechen;
von Hand gepflegte Datierungen bleiben unberührt. Ohne --apply nur Vorschau.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from slg.models import Muenztyp, Obj, Person, SlgInformation

# (Modell, Feld von, Feld bis)
TARGETS = ((Obj, 'dat_von', 'dat_bis'), (Muenztyp, 'dat_von', 'dat_bis'),
           (Person, 'dat_geboren', 'dat_gestorben'), (SlgInformation, 'dat_von', 'dat_bis'))


def legacy_text(von, bis):
    """Was die alte get_dat_verb() für Zeiträume über die Zeitenwende erzeugt hat."""
    return f'{von}-{bis} n. Chr.'


class Command(BaseCommand):
    help = 'Korrigiert automatisch erzeugte Datierungen über die Zeitenwende (z. B. "-44-14 n. Chr.").'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Änderungen speichern (sonst nur Vorschau).')

    def handle(self, *args, apply=False, **options):
        total = 0
        for model, start, end in TARGETS:
            rows = model.objects.filter(**{f'{start}__lt': 0, f'{end}__gt': 0}).exclude(dat_verb__isnull=True)
            for instance in rows.iterator():
                old = (instance.dat_verb or '').strip()
                von, bis = getattr(instance, start), getattr(instance, end)
                if old != legacy_text(von, bis):
                    continue
                new = instance.get_dat_verb()
                total += 1
                self.stdout.write(f'{model.__name__} #{instance.pk}: "{old}" -> "{new}"')
                if apply:
                    with transaction.atomic():
                        instance.dat_verb = new
                        # save() löst die bestehende MTOA-Synchronisierung samt OAI-Datestamp aus.
                        instance.save(update_fields=['dat_verb'])
        verb = 'korrigiert' if apply else 'zu korrigieren (Vorschau, --apply zum Speichern)'
        self.stdout.write(self.style.SUCCESS(f'{total} Datierung(en) {verb}.'))
