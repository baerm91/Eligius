"""
Shared MTOA-Sync-Logik.

Wird verwendet von:
- signals.py (Auto-Sync bei Save)
- admin.py (Admin-Aktion)
- management/commands/sync_mtoa.py (Batch-Sync)
"""

import logging
from django.db import connection, models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _mtoa_model():
    from .models import MuenztypObjektAnzeige
    return MuenztypObjektAnzeige


def update_fields():
    return [f.name for f in _mtoa_model()._meta.concrete_fields if f.name != 'id']


def fit_lengths(data):
    """Kürzt Texte auf die Spaltenlänge der MTOA.

    Ein einziger zu langer Wert (MySQL DataError 1406) würde sonst den ganzen
    500er-Batch abbrechen. Die Quellfelder sind lesbar im Objekt; die MTOA ist
    nur eine Anzeigeprojektion.
    """
    model = _mtoa_model()
    for name, value in data.items():
        if isinstance(value, str):
            try:
                field = model._meta.get_field(name)
            except Exception:
                continue
            if isinstance(field, models.CharField) and field.max_length and len(value) > field.max_length:
                logger.warning('MTOA-Feld %s für Obj %s auf %d Zeichen gekürzt', name, data.get('obj_id'), field.max_length)
                data[name] = value[:field.max_length]
    return data


def save_projections(to_create, to_update, batch_size=500):
    """Schreibt MTOA-Zeilen; obj_id ist eindeutig, parallele Erstanlagen werden zu Updates."""
    model = _mtoa_model()
    fields = update_fields()
    if to_create:
        kwargs = {'update_conflicts': True, 'update_fields': [f for f in fields if f != 'obj_id']}
        if connection.features.supports_update_conflicts_with_target:
            kwargs['unique_fields'] = ['obj_id']
        model.objects.bulk_create(to_create, batch_size=batch_size, **kwargs)
    if to_update:
        model.objects.bulk_update(to_update, fields, batch_size=batch_size)
    if to_create or to_update:
        _invalidate_browse_cache()


def _invalidate_browse_cache():
    """Gecachte Browse-Zahlen/Facetten nach dem Commit verwerfen (sonst könnte
    eine parallele Anfrage alte Daten unter der neuen Generation ablegen)."""
    from slg.services import browse_cache
    transaction.on_commit(browse_cache.invalidate)


def replace_projection_persons(obj_to_persons):
    """Ersetzt die MtoaPerson-Zeilen der gegebenen Objekte."""
    from .models import MtoaPerson
    mtoa_map = dict(_mtoa_model().objects.filter(obj_id__in=list(obj_to_persons)).values_list('obj_id', 'id'))
    MtoaPerson.objects.filter(mtoa_id__in=list(mtoa_map.values())).delete()
    rows = [
        MtoaPerson(mtoa_id=mtoa_map[obj_id], person_id=p['person_id'], funktion_id=p['funktion_id'],
                   appears_on_rev=p['appears_on_rev'])
        for obj_id, persons in obj_to_persons.items() if obj_id in mtoa_map
        for p in persons
    ]
    if rows:
        MtoaPerson.objects.bulk_create(rows, batch_size=2000)
    return len(rows)


def _build_schlagwort_maps_for_ids(av_bt_ids, rv_bt_ids):
    """
    Lädt Schlagwort-Zuordnungen nur für die angegebenen Bildtyp-IDs.
    Viel effizienter als build_schlagwort_maps() bei wenigen Objekten.
    """
    from .models import AvBildtyp_Schlagwort, RvBildtyp_Schlagwort

    av_sw_map = {}
    if av_bt_ids:
        for entry in AvBildtyp_Schlagwort.objects.filter(
            avbildtyp_id__in=av_bt_ids
        ).select_related('schlagwort'):
            av_sw_map.setdefault(entry.avbildtyp_id, []).append(str(entry.schlagwort))
        av_sw_map = {k: ', '.join(v) for k, v in av_sw_map.items()}

    rv_sw_map = {}
    if rv_bt_ids:
        for entry in RvBildtyp_Schlagwort.objects.filter(
            rvbildtyp_id__in=rv_bt_ids
        ).select_related('schlagwort'):
            rv_sw_map.setdefault(entry.rvbildtyp_id, []).append(str(entry.schlagwort))
        rv_sw_map = {k: ', '.join(v) for k, v in rv_sw_map.items()}

    return av_sw_map, rv_sw_map


@transaction.atomic
def sync_objs_to_mtoa(obj_ids):
    """
    Synchronisiert eine Liste von Obj-IDs in die MuenztypObjektAnzeige-Tabelle.
    Effizient für einzelne Objekte und kleine Batches.
    """
    from .models import Obj, MuenztypObjektAnzeige
    from .management.commands.sync_mtoa import (
        build_optimized_queryset, generate_mtoa_from_obj, build_schlagwort_maps
    )

    if not obj_ids:
        return 0, 0  # Aufrufer entpacken (created, updated)

    if isinstance(obj_ids, int):
        obj_ids = [obj_ids]
    obj_ids = list(obj_ids)

    optimized_qs = build_optimized_queryset(
        Obj.objects.filter(pk__in=obj_ids)
    )

    if len(obj_ids) <= 50:
        bt_ids = optimized_qs.values_list(
            'av_bildtyp_id', 'rv_bildtyp_id',
            'Typ__av_bildtyp_id', 'Typ__rv_bildtyp_id',
        )
        av_bt_ids = set()
        rv_bt_ids = set()
        for av1, rv1, av2, rv2 in bt_ids:
            if av1: av_bt_ids.add(av1)
            if av2: av_bt_ids.add(av2)
            if rv1: rv_bt_ids.add(rv1)
            if rv2: rv_bt_ids.add(rv2)
        av_sw_map, rv_sw_map = _build_schlagwort_maps_for_ids(av_bt_ids, rv_bt_ids)
        optimized_qs = build_optimized_queryset(
            Obj.objects.filter(pk__in=obj_ids)
        )
    else:
        av_sw_map, rv_sw_map = build_schlagwort_maps()

    existing_map = dict(
        MuenztypObjektAnzeige.objects
        .filter(obj_id__in=obj_ids)
        .values_list('obj_id', 'id')
    )

    to_create = []
    to_update = []
    obj_to_persons = {}

    for obj in optimized_qs:
        data, persons = generate_mtoa_from_obj(obj, av_sw_map, rv_sw_map)
        obj_to_persons[obj.id] = persons

        if obj.id in existing_map:
            mtoa = MuenztypObjektAnzeige(id=existing_map[obj.id], **data)
            to_update.append(mtoa)
        else:
            to_create.append(MuenztypObjektAnzeige(**data))

    save_projections(to_create, to_update)
    person_links = replace_projection_persons(obj_to_persons)

    # Gelöschte Objekte: Projektion entfernen, sonst bleiben 404-Geister in /browse/.
    removed, _ = MuenztypObjektAnzeige.objects.filter(obj_id__in=obj_ids).exclude(
        obj_id__in=list(obj_to_persons)).delete()

    logger.info(
        "MTOA-Sync: %d Objekte verarbeitet (%d neu, %d aktualisiert, %d entfernt, %d Personen-Links)",
        len(obj_ids), len(to_create), len(to_update), removed, person_links
    )
    return len(to_create), len(to_update)
