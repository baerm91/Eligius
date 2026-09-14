"""Editor regression coverage against a disposable database, never development data."""
import importlib
import json
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.db import connection
from django.test import TestCase, TransactionTestCase, Client, override_settings
from rest_framework.authtoken.models import Token

from slg.models import Obj, Muenztyp, Mzstaette, Metall, Nominal, Slg, Workflow, MuenztypObjektAnzeige
from slg.services import editor_api as api
from slg.signals import disable_mtoa_sync, enable_mtoa_sync


def fixtures():
    disable_mtoa_sync()
    try:
        user = get_user_model().objects.create_user('editor', password='test-password')
        group = Group.objects.create(name='MCP test editors')
        group.permissions.add(*Permission.objects.filter(content_type__app_label='slg',
            codename__in=['change_obj', 'change_muenztyp']))
        user.groups.add(group)
        mint = Mzstaette.objects.create(name='Siscia')
        other_mint = Mzstaette.objects.create(name='Emesa')
        metal = Metall.objects.create(name='Bronze')
        nominal = Nominal.objects.create(name='Follis', material=metal)
        typ = Muenztyp.objects.create(muenztyptitel='MCP type', titel='Test',
            Mzstaette=mint, Nominal=nominal, Metall=metal, dat_von=300, dat_bis=310,
            avleg='TYPE LEGEND', Objekttyp=None, Herstellung=None, workflow=None)
        collection = Slg.objects.create(name='Editor collection')
        obj = Obj.objects.create(invnr='E-1', Slg=collection, Objekttyp=None, workflow=None,
            idfk_Mzstaette=other_mint, avleg='DIRECT LEGEND', gewicht='3.25')
        classified = Obj.objects.create(invnr='E-2', Slg=collection, Typ=typ,
            Objekttyp=None, workflow=None, avleg='PRESERVED')
        return user, typ, obj, classified, other_mint
    finally:
        enable_mtoa_sync()


