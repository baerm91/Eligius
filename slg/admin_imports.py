"""Import and export resources for objects and coin types."""

from import_export import fields, resources
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from .models import (
    AvBeizeichen,
    AvBildrand,
    AvBildtyp,
    Fund,
    Herstellung,
    Metall,
    Muenzstand,
    Muenztyp,
    Mzstaette,
    Nominal,
    Obj,
    Objekttyp,
    Rand,
    Ref,
    Region,
    Reichskreis,
    RvBeizeichen,
    RvBildrand,
    RvBildtyp,
    Slg,
    SlgTeil,
    Variantenbeschr,
    Workflow,
)


class MuenztypImport(resources.ModelResource):
    Objekttyp = fields.Field(
        column_name='Objekttyp',
        attribute='Objekttyp',
        widget=ForeignKeyWidget(Objekttyp, field='name'))  # Bitte anpassen.

    Herstellung = fields.Field(
        column_name='Herstellung',
        attribute='Herstellung',
        widget=ForeignKeyWidget(Herstellung, field='name'))  # Bitte anpassen.

    Reichskreis = fields.Field(
        column_name='Reichskreis',
        attribute='Reichskreis',
        widget=ForeignKeyWidget(Reichskreis, field='name'))

    Muenzstand = fields.Field(
        column_name='Münzstand',
        attribute='Muenzstand',
        widget=ForeignKeyWidget(Muenzstand, field='name'))

    Nominal = fields.Field(
        column_name='Nominal',
        attribute='Nominal',
        widget=ForeignKeyWidget(Nominal, field='name'))

    Metall = fields.Field(
        column_name='Material',
        attribute='Metall',
        widget=ForeignKeyWidget(Metall, field='name'))

    Mzstaette = fields.Field(
        column_name='Münzstätte',
        attribute='Mzstaette',
        widget=ForeignKeyWidget(Mzstaette, field='name'))

    region = fields.Field(
        column_name='Region',
        attribute='region',
        widget=ForeignKeyWidget(Region, field='name'))

    av_bildtyp = fields.Field(
        column_name='AvBildtyp',
        attribute='av_bildtyp',
        widget=ForeignKeyWidget(AvBildtyp, field='name'))

    av_beizeichen = fields.Field(
        column_name='AvBeizeichen',
        attribute='av_beizeichen',
        widget=ForeignKeyWidget(AvBeizeichen, field='name'))

    av_bildrand = fields.Field(
        column_name='AvBildrand',
        attribute='av_bildrand',
        widget=ForeignKeyWidget(AvBildrand, field='name'))

    rv_bildtyp = fields.Field(
        column_name='RvBildtyp',
        attribute='rv_bildtyp',
        widget=ForeignKeyWidget(RvBildtyp, field='name'))

    rv_beizeichen = fields.Field(
        column_name='RvBeizeichen',
        attribute='rv_beizeichen',
        widget=ForeignKeyWidget(RvBeizeichen, field='name'))

    rv_bildrand = fields.Field(
        column_name='RvBildrand',
        attribute='rv_bildrand',
        widget=ForeignKeyWidget(RvBildrand, field='name'))

    rand = fields.Field(
        column_name='Rand',
        attribute='rand',
        widget=ForeignKeyWidget(Rand, field='name'))

    workflow = fields.Field(
        column_name='Workflow',
        attribute='workflow',
        widget=ForeignKeyWidget(Workflow, field='name'))

    Ref = fields.Field(
        column_name='Zitat',
        attribute='Ref',
        widget=ForeignKeyWidget(Ref, field='abk'))

    variante = fields.Field(
        column_name='Variante',
        attribute='variante',
        widget=ForeignKeyWidget(Variantenbeschr, field='name'))

    class Meta:
        model = Muenztyp
        fields = ('id', 'muenztyptitel', 'titel', 'Objekttyp', 'Herstellung', 'Reichskreis', 'Muenzstand',
                  'Nominal', 'Metall', 'Mzstaette', 'region', 'avleg', 'av_bildtyp', 'av_beizeichen', 'av_bildrand',
                  'rvleg', 'rv_bildtyp', 'rv_beizeichen', 'rv_bildrand', 'rand', 'workflow', 'Ref', 'variante', 'link', 'dat_von', 'dat_bis', 'dat_verb')
        export_order = fields
        name = "Export der Muenztypen"
        skip_unchanged = True
        report_skipped = True

    def import_data(self, dataset, dry_run=False, *args, **kwargs):
        from .operations import operation

        with operation('admin_import', 'coin_types', dry_run=dry_run, rows=len(dataset)) as event:
            result = super().import_data(dataset, dry_run, *args, **kwargs)
            if result.has_errors() or result.has_validation_errors():
                event['outcome'] = 'rejected'
            return result

    def get_import_id_fields(self):
        return ['id']

    def dehydrate_Objekttyp(self, muenztyp):
        return muenztyp.Objekttyp.name if muenztyp.Objekttyp else None

    def dehydrate_Herstellung(self, muenztyp):
        return muenztyp.Herstellung.name if muenztyp.Herstellung else None

    def dehydrate_Reichskreis(self, muenztyp):
        return muenztyp.Reichskreis.name if muenztyp.Reichskreis else None

    def dehydrate_Muenzstand(self, muenztyp):
        return muenztyp.Muenzstand.name if muenztyp.Muenzstand else None

    def dehydrate_Nominal(self, muenztyp):
        return muenztyp.Nominal.name if muenztyp.Nominal else None

    def dehydrate_Metall(self, muenztyp):
        return muenztyp.Metall.name if muenztyp.Metall else None

    def dehydrate_Mzstaette(self, muenztyp):
        return muenztyp.Mzstaette.name if muenztyp.Mzstaette else None

    def dehydrate_region(self, muenztyp):
        return muenztyp.region.name if muenztyp.region else None

    def dehydrate_av_bildtyp(self, muenztyp):
        return muenztyp.av_bildtyp.name if muenztyp.av_bildtyp else None

    def dehydrate_av_beizeichen(self, muenztyp):
        return muenztyp.av_beizeichen.name if muenztyp.av_beizeichen else None

    def dehydrate_av_bildrand(self, muenztyp):
        return muenztyp.av_bildrand.name if muenztyp.av_bildrand else None

    def dehydrate_rv_bildtyp(self, muenztyp):
        return muenztyp.rv_bildtyp.name if muenztyp.rv_bildtyp else None

    def dehydrate_rv_beizeichen(self, muenztyp):
        return muenztyp.rv_beizeichen.name if muenztyp.rv_beizeichen else None

    def dehydrate_rv_bildrand(self, muenztyp):
        return muenztyp.rv_bildrand.name if muenztyp.rv_bildrand else None

    def dehydrate_rand(self, muenztyp):
        return muenztyp.rand.name if muenztyp.rand else None

    def dehydrate_workflow(self, muenztyp):
        return muenztyp.workflow.name if muenztyp.workflow else None

    def dehydrate_Ref(self, muenztyp):
        return muenztyp.Ref.abk if muenztyp.Ref else None

    def dehydrate_variante(self, muenztyp):
        return muenztyp.variante.name if muenztyp.variante else None


