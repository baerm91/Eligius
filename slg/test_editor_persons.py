"""Depicted-person assignment respects type/side/role boundaries and preview state."""
import json
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase

from slg.models import (Muenztyp, Mztyp_Person, Obj_Person, Person, PersonFunktion,
                        RvBildtyp, MtoaPerson, MuenztypObjektAnzeige)
from slg.services import editor_api, editor_persons
from slg.test_editor_mcp import fixtures


class DepictedPersonTests(TestCase):
    def setUp(self):
        self.user, self.typ, self.obj, self.classified, _ = fixtures()
        self.user.user_permissions.add(Permission.objects.get(codename='add_mztyp_person',
            content_type__app_label='slg'))
        self.depicted = PersonFunktion.objects.create(pk=2, name='Dargestellte Person')
        self.ruler = PersonFunktion.objects.create(pk=1, name='Prägeherr')
        self.person = Person.objects.create(name='Testperson')
        self.other = Person.objects.create(name='Andere Person')
        self.image_type = RvBildtyp.objects.create(name='Bildtyp')
        Muenztyp.objects.filter(pk=self.typ.pk).update(rv_bildtyp=self.image_type)
        self.typ.refresh_from_db()
        Mztyp_Person.objects.bulk_create([
            Mztyp_Person(Mztyp=self.typ, idfk_Person=self.person,
                         idfk_PersonFunktion=self.ruler, appears_on_rev=True),
            Mztyp_Person(Mztyp=self.typ, idfk_Person=self.person,
                         idfk_PersonFunktion=self.depicted, appears_on_rev=False),
            Mztyp_Person(Mztyp=self.typ, idfk_Person=self.other,
                         idfk_PersonFunktion=self.depicted, appears_on_rev=True),
        ])
        Obj_Person.objects.bulk_create([Obj_Person(idfk_Obj=self.classified,
            idfk_Person=self.other, idfk_PersonFunktion=self.depicted, appears_on_rev=False)])

    def preview(self, **kwargs):
        args = {'type_ids': [self.typ.pk], 'person_id': self.person.pk, 'side': 'rv'} | kwargs
        return editor_persons.preview_assign_depicted_person(self.user.pk, **args)

    def apply(self, preview, **kwargs):
        args = {'preview_token': preview['preview_token'], 'confirmed': True} | kwargs
        return editor_persons.assign_depicted_person(self.user.pk, **args)

    def test_preview_and_apply_preserve_other_sides_roles_objects_and_image_types(self):
        before_type = editor_api.row_state(self.typ)
        before_obj = editor_api.row_state(self.classified)
        before_image = editor_api.row_state(self.image_type)
        before_relations = list(Mztyp_Person.objects.order_by('pk').values())
        before_obj_persons = list(Obj_Person.objects.values())
        tables = connection.introspection.table_names()
        preview = self.preview()
        self.assertEqual(preview['model'], 'Mztyp_Person')
        self.assertEqual(preview['function']['id'], 2)
        self.assertEqual(preview['affected_object_count'], 1)
        self.assertEqual(preview['entries'][0]['status'], 'add')
        self.assertEqual(Mztyp_Person.objects.count(), 3)
        self.assertEqual(LogEntry.objects.count(), 0)
        self.typ.refresh_from_db()
        self.assertEqual(editor_api.row_state(self.typ), before_type)
        result = self.apply(preview)
        self.assertEqual(result['changed_type_count'], 1)
        self.assertEqual(Mztyp_Person.objects.count(), 4)
        self.assertEqual(list(Mztyp_Person.objects.filter(pk__in=[r['id'] for r in before_relations])
                              .order_by('pk').values()), before_relations)
        self.assertEqual(list(Obj_Person.objects.values()), before_obj_persons)
        self.classified.refresh_from_db()
        self.image_type.refresh_from_db()
        self.typ.refresh_from_db()
        self.assertEqual(editor_api.row_state(self.classified), before_obj)
        self.assertEqual(editor_api.row_state(self.image_type), before_image)
        after_type = editor_api.row_state(self.typ)
        self.assertNotEqual(after_type.pop('modified_at'), before_type.pop('modified_at'))
        self.assertEqual(after_type, before_type)
        self.assertEqual(connection.introspection.table_names(), tables)
        log = LogEntry.objects.get()
        self.assertEqual(log.user_id, self.user.pk)
        self.assertEqual(log.content_type.model, 'muenztyp')
        audit = json.loads(log.change_message)[0]
        self.assertEqual(len(audit['old']), 3)
        self.assertEqual(len(audit['new']), 4)
        projection = MuenztypObjektAnzeige.objects.get(obj_id=self.classified.pk)
        self.assertTrue(MtoaPerson.objects.filter(mtoa=projection, person=self.person,
            funktion=self.depicted, appears_on_rev=True).exists())

    def test_existing_assignment_is_noop_without_duplicate_or_audit(self):
        preview = self.preview(side='av')
        self.assertEqual(preview['changed_type_count'], 0)
        self.assertEqual(preview['affected_object_count'], 0)
        self.assertEqual(preview['entries'][0]['status'], 'already_assigned')
        before = editor_api.row_state(self.typ)
        self.apply(preview)
        self.typ.refresh_from_db()
        self.assertEqual(editor_api.row_state(self.typ), before)
        self.assertEqual(Mztyp_Person.objects.count(), 3)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_bulk_assignment_to_30_types(self):
        Muenztyp.objects.bulk_create([Muenztyp(muenztyptitel=f'Bulk {i}', titel='Bulk',
            Objekttyp=None, Herstellung=None, workflow=None) for i in range(29)])
        ids = list(Muenztyp.objects.order_by('pk').values_list('pk', flat=True))
        preview = self.preview(type_ids=ids)
        self.assertEqual(len(preview['entries']), 30)
        self.apply(preview)
        self.assertEqual(Mztyp_Person.objects.filter(idfk_Person=self.person,
            idfk_PersonFunktion=self.depicted, appears_on_rev=True).count(), 30)
        self.assertEqual(LogEntry.objects.count(), 30)

    def test_invalid_inputs_and_missing_records(self):
        for args in ({'side': 'reverse'}, {'side': True}, {'person_id': True},
                     {'person_id': 999999}, {'type_ids': []}, {'type_ids': [True]},
                     {'type_ids': [self.typ.pk, self.typ.pk]}, {'type_ids': list(range(1, 102))},
                     {'type_ids': [self.typ.pk, 999999]}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.preview(**args)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_missing_depicted_function_does_not_create_role(self):
        Mztyp_Person.objects.all().delete()
        Obj_Person.objects.all().delete()
        self.depicted.delete()
        with self.assertRaisesRegex(ValueError, 'Funktion'):
            self.preview()
        self.assertFalse(PersonFunktion.objects.filter(pk=2).exists())

    def test_type_and_through_permissions_required_and_rechecked(self):
        preview = self.preview()
        self.user.user_permissions.clear()
        with self.assertRaisesRegex(ValueError, 'add_mztyp_person'):
            self.apply(preview)
        self.user.user_permissions.add(Permission.objects.get(codename='add_mztyp_person',
            content_type__app_label='slg'))
        self.user.groups.clear()
        with self.assertRaises(ValueError):
            self.preview()
        with self.assertRaises(ValueError):
            self.apply(preview)

    def test_relation_change_without_modified_at_invalidates_preview(self):
        preview = self.preview()
        Mztyp_Person.objects.filter(Mztyp=self.typ, idfk_Person=self.other).update(appears_on_rev=False)
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)
        self.assertEqual(Mztyp_Person.objects.count(), 3)

    def test_relation_insertion_and_type_changes_invalidate_preview(self):
        preview = self.preview()
        Mztyp_Person.objects.bulk_create([Mztyp_Person(Mztyp=self.typ,
            idfk_Person=self.other, idfk_PersonFunktion=self.ruler, appears_on_rev=False)])
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)
        preview = self.preview()
        Muenztyp.objects.filter(pk=self.typ.pk).update(anmerkung='Concurrent')
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)

    def test_object_assignment_and_person_changes_invalidate_preview(self):
        from slg.models import Obj
        preview = self.preview()
        Obj.objects.filter(pk=self.obj.pk).update(Typ=self.typ)
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)
        preview = self.preview()
        Person.objects.filter(pk=self.person.pk).update(name='Renamed')
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)

    def test_confirmation_signature_expiry_user_and_cross_action_binding(self):
        preview = self.preview()
        with self.assertRaises(ValueError):
            self.apply(preview, confirmed=False)
        with self.assertRaises(ValueError):
            self.apply(preview, preview_token=preview['preview_token'] + 'x')
        with patch('django.core.signing.time.time', return_value=9999999999):
            with self.assertRaises(ValueError):
                self.apply(preview)
        with self.assertRaises(ValueError):
            editor_persons.assign_depicted_person(self.user.pk + 1, preview['preview_token'], True)
        scalar = editor_api.preview(self.user.pk, 'update_coin_type', [self.typ.pk], {'avleg': 'x'})
        with self.assertRaises(ValueError):
            self.apply(scalar)
        with self.assertRaises(ValueError):
            editor_api.apply(self.user.pk, 'update_coin_type', preview['preview_token'], True)
        self.apply(preview)
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)

    def test_audit_or_projection_failure_rolls_back_relation_and_parent(self):
        for target in ('slg.services.editor_persons.LogEntry.objects.create', 'slg.mtoa_sync.sync_objs_to_mtoa'):
            before = editor_api.row_state(self.typ)
            preview = self.preview()
            with patch(target, side_effect=RuntimeError('test failure')):
                with self.assertRaises(RuntimeError):
                    self.apply(preview)
            self.typ.refresh_from_db()
            self.assertEqual(editor_api.row_state(self.typ), before)
            self.assertEqual(Mztyp_Person.objects.count(), 3)
            self.assertEqual(LogEntry.objects.count(), 0)

    def test_scalar_update_cannot_write_person_fields(self):
        for name in ('Ppl', 'personen', 'rv_dargestellte', 'Mztyp_Person'):
            with self.assertRaises(ValueError):
                editor_api.preview(self.user.pk, 'update_coin_type', [self.typ.pk], {name: [self.person.pk]})

    def test_late_bulk_failure_rolls_back_all_types_and_relations(self):
        other_type = Muenztyp.objects.create(muenztyptitel='Second type', titel='Second',
            Objekttyp=None, Herstellung=None, workflow=None)
        before = list(Muenztyp.objects.order_by('pk').values())
        preview = self.preview(type_ids=[self.typ.pk, other_type.pk])
        create_log = LogEntry.objects.create
        calls = 0

        def fail_second_log(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('Second audit failed')
            return create_log(**kwargs)

        with patch('slg.services.editor_persons.LogEntry.objects.create', side_effect=fail_second_log):
            with self.assertRaises(RuntimeError):
                self.apply(preview)
        self.assertEqual(list(Muenztyp.objects.order_by('pk').values()), before)
        self.assertEqual(Mztyp_Person.objects.count(), 3)
        self.assertEqual(LogEntry.objects.count(), 0)
