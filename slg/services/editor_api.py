"""Domain-limited editor operations. No preview persistence or schema changes."""
import hashlib
import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers

from slg.models import Obj, Muenztyp, Paket, Workflow

SALT = 'eligius.editor.preview.v1'
MAX_AGE = 600
MAX_BULK = 100
TYPE_FIELDS = (
    'titel',
    'link',
    'Mzstaette', 'Nominal', 'Metall', 'dat_von', 'dat_bis', 'dat_verb',
    'avleg', 'rvleg', 'avbeschr', 'rvbeschr', 'av_bildtyp', 'rv_bildtyp',
    'av_beizeichen', 'rv_beizeichen', 'av_offizin_symbol', 'rv_offizin_symbol',
)
UNIDENTIFIED_FIELDS = (
    'idfk_Mzstaette', 'idfk_Nominal', 'Metall', 'dat_von', 'dat_bis', 'dat_verb',
    'avleg', 'rvleg', 'avbeschr', 'rvbeschr', 'av_bildtyp', 'rv_bildtyp',
    'av_beizeichen', 'rv_beizeichen', 'av_offizin', 'rv_offizin',
    'av_offizin_symbol', 'rv_offizin_symbol',
)
OPERATIONS = {
    'assign_coin_type': (Obj, ('Typ', 'Typ_unsicher')),
    'remove_coin_type': (Obj, ('Typ',)),
    'update_unidentified_object_data': (Obj, UNIDENTIFIED_FIELDS),
    'update_unidentified_legend': (Obj, ('avleg', 'rvleg')),
    'update_object_measurements': (Obj, ('gewicht', 'durchmesser', 'stempelstellung')),
    'update_object_note': (Obj, ('anmerkung',)),
    'update_coin_type': (Muenztyp, TYPE_FIELDS),
    'update_coin_type_legend': (Muenztyp, ('avleg', 'rvleg')),
    'set_object_workflow_status': (Obj, ('workflow',)),
    'set_coin_type_workflow_status': (Muenztyp, ('workflow',)),
}