class ObjResource(resources.ModelResource):
    Slg__name = Field(attribute='Slg__name', column_name='Sammlung')
    SlgTeil__name = Field(attribute='SlgTeil__name', column_name='Sammlungsteil')
    durchmesser = Field(attribute='durchmesser', column_name='Durchmesser in mm')
    gewicht = Field(attribute='gewicht', column_name='Gewicht in g')
    stempelstellung = Field(attribute='stempelstellung', column_name='Stempelstellung in h')
    abnutzung = Field(attribute='abnutzung', column_name='Abnutzung')
    faelschung = Field(attribute='faelschung', column_name='Fälschung?')
    Typ_unsicher = Field(attribute='Typ_unsicher', column_name='Typ_unsicher?')
    #Typ__muenztyptitel = Field(attribute='Typ__muenztyptitel', column_name='Zitat')
    Typ__titel = Field(attribute='Typ__titel', column_name='Titel des Objektes')
    Typ__Herstellung__name = Field(attribute='Typ__Herstellung__name', column_name='Herstellung')
    Typ__Reichskreis__name = Field(attribute='Typ__Reichskreis__name', column_name='Reichskreis')
    Typ__Muenzstand__name = Field(attribute='Typ__Muenzstand__name', column_name='Münzstand')
    Typ__Nominal__name = Field(attribute='Typ__Nominal__name', column_name='Nominal')
    Typ__Metall__name = Field(attribute='Typ__Metall__name', column_name='Metall')
    Typ__Mzstaette__name = Field(attribute='Typ__Mzstaette__name', column_name='Münzstätte')
    Typ__region__name = Field(attribute='Typ__region__name', column_name='Region')
    Typ__dat_von = Field(attribute='Typ__dat_von', column_name='Datierung von')
    Typ__dat_bis = Field(attribute='Typ__dat_bis', column_name='Datierung bis')
    Typ__dat_verb = Field(attribute='Typ__dat_verb', column_name='Datierung')
    Typ__avleg = Field(attribute='Typ__avleg', column_name='Av.-Leg.')
    Typ__av_bildtyp__name = Field(attribute='Typ__av_bildtyp__name', column_name='Av.-Beschreibung')
    Typ__av_beizeichen__name = Field(attribute='Typ__av_beizeichen__name', column_name='Av.-Beizeichen')
    #Typ__av_offizin__name = Field(attribute='Typ__av_offizin__name', column_name='Av.-Offizin')
    Typ__rvleg = Field(attribute='Typ__rvleg', column_name='Rv.-Leg.')
    Typ__rv_bildtyp__name = Field(attribute='Typ__rv_bildtyp__name', column_name='Rv.-Beschreibung')
    Typ__rv_beizeichen__name = Field(attribute='Typ__rv_beizeichen__name', column_name='Rv.-Beizeichen')
    #Typ__rv_offizin__name = Field(attribute='Typ__rv_offizin__name', column_name='Rv.-Offizin')
    #Konkordanzen = Field(column_name='Konkordanzen', attribute=None)  # Attribut ist None, da dies ein benutzerdefiniertes Feld ist
    Zitate = Field(column_name='Zitat', attribute=None)  # Attribut ist None, da dies ein benutzerdefiniertes Feld ist

    class Meta:
        model = Obj
        # fields = ('id', 'invnr', 'Slg__name','SlgTeil__name', 'Objekttyp__name', 'Metall__name', 'Typ__muenztyptitel', 'Typ__titel')
        fields = ('id', 'invnr', 'Slg__name','SlgTeil__name', 'durchmesser','gewicht','stempelstellung', 'abnutzung', 'faelschung', 'Typ_unsicher', 'Zitate', 'Typ__titel', 'Typ__Herstellung__name', 'Typ__Reichskreis__name', 'Typ__Muenzstand__name', 'Typ__Nominal__name', 'Typ__Metall__name', 'Typ__Mzstaette__name', 'Typ__region__name', 'Typ__dat_von', 'Typ__dat_bis', 'Typ__dat_verb', 'Typ__avleg', 'Typ__av_bildtyp__name', 'Typ__av_beizeichen__name','Typ__rvleg', 'Typ__rv_bildtyp__name', 'Typ__rv_beizeichen__name', 'rv_offizin__name')
        export_order = ('id', 'invnr', 'Slg__name','SlgTeil__name', 'durchmesser','gewicht','stempelstellung', 'abnutzung', 'faelschung', 'Typ_unsicher', 'Zitate', 'Typ__titel', 'Typ__Herstellung__name', 'Typ__Reichskreis__name', 'Typ__Muenzstand__name', 'Typ__Nominal__name', 'Typ__Metall__name', 'Typ__Mzstaette__name', 'Typ__region__name', 'Typ__dat_von', 'Typ__dat_bis', 'Typ__dat_verb', 'Typ__avleg', 'Typ__av_bildtyp__name', 'Typ__av_beizeichen__name', 'Typ__rvleg', 'Typ__rv_bildtyp__name', 'Typ__rv_beizeichen__name', 'rv_offizin__name')
        name = "Export der Objekte"

    def dehydrate_Zitate(self, obj):
        if obj.Typ:
            konkordanz_list = [str(konkordanz) for konkordanz in obj.Typ.Konkordanz.all()]
            muenztyptitel = obj.Typ.muenztyptitel if obj.Typ.muenztyptitel else ''

            if konkordanz_list:
                konkordanz_str = '; '.join(konkordanz_list)
                return f"{muenztyptitel}; {konkordanz_str}"
            else:
                return muenztyptitel
        return ''

