"""
Management-Command: sync_mtoa

Synchronisiert alle Obj-Instanzen in die MuenztypObjektAnzeige-Tabelle.
Lädt alle benötigten Daten batch-weise mit optimierten Queries.

Verwendung:
    python manage.py sync_mtoa                    # Alles synchronisieren
    python manage.py sync_mtoa --slg 5            # Nur Sammlung mit ID 5
    python manage.py sync_mtoa --since 2025-01-01 # Nur seit einem Datum geänderte
    python manage.py sync_mtoa --force             # Alle vorhandenen MTOA-Einträge löschen & neu erstellen
"""

from django.core.management.base import BaseCommand
from django.db.models import Prefetch
from django.utils import timezone
from datetime import datetime

from slg.models import (
    Obj, MuenztypObjektAnzeige, MtoaPerson, Obj_Person,
    Mztyp_Person, AvBildtyp_Schlagwort, RvBildtyp_Schlagwort,
)


BATCH_SIZE = 500


def build_optimized_queryset(base_qs):
    """
    Baut ein optimiertes Queryset, das ALLE FK-Daten vorlädt,
    damit generate_mtoa_data() KEINE zusätzlichen Queries braucht.
    """
    return base_qs.select_related(
        'Slg', 'SlgTeil',
        'Typ',
        'Typ__Objekttyp', 'Typ__Herstellung', 'Typ__Reichskreis',
        'Typ__Muenzstand', 'Typ__Nominal', 'Typ__Metall',
        'Typ__Mzstaette', 'Typ__region',
        'Typ__av_bildtyp', 'Typ__rv_bildtyp',
        'Typ__av_beizeichen', 'Typ__rv_beizeichen',
        'Typ__av_bildrand', 'Typ__rv_bildrand',
        'Typ__rand', 'Typ__workflow',
        # Direkte FK-Felder vom Obj
        'Objekttyp', 'idfk_Herstellung', 'idfk_Muenzstand',
        'idfk_Nominal', 'Metall', 'idfk_Mzstaette', 'region',
        'av_bildtyp', 'rv_bildtyp',
        'av_beizeichen', 'rv_beizeichen',
        'av_offizin', 'rv_offizin',
        'av_bildrand', 'rv_bildrand',
        'rand', 'workflow',
    ).prefetch_related(
        Prefetch(
            'Typ__mztyp_person_set',
            queryset=Mztyp_Person.objects.select_related(
                'idfk_Person', 'idfk_PersonFunktion'
            )
        ),
        Prefetch(
            'obj_person_set',
            queryset=Obj_Person.objects.select_related(
                'idfk_Person', 'idfk_PersonFunktion'
            )
        ),
        'Typ__Konkordanz',
    )