def json_value(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def editor_user(user_id, model=None):
    # Fetch afresh: never reuse Django's permission cache between preview/apply.
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    permissions = [f'slg.change_{model._meta.model_name}'] if model else [
        'slg.change_obj', 'slg.change_muenztyp']
    if user is None or not any(user.has_perm(p) for p in permissions):
        raise ValueError('Keine Bearbeitungsberechtigung für dieses Model.')
    return user


def row_state(row):
    return json_value({f.attname: getattr(row, f.attname) for f in row._meta.concrete_fields})


def digest(value):
    return hashlib.sha256(json.dumps(json_value(value), sort_keys=True).encode()).hexdigest()


def validate_changes(row, action, changes):
    model, fields = OPERATIONS[action]
    if not isinstance(changes, dict) or not changes or set(changes) - set(fields):
        raise ValueError('Nur die ausdrücklich erlaubten Felder dieser Aktion sind zulässig: ' + ', '.join(fields))
    if action.startswith('update_unidentified') and row.Typ_id is not None:
        # Bei bestimmten Objekten haben gespeicherte Obj-Altangaben in Browse,
        # Detail und OAI Vorrang vor dem Münztyp (MTOA-Projektion: Obj → Typ).
        # Neue Werte sind hier tabu, das Bereinigen (Leeren) muss aber möglich
        # sein, sonst verdecken Altangaben dauerhaft die Typangaben.
        if any(value not in (None, '') for value in changes.values()):
            raise ValueError('Die typbezogenen Angaben dieses Objekts werden über den Münztyp definiert. '
                             'Bei bestimmten Objekten können direkte Angaben nur geleert werden '
                             '(null/""); sonst Typzuweisung oder separate Münztypänderung verwenden.')
    if action == 'assign_coin_type' and changes.get('Typ') is None:
        raise ValueError('Eine existierende Münztyp-ID ist erforderlich.')
    if action == 'remove_coin_type' and changes != {'Typ': None}:
        raise ValueError('Diese Aktion entfernt ausschließlich die Typrelation.')
    meta = type('Meta', (), {'model': model, 'fields': fields})
    serializer_class = type('EditorFields', (serializers.ModelSerializer,), {'Meta': meta})
    serializer = serializer_class(row, data=changes, partial=True)
    if not serializer.is_valid():
        raise ValueError(str(serializer.errors))
    values = {key: value.pk if hasattr(value, 'pk') else value
              for key, value in serializer.validated_data.items()}
    start = values.get('dat_von', row.dat_von)
    end = values.get('dat_bis', row.dat_bis)
    if {'dat_von', 'dat_bis'} & values.keys() and start is not None and end is not None and start > end:
        raise ValueError('dat_von darf nicht nach dat_bis liegen.')
    for key in ('gewicht', 'durchmesser'):
        if values.get(key) is not None and values[key] < 0:
            raise ValueError(f'{key} darf nicht negativ sein.')
    return json_value(values)


def _prepare(user_id, action, ids, changes, lock=False):
    if action not in OPERATIONS:
        raise ValueError('Unbekannte Bearbeiteraktion.')
    model, _ = OPERATIONS[action]
    editor_user(user_id, model)
    if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_BULK
            or any(type(i) is not int or i < 1 for i in ids) or len(set(ids)) != len(ids)):
        raise ValueError('1–100 verschiedene positive IDs erforderlich.')
    if model is Muenztyp and len(ids) != 1:
        raise ValueError('Münztypen werden einzeln bearbeitet.')
    qs = model.objects.filter(pk__in=ids).order_by('pk')
    if lock:
        qs = qs.select_for_update()
    rows = list(qs)
    if len(rows) != len(ids):
        raise ValueError('Mindestens ein Datensatz existiert nicht.')
    normalized = None
    entries = []
    warnings = []
    for row in rows:
        values = validate_changes(row, action, changes)
        normalized = values
        old = {key: json_value(getattr(row, model._meta.get_field(key).attname)) for key in values}
        entries.append({'id': row.pk, 'old': old, 'new': values, 'fingerprint': digest(row_state(row))})
        if action == 'assign_coin_type':
            if row.Typ_id is not None and row.Typ_id != values['Typ']:
                warnings.append(f'Objekt {row.pk}: bisheriger Typ {row.Typ_id} wird ersetzt.')
            direct = {key: json_value(getattr(row, Obj._meta.get_field(key).attname))
                      for key in UNIDENTIFIED_FIELDS
                      if getattr(row, Obj._meta.get_field(key).attname) not in (None, '')}
            if direct:
                warnings.append(f'Objekt {row.pk}: direkte Angaben bleiben erhalten und haben in '
                                'Browse/Detail/OAI weiterhin Vorrang vor den Typangaben. Zum Bereinigen '
                                'danach update_unidentified_object_data mit null-Werten verwenden.')
                entries[-1]['preserved_direct_data'] = direct
    impact = None
    target = None
    if model is Muenztyp:
        assigned = list(Obj.objects.filter(Typ_id=rows[0].pk).order_by('pk').values_list('pk', flat=True))
        impact = {'object_count': len(assigned), 'assignment_fingerprint': digest(assigned)}
        warnings.append(f'Dieser Münztyp ist {len(assigned)} Objekten zugeordnet. '
                        'Die Änderung wirkt auf deren Typdarstellung; die Obj-Datensätze werden nicht geändert.')
    if action == 'assign_coin_type':
        target_qs = Muenztyp.objects.filter(pk=normalized['Typ'])
        if lock:
            target_qs = target_qs.select_for_update()
        typ = target_qs.first()
        if typ is None:
            raise ValueError('Der Zieltyp existiert nicht mehr.')
        target = {'id': typ.pk, 'fingerprint': digest(row_state(typ)),
                  'mint': str(typ.Mzstaette) if typ.Mzstaette_id else None,
                  'denomination': str(typ.Nominal) if typ.Nominal_id else None,
                  'date_from': typ.dat_von, 'date_to': typ.dat_bis}
    return rows, {'action': action, 'model': model.__name__, 'ids': sorted(ids),
                  'changes': normalized, 'entries': entries, 'impact': impact,
                  'coin_type': target, 'warnings': warnings}


def preview(user_id, action, ids, changes):
    _, data = _prepare(user_id, action, ids, changes)
    # Only the digest needs to travel back on Apply; large old notes in bulk
    # previews must not make the confirmation request exceed the transport limit.
    payload = {'user_id': user_id, 'action': action, 'ids': data['ids'],
               'changes': data['changes'], 'fingerprint': digest(data)}
    data['preview_token'] = signing.dumps(payload, salt=SALT, compress=True)
    data['expires_in_seconds'] = MAX_AGE
    data['requires_confirmation'] = True
    return data