class SafeField(Field):
    def get_value(self, obj):
        try:
            return super().get_value(obj)
        except Fund.DoesNotExist:
            return None

class CachedForeignKeyWidget(ForeignKeyWidget):
    """
    Ein ForeignKeyWidget, das die Datenbankabfragen zwischenspeichert,
    um die Import-Geschwindigkeit drastisch zu verbessern.
    """
    def __init__(self, model, field='pk', *args, **kwargs):
        super().__init__(model, field=field, *args, **kwargs)
        self._cache = {}

    def clean(self, value, row=None, *args, **kwargs):
        # In older django-import-export versions, empty_values checking is done by the Field.
        # We can just do a basic check here.
        if value is None or value == '':
            return None

        if value not in self._cache:
            # Query the database only once per unique value
            self._cache[value] = super().clean(value, row, *args, **kwargs)

        return self._cache[value]

class ObjImport(resources.ModelResource):
    # Objekte werden über (invnr, Sammlung[, Sammlungsteil]) gefunden. Die id wird
    # nur exportiert; eine leere id-Spalte würde sonst beim Update pk=None setzen.
    id = fields.Field(attribute='id', column_name='id', readonly=True)

    Slg = fields.Field(
        column_name='Sammlung',
        attribute='Slg',
        widget=CachedForeignKeyWidget(Slg, field='name'))

    SlgTeil = fields.Field(
        column_name='Sammlungsteil',
        attribute='SlgTeil',
        widget=CachedForeignKeyWidget(SlgTeil, field='name'))

    Typ = fields.Field(
        column_name='Münztyp',
        attribute='Typ',
        widget=CachedForeignKeyWidget(Muenztyp, field='muenztyptitel'))

    # Defaults, falls before_import nicht (vollständig) läuft
    _instance_cache = None
    _import_invnr_values = frozenset()
    _import_slg_names = frozenset()
    _dry_run = True

    def import_data(self, dataset, dry_run=False, raise_errors=False, use_transactions=None, collect_failed_rows=False, **kwargs):
        # django-import-export 4.x übergibt dry_run nicht mehr an before_import.
        # Auto-Sync für die Dauer des Imports pausieren und in jedem Fall wieder
        # einschalten; danach einmal gebündelt synchronisieren (after_import).
        from slg.operations import operation
        from slg.signals import mtoa_sync_paused
        self._dry_run = dry_run
        with operation('admin_import', 'objects', dry_run=dry_run, rows=len(dataset)) as event:
            with mtoa_sync_paused():
                result = super().import_data(dataset, dry_run=dry_run, raise_errors=raise_errors,
                                             use_transactions=use_transactions,
                                             collect_failed_rows=collect_failed_rows, **kwargs)
            self._sync_imported_objects()
            if result.has_errors() or result.has_validation_errors():
                event['outcome'] = 'rejected'
            return result

    def before_import(self, dataset, **kwargs):
        self._instance_cache = None
        self._import_invnr_values = set()
        self._import_slg_names = set()

        try:
            invnr_col = self.fields['invnr'].column_name
            slg_col = self.fields['Slg'].column_name

            for row_dict in dataset.dict:
                inv = row_dict.get(invnr_col, '')
                slg = row_dict.get(slg_col, '')
                if inv:
                    self._import_invnr_values.add(str(inv).strip())
                if slg:
                    self._import_slg_names.add(str(slg).strip())

            if self._import_slg_names and self._import_invnr_values:
                slg_map = {s.name: s for s in Slg.objects.filter(name__in=self._import_slg_names)}
                slg_ids = [s.id for s in slg_map.values()]

                if slg_ids:
                    self._instance_cache = {}
                    qs = Obj.objects.filter(
                        Slg_id__in=slg_ids,
                        invnr__in=self._import_invnr_values
                    ).select_related('Slg', 'SlgTeil', 'Typ')
                    for obj in qs:
                        key = (str(obj.invnr).strip(), obj.Slg_id)
                        self._instance_cache.setdefault(key, []).append(obj)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Pre-Cache konnte nicht erstellt werden, verwende Standard-Lookup",
                exc_info=True
            )
            self._instance_cache = None

        super().before_import(dataset, **kwargs)

    def _sync_imported_objects(self):
        if not self._dry_run and self._import_slg_names and self._import_invnr_values:
            try:
                slg_ids = list(
                    Slg.objects.filter(name__in=self._import_slg_names)
                    .values_list('id', flat=True)
                )
                if slg_ids:
                    imported_pks = list(
                        Obj.objects.filter(
                            Slg_id__in=slg_ids,
                            invnr__in=self._import_invnr_values
                        ).values_list('pk', flat=True)
                    )
                    if imported_pks:
                        from .mtoa_sync import sync_objs_to_mtoa
                        for i in range(0, len(imported_pks), 500):
                            sync_objs_to_mtoa(imported_pks[i:i + 500])
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "MTOA Batch-Sync nach Import fehlgeschlagen"
                )

    class Meta:
        model = Obj
        fields = ('id', 'invnr', 'Slg', 'SlgTeil', 'Typ', 'TempTyp', 'durchmesser', 'gewicht', 'stempelstellung', 'abnutzung',)
        export_order = fields
        name = "Export der Objekte"
        skip_unchanged = True
        report_skipped = True
        use_bulk = True
        batch_size = 500
        # Bulk-Import ohne Transaktion hinterließ bei Fehlern Teilimporte.
        use_transactions = True

    def get_import_id_fields(self):
        # Pro Resource-Instanz (= pro Import) statt über die geteilte Meta-Klasse:
        # Fundmünzprojekt-Zeilen identifizieren sich zusätzlich über SlgTeil.
        return list(getattr(self, '_current_id_fields', None) or ['invnr', 'Slg'])

    def before_import_row(self, row, **kwargs):
        sammlung_name = row.get('Sammlung', '')
        if sammlung_name == 'Fundmünzprojekt':
            self._current_id_fields = ['invnr', 'Slg', 'SlgTeil']
        else:
            self._current_id_fields = ['invnr', 'Slg']

    def get_or_init_instance(self, instance_loader, row):
        if self._instance_cache is not None:
            try:
                invnr_val = self.fields['invnr'].clean(row)
                if invnr_val:
                    invnr_val = str(invnr_val).strip()
            except Exception:
                invnr_val = None

            try:
                slg_obj = self.fields['Slg'].clean(row)
            except Exception:
                slg_obj = None

            if slg_obj and invnr_val:
                key = (invnr_val, slg_obj.id)
                candidates = self._instance_cache.get(key, [])

                if candidates:
                    if hasattr(self, '_current_id_fields') and 'SlgTeil' in self._current_id_fields:
                        try:
                            slgteil_obj = self.fields['SlgTeil'].clean(row)
                        except Exception:
                            slgteil_obj = None
                        slgteil_id = slgteil_obj.id if slgteil_obj else None
                        for obj in candidates:
                            if obj.SlgTeil_id == slgteil_id:
                                return obj, False
                    else:
                        return candidates[0], False

            return self.Meta.model(), True

        # Fallback ohne Cache: get_import_id_fields() berücksichtigt _current_id_fields.
        return super().get_or_init_instance(instance_loader, row)