class EditorServiceTests(TestCase):
    def setUp(self):
        self.user, self.typ, self.obj, self.classified, self.other_mint = fixtures()

    def preview(self, action, changes, ids=None):
        return api.preview(self.user.pk, action, ids or [self.obj.pk], changes)

    def apply(self, preview, **kwargs):
        return api.apply(self.user.pk, preview['action'], preview['preview_token'], **({'confirmed': True} | kwargs))

    def assert_only_changed(self, row, before, allowed):
        row.refresh_from_db()
        after = api.row_state(row)
        self.assertEqual({k: v for k, v in before.items() if k not in allowed},
                         {k: v for k, v in after.items() if k not in allowed})

    def test_assignment_preview_no_writes_and_apply_only_relation(self):
        before = api.row_state(self.obj)
        tables = set(connection.introspection.table_names())
        preview = self.preview('assign_coin_type', {'Typ': self.typ.pk})
        self.assertEqual(preview['coin_type']['mint'], 'Siscia')
        self.assertEqual(LogEntry.objects.count(), 0)
        self.assert_only_changed(self.obj, before, set())
        self.apply(preview)
        self.assert_only_changed(self.obj, before, {'Typ_id', 'modified_at'})
        self.assertEqual(self.obj.Typ_id, self.typ.pk)
        self.assertIsNone(self.obj.Metall_id)
        self.assertEqual(set(connection.introspection.table_names()), tables)
        self.assertEqual(MuenztypObjektAnzeige.objects.get(obj_id=self.obj.pk).typ_fk_id, self.typ.pk)
        log = LogEntry.objects.get()
        self.assertEqual(log.user_id, self.user.pk)
        data = json.loads(log.change_message)[0]
        self.assertEqual(data['old'], {'Typ': None})
        self.assertEqual(data['new'], {'Typ': self.typ.pk})

    def test_assignment_uncertainty_and_replacement_are_explicit(self):
        preview = self.preview('assign_coin_type', {'Typ': self.typ.pk, 'Typ_unsicher': True})
        self.apply(preview)
        self.obj.refresh_from_db()
        self.assertTrue(self.obj.Typ_unsicher)
        other = Muenztyp.objects.create(muenztyptitel='Other', titel='Other',
            Objekttyp=None, Herstellung=None, workflow=None)
        preview = self.preview('assign_coin_type', {'Typ': other.pk})
        self.assertIn('ersetzt', str(preview['warnings']))

    def test_type_mint_changes_only_type_and_projection(self):
        before = api.row_state(self.classified)
        typ_before = api.row_state(self.typ)
        preview = self.preview('update_coin_type', {'Mzstaette': self.other_mint.pk}, [self.typ.pk])
        self.assertEqual(preview['impact']['object_count'], 1)
        self.assertIn('1 Objekten', str(preview['warnings']))
        self.apply(preview)
        self.assert_only_changed(self.classified, before, set())
        self.assert_only_changed(self.typ, typ_before, {'Mzstaette_id', 'modified_at'})
        self.assertEqual(self.typ.Mzstaette_id, self.other_mint.pk)

    def test_unidentified_changes_and_classified_rejection(self):
        preview = self.preview('update_unidentified_object_data', {'idfk_Mzstaette': self.typ.Mzstaette_id, 'avleg': 'NEW'})
        self.apply(preview)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.avleg, 'NEW')
        for action in ('update_unidentified_object_data', 'update_unidentified_legend'):
            with self.assertRaisesRegex(ValueError, 'Münztyp'):
                self.preview(action, {'avleg': 'BAD'}, [self.classified.pk])

    def test_removal_preserves_direct_fields_without_default_copy(self):
        Obj.objects.filter(pk=self.classified.pk).update(idfk_Nominal=self.typ.Nominal_id, Metall=None)
        self.classified.refresh_from_db()
        before = api.row_state(self.classified)
        self.apply(self.preview('remove_coin_type', {'Typ': None}, [self.classified.pk]))
        self.assert_only_changed(self.classified, before, {'Typ_id', 'modified_at'})
        self.assertIsNone(self.classified.Typ_id)
        self.assertIsNone(self.classified.Metall_id)

    def test_measurements_note_workflow_and_legend_boundaries(self):
        self.apply(self.preview('update_object_measurements', {'gewicht': '4.50', 'durchmesser': '20.1', 'stempelstellung': 6}))
        self.apply(self.preview('update_object_note', {'anmerkung': 'Bearbeitet'}))
        workflow = Workflow.objects.create(name='Prüfen')
        self.apply(self.preview('set_object_workflow_status', {'workflow': workflow.pk}))
        self.apply(self.preview('update_coin_type_legend', {'avleg': 'NEW TYPE'}, [self.typ.pk]))
        self.apply(self.preview('set_coin_type_workflow_status', {'workflow': workflow.pk}, [self.typ.pk]))
        self.obj.refresh_from_db()
        self.typ.refresh_from_db()
        self.assertEqual(str(self.obj.gewicht), '4.50')
        self.assertEqual(self.obj.workflow_id, workflow.pk)
        self.assertEqual(self.typ.avleg, 'NEW TYPE')
        self.assertEqual(self.obj.avleg, 'DIRECT LEGEND')

    def test_field_validation_and_no_model_boundary_escape(self):
        cases = [
            ('assign_coin_type', {'Typ': self.typ.pk, 'Metall': self.typ.Metall_id}),
            ('assign_coin_type', {'Typ': 999999}),
            ('update_object_note', {'Typ__Mzstaette': 1}),
            ('update_object_note', {'anmerkung': 'ok', 'Typ': self.typ.pk}),
            ('update_unidentified_object_data', {'Ppl': [1]}),
            ('update_object_measurements', {'gewicht': '-1'}),
            ('update_object_measurements', {'gewicht': '1.234'}),
            ('update_object_measurements', {'stempelstellung': 99}),
            ('update_unidentified_object_data', {'dat_von': 400, 'dat_bis': 300}),
            ('update_object_note', {}),
        ]
        for action, changes in cases:
            with self.subTest(action=action, changes=changes), self.assertRaises(ValueError):
                self.preview(action, changes)
        for ids in ([self.obj.pk] * 2, [], [True], list(range(1, 102))):
            with self.assertRaises(ValueError):
                api.preview(self.user.pk, 'update_object_note', ids, {'anmerkung': 'x'})

    def test_stale_data_even_without_timestamp_rejected(self):
        preview = self.preview('assign_coin_type', {'Typ': self.typ.pk})
        Obj.objects.filter(pk=self.obj.pk).update(anmerkung='Concurrent change')
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_changed_target_and_changed_impact_require_new_preview(self):
        preview = self.preview('assign_coin_type', {'Typ': self.typ.pk})
        Muenztyp.objects.filter(pk=self.typ.pk).update(avleg='Changed')
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)
        preview = self.preview('update_coin_type', {'rvleg': 'Update'}, [self.typ.pk])
        Obj.objects.filter(pk=self.obj.pk).update(Typ=self.typ)
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)

    def test_confirmation_tampering_expiration_replay_and_user_binding(self):
        preview = self.preview('update_object_note', {'anmerkung': 'x'})
        with self.assertRaises(ValueError):
            self.apply(preview, confirmed=False)
        with self.assertRaises(ValueError):
            api.apply(self.user.pk, preview['action'], preview['preview_token'] + 'x', True)
        with patch('django.core.signing.time.time', return_value=9999999999):
            with self.assertRaisesRegex(ValueError, 'abgelaufene'):
                self.apply(preview)
        with self.assertRaises(ValueError):
            api.apply(self.user.pk + 100, preview['action'], preview['preview_token'], True)
        with self.assertRaises(ValueError):
            api.apply(self.user.pk, 'remove_coin_type', preview['preview_token'], True)
        self.apply(preview)
        with self.assertRaisesRegex(ValueError, 'Konflikt'):
            self.apply(preview)

    def test_permissions_revoked_or_wrong_model(self):
        preview = self.preview('update_object_note', {'anmerkung': 'x'})
        self.user.groups.clear()
        self.user.user_permissions.add(Permission.objects.get(codename='change_obj', content_type__app_label='slg'))
        with self.assertRaises(ValueError):
            self.preview('update_coin_type', {'avleg': 'x'}, [self.typ.pk])
        self.user.user_permissions.clear()
        with self.assertRaises(ValueError):
            self.apply(preview)

    def test_bulk_conflict_is_all_or_nothing(self):
        before = api.row_state(self.obj)
        preview = self.preview('assign_coin_type', {'Typ': self.typ.pk}, [self.obj.pk, self.classified.pk])
        Obj.objects.filter(pk=self.classified.pk).update(anmerkung='concurrent')
        with self.assertRaises(ValueError):
            self.apply(preview)
        self.assert_only_changed(self.obj, before, set())
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_bulk_success_and_compact_preview_for_large_old_notes(self):
        Obj.objects.filter(pk__in=[self.obj.pk, self.classified.pk]).update(anmerkung='long note ' * 10000)
        preview = self.preview('update_object_note', {'anmerkung': 'revised'}, [self.obj.pk, self.classified.pk])
        self.assertLess(len(preview['preview_token']), 2000)
        self.apply(preview)
        self.assertEqual(Obj.objects.filter(anmerkung='revised').count(), 2)
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_editor_reads_separate_models_and_find_candidate_types(self):
        result = api.get_editor_object(self.user.pk, self.classified.pk)
        self.assertEqual(result['type_data_source'], 'Muenztyp')
        self.assertEqual(result['object_data']['avleg'], 'PRESERVED')
        self.assertEqual(result['coin_type']['avleg'], 'TYPE LEGEND')
        result = api.search_coin_types(self.user.pk, self.typ.Mzstaette_id, self.typ.Nominal_id)
        self.assertEqual(result['results'][0]['id'], self.typ.pk)
        self.assertEqual(api.search_coin_types(self.user.pk, self.other_mint.pk)['total'], 0)

    def test_audit_and_projection_failure_roll_back_bulk(self):
        for target in ('slg.services.editor_api.LogEntry.objects.create', 'slg.mtoa_sync.sync_objs_to_mtoa'):
            before = api.row_state(self.obj)
            preview = self.preview('assign_coin_type', {'Typ': self.typ.pk}, [self.obj.pk, self.classified.pk])
            with patch(target, side_effect=RuntimeError('failure')):
                with self.assertRaises(RuntimeError):
                    self.apply(preview)
            self.assert_only_changed(self.obj, before, set())
            self.assertEqual(LogEntry.objects.count(), 0)