def apply(user_id, action, preview_token, confirmed=False):
    if confirmed is not True:
        raise ValueError('Vorschau muss vor Apply ausdrücklich bestätigt werden (confirmed=true).')
    try:
        payload = signing.loads(preview_token, salt=SALT, max_age=MAX_AGE)
    except (signing.BadSignature, TypeError, ValueError):
        raise ValueError('Ungültige oder abgelaufene Vorschau. Neue Vorschau erstellen.') from None
    if payload['user_id'] != user_id or payload['action'] != action:
        raise ValueError('Vorschau gehört zu einem anderen Benutzer oder einer anderen Aktion.')
    with transaction.atomic():
        rows, current = _prepare(user_id, action, payload['ids'], payload['changes'], lock=True)
        if digest(current) != payload['fingerprint']:
            raise ValueError('Konflikt: Daten oder Typzuordnungen wurden seit der Vorschau geändert. Neue Vorschau erstellen.')
        model = OPERATIONS[action][0]
        content_type = ContentType.objects.get_for_model(model)
        for row, entry in zip(rows, current['entries']):
            fields = {model._meta.get_field(key).attname: value for key, value in current['changes'].items()}
            fields['modified_at'] = timezone.now()
            # Compare full concrete state as well as locking: catches writers that
            # use QuerySet.update without updating modified_at.
            expected = {f.attname: getattr(row, f.attname) for f in model._meta.concrete_fields}
            if model.objects.filter(**expected).update(**fields) != 1:
                raise ValueError('Konflikt beim Schreiben. Neue Vorschau erstellen.')
            LogEntry.objects.create(user_id=user_id, content_type=content_type,
                object_id=str(row.pk), object_repr=f'{model.__name__} {row.pk}', action_flag=CHANGE,
                change_message=json.dumps([{'changed': {'fields': list(current['changes'])},
                    'source': 'editor_mcp', 'action': action, 'old': entry['old'], 'new': entry['new']}],
                    ensure_ascii=False))
        from slg.mtoa_sync import sync_objs_to_mtoa
        # Bei Münztypen wie sync_muenztyp_on_save: alle Objekte der Typen und
        # alle Objekte, deren Typ einen dieser Typen als Konkordanz führt.
        typ_ids = [row.pk for row in rows]
        affected = (current['ids'] if model is Obj else list(
            Obj.objects.filter(Q(Typ_id__in=typ_ids) | Q(Typ__Konkordanz__in=typ_ids))
            .order_by('pk').values_list('pk', flat=True).distinct()))
        # Existing projection, no Obj writes; errors roll back the entire operation.
        for offset in range(0, len(affected), MAX_BULK):
            sync_objs_to_mtoa(affected[offset:offset + MAX_BULK])
    return {'applied': True, 'action': action, 'model': model.__name__, 'ids': current['ids'],
            'entries': current['entries'], 'impact': current['impact']}


def get_editor_object(user_id, object_id):
    editor_user(user_id, Obj)
    obj = Obj.objects.filter(pk=object_id).select_related('Typ').first()
    if obj is None:
        raise ValueError('Objekt existiert nicht.')
    return {'model': 'Obj', 'object_id': obj.pk, 'object_data': row_state(obj),
            'coin_type': row_state(obj.Typ) if obj.Typ_id else None,
            'type_data_source': 'Muenztyp' if obj.Typ_id else 'Obj',
            'notice': 'Direkte Altangaben bleiben gespeichert; bei gesetztem Typ gelten die Typangaben.'}


# Fachlich definierter Kontrollstatus: derselbe Workflow-Name wie OAI/Kulturpool,
# Nomisma und SEO. Nicht die Reihenfolge (sichtbare "3") und nicht die DB-ID.
CONTROLLED_WORKFLOW_NAME = 'kontrolliert'


def get_workflow_statistics(user_id, collection_id, exclude_collection_part_ids=None):
    """Object and coin type control rates on the public get_statistics population.

    Uses the same MTOA base set as public get_statistics (filter Slg), minus the
    excluded collection parts. Types are counted once each, however many objects
    are assigned; their own Muenztyp workflow decides "kontrolliert".
    """
    editor_user(user_id)
    from slg.services.public_api import filter_request
    from slg.services.search import _get_filtered_mtoa_queryset
    if type(collection_id) is not int or collection_id < 1:
        raise ValueError('Positive Sammlungs-ID erforderlich.')
    excluded = list(exclude_collection_part_ids or [])
    if (len(excluded) > 100 or any(type(i) is not int or i < 1 for i in excluded)
            or len(set(excluded)) != len(excluded)):
        raise ValueError('Höchstens 100 verschiedene positive Sammlungsteil-IDs erforderlich.')
    rows, _, _ = _get_filtered_mtoa_queryset(filter_request({'Slg': collection_id}))
    if excluded:
        # exclude() keeps rows without collection part (NULL), as intended.
        rows = rows.exclude(slgteil_fk_id__in=excluded)
    rows = rows.order_by()
    workflows = Workflow.objects.filter(name__iexact=CONTROLLED_WORKFLOW_NAME)
    object_ids = rows.values('obj_id')
    type_ids = rows.filter(typ_fk__isnull=False).values('typ_fk_id')
    totals = rows.aggregate(objects_total=Count('obj_id', distinct=True),
                            assigned_types_total=Count('typ_fk', distinct=True))
    objects_with_type = (rows.filter(typ_fk__isnull=False)
                         .aggregate(n=Count('obj_id', distinct=True))['n'])
    objects_controlled = Obj.objects.filter(pk__in=object_ids, workflow__in=workflows).count()
    types_controlled = Muenztyp.objects.filter(pk__in=type_ids, workflow__in=workflows).count()

    def rate(part, whole):
        return round(part / whole, 6) if whole else None

    return {
        'collection_id': collection_id,
        'exclude_collection_part_ids': sorted(excluded),
        'objects_total': totals['objects_total'],
        'objects_with_type': objects_with_type,
        'objects_controlled': objects_controlled,
        'assigned_types_total': totals['assigned_types_total'],
        'assigned_types_controlled': types_controlled,
        'object_control_rate': rate(objects_controlled, totals['objects_total']),
        'type_control_rate': rate(types_controlled, totals['assigned_types_total']),
        'controlled_workflow': json_value(list(workflows.order_by('pk').values('id', 'name', 'reihenfolge'))),
        'notice': ('Grundgesamtheit wie öffentliches get_statistics (Slg-Filter) abzüglich der '
                   'ausgeschlossenen Sammlungsteile. "kontrolliert" per Workflow-Name, nicht per '
                   'Reihenfolge oder ID. Typquote: jeder zugewiesene Münztyp zählt einmal, '
                   'nach seinem eigenen Typ-Workflow.'),
    }


