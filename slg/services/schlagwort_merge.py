"""Merge catalogue keywords and refresh only the affected search text."""
import hashlib
import json
from collections import defaultdict
from itertools import islice

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Case, Q, TextField, Value, When
from django.db.models.functions import Coalesce

from slg.models import (
    AvBildtyp_Schlagwort,
    MuenztypObjektAnzeige,
    Mztyp_Schlagwort,
    Obj,
    RvBildtyp_Schlagwort,
    Schlagwort,
)
from slg.mtoa_sync import _build_schlagwort_maps_for_ids

RELATIONS = (
    (AvBildtyp_Schlagwort, 'avbildtyp_id'),
    (RvBildtyp_Schlagwort, 'rvbildtyp_id'),
    (Mztyp_Schlagwort, 'mztyp_id'),
)
METADATA = {'name_en': 'Englische Übersetzung', 'name_nom_id': 'Nomisma-ID oder -URL'}


def lock_keyword_writes():
    # Serialize admin naming checks and merges before locking individual keywords.
    content_type = ContentType.objects.get_for_model(Schlagwort)
    ContentType.objects.select_for_update().only('pk').get(pk=content_type.pk)


def merge_preview(ids, *, lock=False):
    keywords = Schlagwort.objects.filter(pk__in=ids).order_by('pk')
    if lock:
        keywords = keywords.select_for_update()

    selected = list(keywords)
    if len(selected) < 2 or len(selected) != len(ids):
        raise ValueError('Wählen Sie mindestens zwei vorhandene Schlagworte aus.')

    counts = {keyword.pk: [0, 0, 0] for keyword in selected}
    links = []
    for index, (model, owner_field) in enumerate(RELATIONS):
        queryset = model.objects.filter(schlagwort_id__in=ids).order_by('pk')
        if lock:
            queryset = queryset.select_for_update()
        rows = list(queryset.values_list('pk', owner_field, 'schlagwort_id'))
        links.append(rows)
        for _, _, keyword_id in rows:
            counts[keyword_id][index] += 1
    metadata = {
        field: list(dict.fromkeys(getattr(keyword, field) for keyword in selected if getattr(keyword, field)))
        for field in METADATA
    }
    snapshot = {
        'schlagworte': [
            {'id': keyword.pk, 'name': keyword.name, **{field: getattr(keyword, field) for field in METADATA}}
            for keyword in selected
        ],
        'verknuepfungen': {model._meta.model_name: rows for (model, _), rows in zip(RELATIONS, links)},
    }
    revision = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False).encode()).hexdigest()
    return selected, counts, metadata, links, snapshot, revision


def _move_links(model, owner_field, rows, target_id):
    # Keep an existing target link first, otherwise retain the oldest source link.
    owners = {owner for _, owner, keyword in rows if keyword == target_id}
    moved, duplicate_ids, affected = [], [], set()
    for link_id, owner, keyword in rows:
        if keyword == target_id:
            continue
        affected.add(owner)
        if owner in owners:
            duplicate_ids.append(link_id)
        else:
            owners.add(owner)
            moved.append(model(pk=link_id, schlagwort_id=target_id, **{owner_field: owner}))

    if duplicate_ids:
        model.objects.filter(pk__in=duplicate_ids).delete()
    if moved:
        model.objects.bulk_update(moved, ['schlagwort'], batch_size=250)
    return affected


def _update_search_keywords(av_ids, rv_ids):
    maps = _build_schlagwort_maps_for_ids(av_ids, rv_ids)
    for side, affected_ids, labels in zip(('av', 'rv'), (av_ids, rv_ids), maps):
        if not affected_ids:
            continue
        field = f'{side}_bildtyp_id'
        objects = Obj.objects.filter(
            Q(**{f'{field}__in': affected_ids}) |
            Q(**{f'{field}__isnull': True, f'Typ__{field}__in': affected_ids})
        ).annotate(keyword_owner=Coalesce(field, f'Typ__{field}')).order_by('pk')
        rows = objects.values_list('pk', 'keyword_owner').iterator(chunk_size=500)
        while batch := list(islice(rows, 500)):
            grouped = defaultdict(list)
            for obj_id, owner_id in batch:
                grouped[labels.get(owner_id, '')].append(obj_id)
            values = [When(obj_id__in=ids, then=Value(label)) for label, ids in grouped.items()]
            MuenztypObjektAnzeige.objects.filter(obj_id__in=[pk for pk, _ in batch]).update(
                **{f'{side}_schlagworte': Case(*values, output_field=TextField())},
            )


@transaction.atomic
def merge_keywords(ids, target_id, choices, expected_revision):
    lock_keyword_writes()
    selected, _, metadata, links, snapshot, revision = merge_preview(ids, lock=True)
    if revision != expected_revision:
        raise ValueError('Die Schlagworte oder Verknüpfungen wurden geändert. Starten Sie die Aktion erneut.')
    target = next((keyword for keyword in selected if keyword.pk == target_id), None)
    if target is None:
        raise ValueError('Das Ziel muss zu den ausgewählten Schlagworten gehören.')

    for field, values in metadata.items():
        value = choices.get(field) if len(values) > 1 else next(iter(values), '')
        if len(values) > 1 and value not in values:
            raise ValueError(f'Wählen Sie einen gültigen Wert für {METADATA[field]}.')
        setattr(target, field, value)

    affected = [
        _move_links(model, owner_field, rows, target.pk)
        for (model, owner_field), rows in zip(RELATIONS, links)
    ]
    target.save(update_fields=list(METADATA))
    Schlagwort.objects.filter(pk__in=ids).exclude(pk=target.pk).delete()
    _update_search_keywords(*affected[:2])
    snapshot['ziel'] = {'id': target.pk, **{field: getattr(target, field) for field in METADATA}}
    return target, snapshot