class EditorTransportTests(TransactionTestCase):
    def reload_transports(self):
        # SDK session managers have a single lifespan, like a production process.
        # Give each independent TestClient a fresh transport/application.
        from slg import mcp_server, editor_mcp
        from djangoproject import asgi
        importlib.reload(mcp_server)
        importlib.reload(editor_mcp)
        importlib.reload(asgi)

    def setUp(self):
        self.reload_transports()
        self.addCleanup(self.reload_transports)
        self.user, self.typ, self.obj, self.classified, self.other_mint = fixtures()
        self.token = Token.objects.create(user=self.user).key
        self.headers = {'Accept': 'application/json, text/event-stream',
                        'MCP-Protocol-Version': '2025-03-26'}

    def rpc(self, client, method='tools/list', params=None, headers=None, path='/mcp/editor'):
        return client.post(path, headers=self.headers | (headers or {}), json={
            'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})

    def test_authentication_and_public_registry(self):
        from starlette.testclient import TestClient
        from djangoproject.asgi import application
        with TestClient(application) as client:
            self.assertEqual(self.rpc(client).status_code, 401)
            self.assertEqual(self.rpc(client, path='/mcp/editor?auth_token=' + self.token).status_code, 401)
            self.assertEqual(self.rpc(client, headers={'Authorization': 'Token invalid'}).status_code, 401)
            headers = {'Authorization': 'Token ' + self.token}
            response = self.rpc(client, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            names = {t['name'] for t in response.json()['result']['tools']}
            self.assertTrue({'assign_coin_type', 'update_coin_type', 'set_workflow_status'} <= names)
            self.assertFalse({'set_field', 'execute_sql', 'update_model'} & names)
            public = self.rpc(client, path='/mcp', headers=headers).json()['result']['tools']
            self.assertEqual(len(public), 5)
            self.assertTrue(all(t['annotations']['readOnlyHint'] for t in public))
            result = self.rpc(client, 'tools/call', {'name': 'assign_coin_type',
                'arguments': {'preview_token': 'x', 'confirmed': True}}, headers, '/mcp')
            self.assertTrue(result.json()['result']['isError'])
            self.user.groups.clear()
            self.assertEqual(self.rpc(client, headers=headers).status_code, 403)
            self.user.is_active = False
            self.user.save()
            self.assertEqual(self.rpc(client, headers=headers).status_code, 401)

    @override_settings(ELIGIUS_MCP_ENABLED=False, ELIGIUS_EDITOR_MCP_ENABLED=True)
    def test_editor_enabled_independently_of_public(self):
        from starlette.testclient import TestClient
        self.reload_transports()
        from djangoproject.asgi import application
        with TestClient(application) as client:
            self.assertEqual(self.rpc(client, headers={'Authorization': 'Token ' + self.token}).status_code, 200)
            self.assertEqual(self.rpc(client, path='/mcp').status_code, 404)

    def test_real_preview_apply_and_missing_confirmation(self):
        from starlette.testclient import TestClient
        from djangoproject.asgi import application
        headers = {'Authorization': 'Token ' + self.token}
        with TestClient(application) as client:
            result = self.rpc(client, 'tools/call', {'name': 'preview_type_assignment',
                'arguments': {'object_ids': [self.obj.pk], 'type_id': self.typ.pk}}, headers).json()['result']
            self.assertFalse(result.get('isError'), result)
            preview = result.get('structuredContent') or json.loads(result['content'][0]['text'])
            args = {'preview_token': preview['preview_token']}
            rejected = self.rpc(client, 'tools/call', {'name': 'assign_coin_type', 'arguments': args}, headers)
            self.assertTrue(rejected.json()['result']['isError'])
            applied = self.rpc(client, 'tools/call', {'name': 'assign_coin_type',
                'arguments': args | {'confirmed': True}}, headers).json()['result']
            self.assertFalse(applied.get('isError'), applied)
            self.obj.refresh_from_db()
            self.assertEqual(self.obj.Typ_id, self.typ.pk)

    def test_session_requires_csrf_and_rejects_bad_origin(self):
        from django.conf import settings
        from django.middleware.csrf import _get_new_csrf_string
        from starlette.testclient import TestClient
        from djangoproject.asgi import application
        django_client = Client()
        django_client.force_login(self.user)
        csrf = _get_new_csrf_string()
        cookie = f'{settings.SESSION_COOKIE_NAME}={django_client.cookies[settings.SESSION_COOKIE_NAME].value}; csrftoken={csrf}'
        with TestClient(application) as client:
            self.assertEqual(self.rpc(client, headers={'Cookie': cookie}).status_code, 403)
            headers = {'Cookie': cookie, 'X-CSRFToken': csrf}
            self.assertEqual(self.rpc(client, headers=headers).status_code, 200)
            self.assertEqual(self.rpc(client, headers=headers | {'Origin': 'https://evil.example'}).status_code, 403)