def list_packages(user_id, collection_id, page=1):
    """Return package metadata and scoped membership counts for an editor."""
    user = editor_user(user_id)
    if not user.has_perm('slg.view_paket'):
        raise ValueError('Keine Leseberechtigung für Pakete.')
    if type(collection_id) is not int or collection_id < 1 or type(page) is not int or page < 1:
        raise ValueError('Positive Sammlungs-ID und Seite erforderlich.')
    page_size = 100
    packages = (Paket.objects.annotate(
        object_count=Count('obj', filter=Q(obj__Slg_id=collection_id), distinct=True))
        .filter(object_count__gt=0).order_by('name', 'pk'))
    start = (page - 1) * page_size
    results = list(packages.values('id', 'name', 'slug', 'object_count',
                                   'ist_arbeitspaket', 'online_freigegeben')[start:start + page_size + 1])
    return {'collection_id': collection_id, 'page': page,
            'has_more': len(results) > page_size, 'results': results[:page_size]}


def get_package_workflow_statistics(user_id, collection_id, package_ids):
    """Count the union of objects in selected editor packages for one collection."""
    user = editor_user(user_id)
    if not user.has_perm('slg.view_paket'):
        raise ValueError('Keine Leseberechtigung für Pakete.')
    if (type(collection_id) is not int or collection_id < 1 or not package_ids
            or len(package_ids) > 100 or any(type(i) is not int or i < 1 for i in package_ids)
            or len(set(package_ids)) != len(package_ids)):
        raise ValueError('Positive Sammlungs-ID und bis zu 100 unterschiedliche Paket-IDs erforderlich.')
    package_ids = sorted(package_ids)
    if Paket.objects.filter(pk__in=package_ids).count() != len(package_ids):
        raise ValueError('Mindestens ein ausgewähltes Paket ist nicht verfügbar.')
    objects = Obj.objects.filter(Slg_id=collection_id, pakete__pk__in=package_ids).order_by()
    workflows = Workflow.objects.filter(name__iexact=CONTROLLED_WORKFLOW_NAME)
    if not workflows.exists():
        raise ValueError('Der Workflow „kontrolliert“ ist nicht konfiguriert.')
    counts = objects.aggregate(
        objects_total=Count('pk', distinct=True),
        objects_with_type=Count('pk', filter=Q(Typ_id__isnull=False), distinct=True),
        objects_controlled=Count('pk', filter=Q(workflow__in=workflows), distinct=True),
        assigned_types_total=Count('Typ', distinct=True),
        assigned_types_controlled=Count('Typ', filter=Q(Typ__workflow__in=workflows), distinct=True),
    )
    return {'collection_id': collection_id, 'package_ids': package_ids, **counts}


def search_coin_types(user_id, mint_id=None, nominal_id=None, page=1):
    editor_user(user_id)
    if type(page) is not int or page < 1:
        raise ValueError('Positive Seite erforderlich.')
    qs = Muenztyp.objects.order_by('pk')
    if mint_id is not None:
        qs = qs.filter(Mzstaette_id=mint_id)
    if nominal_id is not None:
        qs = qs.filter(Nominal_id=nominal_id)
    count = qs.count()
    rows = qs[(page - 1) * 25:page * 25]
    fields = ('id', 'muenztyptitel', *TYPE_FIELDS)
    return {'total': count, 'page': page, 'has_more': page * 25 < count,
            'results': json_value(list(rows.values(*fields)))}
