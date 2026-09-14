"""Domain-limited editor operations. No preview persistence or schema changes."""
import hashlib
import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from slg.models import Obj, Muenztyp

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
        raise ValueError('Die typbezogenen Angaben dieses Objekts werden über den Münztyp definiert. '
                         'Typzuweisung oder separate Münztypänderung verwenden.')
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
                warnings.append(f'Objekt {row.pk}: direkte Angaben bleiben erhalten; '
                                'die Typangaben bestimmen künftig die typbezogene Darstellung.')
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
        affected = (current['ids'] if model is Obj else list(
            Obj.objects.filter(Typ_id=rows[0].pk).values_list('pk', flat=True)))
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
