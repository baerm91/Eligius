"""Add depicted people through the existing Mztyp_Person model only."""
import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.db import transaction
from django.utils import timezone

from slg.models import Muenztyp, Mztyp_Person, Obj, Person, PersonFunktion
from slg.services import editor_api

ACTION = 'assign_depicted_person'
SALT = 'eligius.editor.depicted-person.v1'
# Existing model properties and FILTER_PARAMETERS identify depicted people by 2.
DEPICTED_FUNCTION_ID = 2


def _prepare(user_id, type_ids, person_id, side, lock=False):
    user = editor_api.editor_user(user_id, Muenztyp)
    # Match the existing Django admin inline's add permission as well as parent rights.
    if not user.has_perm('slg.add_mztyp_person'):
        raise ValueError('Berechtigung slg.add_mztyp_person für die Personenzuordnung fehlt.')
    if (not isinstance(type_ids, list) or not 1 <= len(type_ids) <= editor_api.MAX_BULK
            or any(type(pk) is not int or pk < 1 for pk in type_ids)
            or len(set(type_ids)) != len(type_ids)):
        raise ValueError('1–100 verschiedene positive Münztyp-IDs erforderlich.')
    if type(person_id) is not int or person_id < 1 or side not in ('av', 'rv'):
        raise ValueError('Positive Personen-ID und side="av" oder "rv" erforderlich.')
    persons = Person.objects.filter(pk=person_id)
    functions = PersonFunktion.objects.filter(pk=DEPICTED_FUNCTION_ID)
    types = Muenztyp.objects.filter(pk__in=type_ids).order_by('pk')
    if lock:
        persons = persons.select_for_update()
        functions = functions.select_for_update()
        types = types.select_for_update()
    person, function = persons.first(), functions.first()
    if person is None:
        raise ValueError('Person existiert nicht.')
    if function is None:
        raise ValueError('Die von Eligius verwendete Dargestellten-Funktion (ID 2) fehlt.')
    rows = list(types)
    if len(rows) != len(type_ids):
        raise ValueError('Mindestens ein Münztyp existiert nicht.')
    relations = Mztyp_Person.objects.filter(Mztyp_id__in=type_ids).order_by('pk')
    if lock:
        relations = relations.select_for_update()
    relations_by_type = {row.pk: [] for row in rows}
    for relation in relations:
        relations_by_type[relation.Mztyp_id].append(editor_api.row_state(relation))
    object_ids = {row.pk: [] for row in rows}
    for typ_id, obj_id in Obj.objects.filter(Typ_id__in=type_ids).order_by('pk').values_list('Typ_id', 'pk'):
        object_ids[typ_id].append(obj_id)
    reverse = side == 'rv'
    entries = []
    for row in rows:
        old = relations_by_type[row.pk]
        already_assigned = any(r['idfk_Person_id'] == person_id
                               and r['idfk_PersonFunktion_id'] == DEPICTED_FUNCTION_ID
                               and r['appears_on_rev'] == reverse for r in old)
        added = {'Mztyp_id': row.pk, 'idfk_Person_id': person_id,
                 'idfk_PersonFunktion_id': DEPICTED_FUNCTION_ID, 'appears_on_rev': reverse}
        entries.append({'type_id': row.pk, 'title': row.muenztyptitel,
                        'status': 'already_assigned' if already_assigned else 'add',
                        'old': old, 'new': old if already_assigned else old + [added],
                        'type_fingerprint': editor_api.digest(editor_api.row_state(row)),
                        'object_count': len(object_ids[row.pk]),
                        'assignment_fingerprint': editor_api.digest(object_ids[row.pk])})
    changed = [entry for entry in entries if entry['status'] == 'add']
    data = {'action': ACTION, 'model': 'Mztyp_Person', 'parent_model': 'Muenztyp',
            'fields': ['Mztyp', 'idfk_Person', 'idfk_PersonFunktion', 'appears_on_rev'],
            'type_ids': sorted(type_ids), 'person': {'id': person.pk, 'name': person.name,
                'fingerprint': editor_api.digest(editor_api.row_state(person))},
            'function': {'id': function.pk, 'name': function.name},
            'side': side, 'appears_on_rev': reverse, 'entries': entries,
            'changed_type_count': len(changed),
            'affected_object_count': sum(entry['object_count'] for entry in changed),
            'notice': 'Es werden nur fehlende Dargestellten-Zuordnungen auf der gewählten Seite ergänzt. '
                      'Bestehende Personen und Rollen bleiben erhalten. Die Darstellung zugeordneter '
                      'Objekte ändert sich über den Münztyp; Obj, Obj_Person und Bildtypen bleiben unverändert.'}
    return rows, data