def generate_mtoa_from_obj(obj, av_sw_map=None, rv_sw_map=None):
    """
    Generiert MTOA-Daten aus einem Obj.
    Nutzt vorgefetchte Daten (select_related/prefetch_related)
    und optionale Schlagwort-Maps (av_sw_map, rv_sw_map)
    statt eigener DB-Queries.
    """
    urls = obj.get_bild_urls() or {}

    # Personen aus den vorgefetchten relations
    if obj.Typ:
        try:
            all_persons = list(obj.Typ.mztyp_person_set.all())
        except AttributeError:
            all_persons = []
    else:
        try:
            all_persons = list(obj.obj_person_set.all())
        except AttributeError:
            all_persons = []
            
    persons_to_link = []
    for mp in all_persons:
        persons_to_link.append({
            'person_id': mp.idfk_Person_id,
            'funktion_id': mp.idfk_PersonFunktion_id,
            'appears_on_rev': mp.appears_on_rev
        })

    personen_av = ' | '.join(
        f"{mp.idfk_Person}: {mp.idfk_PersonFunktion} ({mp.idfk_PersonFunktion_id})"
        for mp in all_persons
        if not mp.appears_on_rev and mp.idfk_PersonFunktion_id == 2
    )
    personen_rv = ' | '.join(
        f"{mp.idfk_Person}: {mp.idfk_PersonFunktion} ({mp.idfk_PersonFunktion_id})"
        for mp in all_persons
        if mp.appears_on_rev and mp.idfk_PersonFunktion_id == 2
    )
    sonstige_personen = ' | '.join(
        f"{mp.idfk_Person}: {mp.idfk_PersonFunktion} ({mp.idfk_PersonFunktion_id})"
        for mp in all_persons
        if mp.idfk_PersonFunktion_id != 2
    )

    try:
        konkordanz_liste = ' | '.join(
            str(k) for k in obj.Typ.Konkordanz.all()
        )
    except AttributeError:
        konkordanz_liste = ''

    # Schlagworte aus den vorab geladenen Maps
    av_bt_id = obj.av_bildtyp_id or (obj.Typ.av_bildtyp_id if obj.Typ else None)
    rv_bt_id = obj.rv_bildtyp_id or (obj.Typ.rv_bildtyp_id if obj.Typ else None)

    av_schlagworte = ''
    rv_schlagworte = ''
    if av_bt_id and av_sw_map:
        av_schlagworte = av_sw_map.get(av_bt_id, '')
    if rv_bt_id and rv_sw_map:
        rv_schlagworte = rv_sw_map.get(rv_bt_id, '')

    # Beizeichen-Logik (Offizin-Ersetzung)
    rv_beizeichen = obj.rv_beizeichen.name if obj.rv_beizeichen else ''
    if not rv_beizeichen and obj.Typ and obj.Typ.rv_beizeichen:
        rv_beizeichen = obj.Typ.rv_beizeichen.name
    if obj.rv_offizin:
        rv_beizeichen = rv_beizeichen.replace('?', obj.rv_offizin.name)

    av_beizeichen = obj.av_beizeichen.name if obj.av_beizeichen else ''
    if not av_beizeichen and obj.Typ and obj.Typ.av_beizeichen:
        av_beizeichen = obj.Typ.av_beizeichen.name
    if obj.av_offizin:
        av_beizeichen = av_beizeichen.replace('?', obj.av_offizin.name)

    typ = obj.Typ
    
    data = {
        'obj_id': obj.id,
        'invnr': obj.invnr,
        'objekttitel': obj.titel or (typ.titel if typ and typ.titel else None),
        'objekttyp': obj.Objekttyp.name if obj.Objekttyp else (typ.Objekttyp.name if typ and typ.Objekttyp else None),
        'herstellung': obj.idfk_Herstellung.name if obj.idfk_Herstellung else (typ.Herstellung.name if typ and typ.Herstellung else None),
        'reichskreis': typ.Reichskreis.name if typ and typ.Reichskreis else None,
        'muenzstand': obj.idfk_Muenzstand.name if obj.idfk_Muenzstand else (typ.Muenzstand.name if typ and typ.Muenzstand else None),
        'nominal': obj.idfk_Nominal.name if obj.idfk_Nominal else (typ.Nominal.name if typ and typ.Nominal else None),
        'metall': obj.Metall.name if obj.Metall else (typ.Metall.name if typ and typ.Metall else None),
        'mzstaette': obj.idfk_Mzstaette.name if obj.idfk_Mzstaette else (typ.Mzstaette.name if typ and typ.Mzstaette else None),
        'region': obj.region.name if obj.region else (typ.region.name if typ and typ.region else None),
        'datierung_von': obj.dat_von or (typ.dat_von if typ else None),
        'datierung_bis': obj.dat_bis or (typ.dat_bis if typ else None),
        'datierung_verbale': obj.dat_verb or (typ.dat_verb if typ else None),
        'durchmesser': obj.durchmesser,
        'gewicht': obj.gewicht,
        'stempelstellung': obj.stempelstellung,
        'abnutzung': obj.abnutzung,
        'av_legende': obj.avleg or (typ.avleg if typ else None),
        'av_bildtyp': obj.av_bildtyp.name if obj.av_bildtyp else (typ.av_bildtyp.name if typ and typ.av_bildtyp else None),
        'av_beizeichen': av_beizeichen,
        'av_bildrand': obj.av_bildrand.name if obj.av_bildrand else (typ.av_bildrand.name if typ and typ.av_bildrand else None),
        'av_schlagworte': av_schlagworte,
        'rv_legende': obj.rvleg or (typ.rvleg if typ else None),
        'rv_bildtyp': obj.rv_bildtyp.name if obj.rv_bildtyp else (typ.rv_bildtyp.name if typ and typ.rv_bildtyp else None),
        'rv_beizeichen': rv_beizeichen,
        'rv_bildrand': obj.rv_bildrand.name if obj.rv_bildrand else (typ.rv_bildrand.name if typ and typ.rv_bildrand else None),
        'rv_schlagworte': rv_schlagworte,
        'rand': obj.rand.name if obj.rand else (typ.rand.name if typ and typ.rand else None),
        'anmerkungen': obj.anmerkung or (typ.anmerkung if typ else None),
        'typ': typ.muenztyptitel if typ and typ.muenztyptitel else None,
        'typlink': typ.link if typ and hasattr(typ, 'link') and typ.link else None,
        'personen_av': personen_av,
        'personen_rv': personen_rv,
        'personen_sonstige': sonstige_personen,
        'konkordanz': konkordanz_liste,
        'last_modified': timezone.now(),
        'av_url': urls.get('av'),
        'rv_url': urls.get('rv'),
        'thumbnail_av_url': urls.get('thumbnail_av'),
        'thumbnail_rv_url': urls.get('thumbnail_rv'),
        'SlgTeil': obj.SlgTeil.name if obj.SlgTeil else None,
        'Slg': obj.Slg.name if obj.Slg else None,
        # FK-IDs für effizientes Filtern (Obj → Typ Fallback)
        'nominal_fk_id': obj.idfk_Nominal_id or (typ.Nominal_id if typ else None),
        'metall_fk_id': obj.Metall_id or (typ.Metall_id if typ else None),
        'mzstaette_fk_id': obj.idfk_Mzstaette_id or (typ.Mzstaette_id if typ else None),
        'region_fk_id': obj.region_id or (typ.region_id if typ else None),
        'muenzstand_fk_id': obj.idfk_Muenzstand_id or (typ.Muenzstand_id if typ else None),
        'objekttyp_fk_id': obj.Objekttyp_id or (typ.Objekttyp_id if typ else None),
        'herstellung_fk_id': obj.idfk_Herstellung_id or (typ.Herstellung_id if typ else None),
        'av_bildtyp_fk_id': av_bt_id,
        'rv_bildtyp_fk_id': rv_bt_id,
        'slg_fk_id': obj.Slg_id,
        'slgteil_fk_id': obj.SlgTeil_id,
        'typ_fk_id': obj.Typ_id,
    }
    
    return data, persons_to_link


