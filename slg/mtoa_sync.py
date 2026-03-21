"""
Shared MTOA-Sync-Logik.

Wird verwendet von:
- signals.py (Auto-Sync bei Save)
- admin.py (Admin-Aktion)
- management/commands/sync_mtoa.py (Batch-Sync)
"""

import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


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


def sync_objs_to_mtoa(obj_ids):
    """
    Synchronisiert eine Liste von Obj-IDs in die MuenztypObjektAnzeige-Tabelle.
    Effizient für einzelne Objekte und kleine Batches.
    """
    from .models import Obj, MuenztypObjektAnzeige, MtoaPerson
    from .management.commands.sync_mtoa import (
        build_optimized_queryset, generate_mtoa_from_obj, build_schlagwort_maps
    )

    if not obj_ids:
        return

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

    if to_create:
        MuenztypObjektAnzeige.objects.bulk_create(to_create)
    if to_update:
        update_fields = [
            f.name for f in MuenztypObjektAnzeige._meta.get_fields()
            if hasattr(f, 'column') and f.name != 'id'
        ]
        MuenztypObjektAnzeige.objects.bulk_update(to_update, update_fields, batch_size=500)

    mtoa_qs = MuenztypObjektAnzeige.objects.filter(obj_id__in=obj_ids)
    mtoa_map = {mtoa.obj_id: mtoa.id for mtoa in mtoa_qs}

    MtoaPerson.objects.filter(mtoa_id__in=mtoa_map.values()).delete()

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

    logger.info(
        "MTOA-Sync: %d Objekte verarbeitet (%d neu, %d aktualisiert, %d Personen-Links)",
        len(obj_ids), len(to_create), len(to_update), len(mtoa_persons_to_create)
    )
    return len(to_create), len(to_update)
