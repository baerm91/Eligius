"""Package administration and bulk object assignments."""

from django.contrib import admin
from django.db.models import Count
from import_export import fields, resources
from import_export.admin import ImportExportModelAdmin
from import_export.results import Result, RowResult

from .import_utils import parse_object_id
from .models import Obj


class PaketAdmin(ImportExportModelAdmin):
    search_fields = ('name', 'titel_oeffentlich', 'beschreibung')
    list_display = (
        'name',
        'titel_oeffentlich',
        'slug',
        'kontexttyp',
        'darstellungsart',
        'fundplatz_kontext',
        'ist_arbeitspaket',
        'online_freigegeben',
        'anzahl_objekte',
        'erstellt_am',
        'bearbeitet_am',
    )
    list_display_links = ('name',)
    readonly_fields = ('slug',)
    list_filter = ('ist_arbeitspaket', 'online_freigegeben', 'kontexttyp', 'darstellungsart', 'fundplatz_kontext', 'erstellt_am')
    list_editable = ('ist_arbeitspaket', 'online_freigegeben', 'darstellungsart')
    autocomplete_fields = ('vergleichspakete', 'literatur')
    radio_fields = {
        'darstellungsart': admin.HORIZONTAL,
        'kontexttyp': admin.HORIZONTAL,
        'fundplatz_kontext': admin.HORIZONTAL,
    }
    ordering = ['name']
    fieldsets = (
        (None, {
            'fields': ('name', 'beschreibung', 'ist_arbeitspaket', 'online_freigegeben')
        }),
        ('Öffentliche Präsentation', {
            'fields': ('titel_oeffentlich', 'slug', 'kontexttyp', 'darstellungsart', 'frontcover', 'bekannte_objektanzahl')
        }),
        ('Fundkontext', {
            'fields': ('fund_lat', 'fund_lng', 'fundzeitpunkt_verbal', 'fundplatz_kontext')
        }),
        ('Vergleich & Literatur', {
            'fields': ('vergleichspakete', 'literatur')
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_anzahl_objekte=Count('obj'))

    def anzahl_objekte(self, obj):
        anzahl = getattr(obj, '_anzahl_objekte', None)
        if anzahl is not None:
            return anzahl
        return obj.obj_set.count()
    anzahl_objekte.short_description = 'Anzahl Objekte'
    anzahl_objekte.admin_order_field = '_anzahl_objekte'

# Import/Export Resource für Paket-Zuweisungen (KOMPLETT ÜBERSCHRIEBEN)
class ObjPaketZuweisungResource(resources.ModelResource):
    invnr = fields.Field(column_name='invnr', attribute='invnr')
    slg_name = fields.Field(column_name='Sammlung')
    slgteil_name = fields.Field(column_name='Sammlungsteil')
    paket_name = fields.Field(column_name='Paket')

    class Meta:
        model = Obj
        fields = ('invnr', 'slg_name', 'slgteil_name', 'paket_name')
        import_id_fields = ('invnr',)  # Vereinfacht
        skip_unchanged = True
        report_skipped = True
        use_transactions = True  # Wichtig für Konsistenz

    def _clean_string(self, value):
        """Robuste String-Bereinigung"""
        if not value:
            return None

        cleaned = str(value).strip()
        # Normalisiere nur mehrfache Leerzeichen zu einzelnen
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)

        return cleaned if cleaned else None

    def import_data(self, dataset, dry_run=False, raise_errors=False, use_transactions=None, collect_failed_rows=False, **kwargs):
        """Eigener Bulk-Import. Der Dry-Run (Vorschau) führt dieselbe Zuordnung aus
        und rollt anschließend zurück, damit Fehler bereits in der Vorschau sichtbar sind."""
        from .operations import operation
        with operation('admin_import', 'package_assignments', dry_run=dry_run, rows=len(dataset)) as event:
            result = self._bulk_import(dataset, dry_run=dry_run)
            if result.has_errors() or result.has_validation_errors():
                event['outcome'] = 'rejected'
            return result

    @staticmethod
    def _norm(value):
        return (value or '').strip().casefold()

    def _row_value(self, row, *keys):
        for key in keys:
            if key in row:
                return self._clean_string(row.get(key))
        return None

    def _bulk_import(self, dataset, dry_run=False):
        from django.db import transaction

        from slg.models import Paket, Obj

        result = Result()
        ThroughModel = Obj.pakete.through
        MAX_FEHLER = 20

        rows = []
        fehler = []
        for i, row in enumerate(dataset.dict, start=2):  # Zeile 1 = Kopfzeile
            obj_id = self._row_value(row, 'Objekt-ID', 'objekt_id', 'id')
            invnr = self._row_value(row, 'invnr', 'Inv.-Nr.')
            slg_name = self._row_value(row, 'Sammlung')
            slgteil_name = self._row_value(row, 'Sammlungsteil')
            paket_name = self._row_value(row, 'Paket')
            if not paket_name:
                fehler.append(f"Zeile {i}: Paket fehlt")
                continue
            if obj_id:
                try:
                    obj_id = parse_object_id(obj_id)
                except ValueError:
                    fehler.append(f"Zeile {i}: ungültige Objekt-ID '{obj_id}'")
                    continue
            elif not (invnr and slg_name):
                fehler.append(f"Zeile {i}: Objekt-ID oder invnr + Sammlung erforderlich")
                continue
            rows.append((i, obj_id, invnr, slg_name, slgteil_name, paket_name))

        if not rows and not fehler:
            fehler.append("Keine Datenzeilen gefunden. Spalten prüfen: invnr, Sammlung, Sammlungsteil, Paket "
                          "(bei CSV Komma als Trennzeichen).")

        created = skipped = 0
        neue_pakete = []
        try:
            with transaction.atomic():
                # Objekte laden: per ID oder per Inventarnummer (Namen werden am Objekt verglichen,
                # nicht über Namens-Caches – so stören doppelte Sammlungs(teil)namen nicht).
                ids = {r[1] for r in rows if r[1]}
                invnrs = {r[2] for r in rows if not r[1]}
                by_id = {o.id: o for o in Obj.objects.filter(pk__in=ids).select_related('Slg', 'SlgTeil')}
                by_invnr = {}
                for o in Obj.objects.filter(invnr__in=invnrs).select_related('Slg', 'SlgTeil'):
                    by_invnr.setdefault(o.invnr.strip(), []).append(o)

                paket_namen = {r[5] for r in rows}
                pakete = {p.name: p for p in Paket.objects.filter(name__in=paket_namen)}
                for name in sorted(paket_namen - set(pakete)):
                    pakete[name] = Paket.objects.create(name=name)
                    neue_pakete.append(name)

                zuweisungen = []
                for i, obj_id, invnr, slg_name, slgteil_name, paket_name in rows:
                    if obj_id:
                        obj = by_id.get(obj_id)
                        if not obj:
                            fehler.append(f"Zeile {i}: Objekt-ID {obj_id} existiert nicht")
                            continue
                    else:
                        kandidaten = by_invnr.get(invnr, [])
                        if not kandidaten:
                            fehler.append(f"Zeile {i}: Inv.-Nr. '{invnr}' existiert nicht")
                            continue
                        passend = [
                            o for o in kandidaten
                            if self._norm(o.Slg.name if o.Slg else '') == self._norm(slg_name)
                            and (not slgteil_name or self._norm(o.SlgTeil.name if o.SlgTeil else '') == self._norm(slgteil_name))
                        ]
                        if len(passend) != 1:
                            vorhanden = '; '.join(
                                f"{o.Slg.name if o.Slg else '–'} / {o.SlgTeil.name if o.SlgTeil else '–'}" for o in kandidaten
                            )
                            grund = 'mehrdeutig' if passend else 'Sammlung/Sammlungsteil passen nicht'
                            fehler.append(f"Zeile {i}: '{invnr}' {grund} (in Eligius: {vorhanden})")
                            continue
                        obj = passend[0]
                    zuweisungen.append((obj.id, pakete[paket_name].id))

                vorhanden = set(
                    ThroughModel.objects.filter(
                        obj_id__in={z[0] for z in zuweisungen},
                        paket_id__in={z[1] for z in zuweisungen},
                    ).values_list('obj_id', 'paket_id')
                )
                neu = sorted(set(zuweisungen) - vorhanden)
                skipped = len(zuweisungen) - len(neu)
                ThroughModel.objects.bulk_create(
                    [ThroughModel(obj_id=o, paket_id=p) for o, p in neu], batch_size=1000, ignore_conflicts=True
                )
                created = len(neu)

                if fehler:
                    # Alles oder nichts: keine Teilimporte und keine neu angelegten
                    # Pakete, wenn eine Zeile fehlerhaft ist.
                    transaction.set_rollback(True)
                    created = skipped = 0
                    if not dry_run:
                        fehler.insert(0, "Import abgebrochen – es wurde nichts gespeichert. "
                                         "Bitte die fehlerhaften Zeilen korrigieren.")
                elif dry_run:
                    transaction.set_rollback(True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            fehler.append(f"Schwerwiegender Fehler: {e}")
            created = skipped = 0

        result.totals[RowResult.IMPORT_TYPE_NEW] = created
        result.totals[RowResult.IMPORT_TYPE_SKIP] = skipped
        result.totals[RowResult.IMPORT_TYPE_ERROR] = len(fehler)
        from import_export.results import Error as ImportError_
        for msg in fehler[:MAX_FEHLER]:
            # Error erwartet eine Exception (das Admin-Template rendert error.traceback)
            result.append_base_error(ImportError_(ValueError(msg)))
        if len(fehler) > MAX_FEHLER:
            result.append_base_error(ImportError_(ValueError(f"... und {len(fehler) - MAX_FEHLER} weitere Fehler")))
        return result

# Optimierte Admin-Klasse für bessere Performance
class ObjPaketZuweisungAdmin(ImportExportModelAdmin):
    resource_class = ObjPaketZuweisungResource
    list_display = ('invnr', 'slg_display', 'slgteil_display', 'pakete_display')
    search_fields = ('invnr',)
    list_filter = ('Slg', 'SlgTeil', 'pakete')

    def get_queryset(self, request):
        """Optimiertes QuerySet mit select_related und prefetch_related"""
        return super().get_queryset(request).select_related(
            'Slg', 'SlgTeil'
        ).prefetch_related('pakete')

    def slg_display(self, obj):
        return obj.Slg.name if obj.Slg else '-'
    slg_display.short_description = 'Sammlung'

    def slgteil_display(self, obj):
        return obj.SlgTeil.name if obj.SlgTeil else '-'
    slgteil_display.short_description = 'Sammlungsteil'

    def pakete_display(self, obj):
        # Nutze prefetch_related Daten
        return ', '.join([paket.name for paket in obj.pakete.all()])
    pakete_display.short_description = 'Pakete'

# Registrierung