def build_schlagwort_maps():
    """
    Lädt ALLE Schlagwort-Zuordnungen in zwei Dicts,
    damit wir während der Batch-Verarbeitung KEINE Queries brauchen.
    """
    av_sw_map = {}
    for entry in AvBildtyp_Schlagwort.objects.select_related('schlagwort').all():
        av_sw_map.setdefault(entry.avbildtyp_id, []).append(str(entry.schlagwort))
    av_sw_map = {k: ', '.join(v) for k, v in av_sw_map.items()}

    rv_sw_map = {}
    for entry in RvBildtyp_Schlagwort.objects.select_related('schlagwort').all():
        rv_sw_map.setdefault(entry.rvbildtyp_id, []).append(str(entry.schlagwort))
    rv_sw_map = {k: ', '.join(v) for k, v in rv_sw_map.items()}

    return av_sw_map, rv_sw_map


class Command(BaseCommand):
    help = 'Synchronisiert alle Obj-Instanzen in die MuenztypObjektAnzeige-Tabelle.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--slg', type=int, default=None,
            help='Nur Objekte einer bestimmten Sammlung synchronisieren (Slg-ID)'
        )
        parser.add_argument(
            '--since', type=str, default=None,
            help='Nur seit einem bestimmten Datum geänderte Objekte (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Alle vorhandenen MTOA-Einträge löschen und neu erstellen'
        )

    def handle(self, *args, **options):
        slg_id = options['slg']
        since = options['since']
        force = options['force']
        verbosity = options['verbosity']

        # 1. Schlagwort-Maps vorladen (2 Queries statt N)
        if verbosity >= 1:
            self.stdout.write('Lade Schlagwort-Zuordnungen...')
        av_sw_map, rv_sw_map = build_schlagwort_maps()
        if verbosity >= 1:
            self.stdout.write(f'  AV: {len(av_sw_map)} Bildtypen, RV: {len(rv_sw_map)} Bildtypen')

        # 2. Basis-Queryset aufbauen
        base_qs = Obj.objects.all()
        if slg_id:
            base_qs = base_qs.filter(Slg_id=slg_id)
            if verbosity >= 1:
                self.stdout.write(f'Filter: Nur Sammlung ID={slg_id}')
        if since:
            since_dt = datetime.strptime(since, '%Y-%m-%d')
            since_dt = timezone.make_aware(since_dt) if timezone.is_naive(since_dt) else since_dt
            base_qs = base_qs.filter(modified_at__gte=since_dt)
            if verbosity >= 1:
                self.stdout.write(f'Filter: Nur seit {since} geänderte Objekte')

        total = base_qs.count()
        if verbosity >= 1:
            self.stdout.write(f'Zu synchronisierende Objekte: {total}')

        if total == 0:
            self.stdout.write(self.style.SUCCESS('Keine Objekte zu synchronisieren.'))
            return

        # 3. Bei --force: Alle bestehenden MTOA-Einträge löschen
        if force:
            if slg_id:
                deleted, _ = MuenztypObjektAnzeige.objects.filter(
                    obj_id__in=base_qs.values_list('id', flat=True)
                ).delete()
            else:
                deleted, _ = MuenztypObjektAnzeige.objects.all().delete()
            if verbosity >= 1:
                self.stdout.write(f'  {deleted} bestehende MTOA-Einträge gelöscht.')

        # 4. Vorhandene MTOA-Einträge laden (obj_id → mtoa.id Mapping)
        existing_map = {}
        if not force:
            existing_map = dict(
                MuenztypObjektAnzeige.objects
                .filter(obj_id__isnull=False)
                .values_list('obj_id', 'id')
            )
            if verbosity >= 2:
                self.stdout.write(f'  {len(existing_map)} bestehende MTOA-Einträge gefunden.')

        # 5. Optimiertes Queryset aufbauen
        optimized_qs = build_optimized_queryset(base_qs)

        # 6. Batch-Verarbeitung
        to_create = []
        to_update = []
        obj_to_persons = {}
        processed = 0

        for obj in optimized_qs.iterator(chunk_size=BATCH_SIZE):
            data, persons = generate_mtoa_from_obj(obj, av_sw_map, rv_sw_map)
            obj_to_persons[obj.id] = persons

            if obj.id in existing_map:
                # Update: Bestehendes MTOA-Objekt modifizieren
                mtoa = MuenztypObjektAnzeige(id=existing_map[obj.id], **data)
                to_update.append(mtoa)
            else:
                # Create: Neues MTOA-Objekt
                to_create.append(MuenztypObjektAnzeige(**data))

            processed += 1
            
            # Wenn Batch voll ist
            if (len(to_create) + len(to_update)) >= BATCH_SIZE:
                self._flush_batch(to_create, to_update, obj_to_persons, existing_map)
                to_create = []
                to_update = []
                obj_to_persons = {}

            if verbosity >= 1 and processed % 1000 == 0:
                self.stdout.write(f'  {processed}/{total} verarbeitet...')

        # Restliche Batches schreiben
        if to_create or to_update:
            self._flush_batch(to_create, to_update, obj_to_persons, existing_map)

        created_count = processed - len(existing_map) if not force else processed
        updated_count = len(existing_map) if not force else 0

        self.stdout.write(self.style.SUCCESS(
            f'Fertig! {processed} Objekte verarbeitet '
            f'({created_count} neu erstellt, {updated_count} aktualisiert).'
        ))

    def _flush_batch(self, to_create, to_update, obj_to_persons, existing_map):
        from slg.models import MuenztypObjektAnzeige, MtoaPerson
        
        # 1. MTOA Objekte speichern
        if to_create:
            MuenztypObjektAnzeige.objects.bulk_create(to_create)
        if to_update:
            update_fields = [f.name for f in MuenztypObjektAnzeige._meta.get_fields()
                             if hasattr(f, 'column') and f.name != 'id']
            MuenztypObjektAnzeige.objects.bulk_update(to_update, update_fields, batch_size=BATCH_SIZE)
            
        # 2. MTOA IDs abrufen
        batch_obj_ids = list(obj_to_persons.keys())
        mtoa_qs = MuenztypObjektAnzeige.objects.filter(obj_id__in=batch_obj_ids)
        mtoa_map = {mtoa.obj_id: mtoa.id for mtoa in mtoa_qs}
        
        # 3. MtoaPerson Bridging Tabelle leeren (für Updates)
        MtoaPerson.objects.filter(mtoa_id__in=mtoa_map.values()).delete()
        
        # 4. Neue MtoaPerson Relationen aufbauen
        mtoa_persons_to_create = []
        for obj_id, persons in obj_to_persons.items():
            mtoa_id = mtoa_map.get(obj_id)
            if mtoa_id:
                for p in persons:
                    mtoa_persons_to_create.append(MtoaPerson(
                        mtoa_id=mtoa_id,
                        person_id=p['person_id'],
                        funktion_id=p['funktion_id'],
                        appears_on_rev=p['appears_on_rev']
                    ))
        
        if mtoa_persons_to_create:
            MtoaPerson.objects.bulk_create(mtoa_persons_to_create, batch_size=2000)