def preview_assign_depicted_person(user_id, type_ids, person_id, side):
    _, data = _prepare(user_id, type_ids, person_id, side)
    payload = {'user_id': user_id, 'action': ACTION, 'type_ids': data['type_ids'],
               'person_id': person_id, 'side': side, 'fingerprint': editor_api.digest(data)}
    data['preview_token'] = signing.dumps(payload, salt=SALT, compress=True)
    data['requires_confirmation'] = True
    data['expires_in_seconds'] = editor_api.MAX_AGE
    return data


def assign_depicted_person(user_id, preview_token, confirmed=False):
    if confirmed is not True:
        raise ValueError('Vorschau muss ausdrücklich bestätigt werden (confirmed=true).')
    try:
        payload = signing.loads(preview_token, salt=SALT, max_age=editor_api.MAX_AGE)
    except (signing.BadSignature, TypeError, ValueError):
        raise ValueError('Ungültige oder abgelaufene Vorschau. Neue Vorschau erstellen.') from None
    if payload['user_id'] != user_id or payload['action'] != ACTION:
        raise ValueError('Vorschau gehört zu einem anderen Benutzer oder einer anderen Aktion.')
    with transaction.atomic():
        rows, current = _prepare(user_id, payload['type_ids'], payload['person_id'], payload['side'], lock=True)
        if editor_api.digest(current) != payload['fingerprint']:
            raise ValueError('Konflikt: Typ, Personen, Relationen oder Objektzuordnungen wurden geändert. Neue Vorschau erstellen.')
        changed = [(row, entry) for row, entry in zip(rows, current['entries']) if entry['status'] == 'add']
        for row, _ in changed:
            expected = {field.attname: getattr(row, field.attname) for field in row._meta.concrete_fields}
            if Muenztyp.objects.filter(**expected).update(modified_at=timezone.now()) != 1:
                raise ValueError('Konflikt beim Schreiben. Neue Vorschau erstellen.')
        # Bulk insert skips the per-row signal. The existing projection is synced
        # once below, inside the transaction, with errors propagated for rollback.
        Mztyp_Person.objects.bulk_create([Mztyp_Person(Mztyp_id=row.pk,
            idfk_Person_id=payload['person_id'], idfk_PersonFunktion_id=DEPICTED_FUNCTION_ID,
            appears_on_rev=payload['side'] == 'rv') for row, _ in changed])
        if changed:
            content_type = ContentType.objects.get_for_model(Muenztyp)
            for row, entry in changed:
                LogEntry.objects.create(user_id=user_id, content_type=content_type,
                    object_id=str(row.pk), object_repr=f'Muenztyp {row.pk}', action_flag=CHANGE,
                    change_message=json.dumps([{'changed': {'fields': ['Mztyp_Person']},
                        'source': 'editor_mcp', 'action': ACTION, 'model': 'Mztyp_Person',
                        'person': current['person']['name'], 'function': current['function'],
                        'old': entry['old'], 'new': entry['new']}], ensure_ascii=False))
            from slg.mtoa_sync import sync_objs_to_mtoa
            affected = list(Obj.objects.filter(Typ_id__in=[row.pk for row, _ in changed])
                            .order_by('pk').values_list('pk', flat=True))
            for offset in range(0, len(affected), editor_api.MAX_BULK):
                sync_objs_to_mtoa(affected[offset:offset + editor_api.MAX_BULK])
    return {'applied': True, **current}
