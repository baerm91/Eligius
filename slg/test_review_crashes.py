"""Regressionstests für das Review (Punkte 13–16: Abstürze, Datenverlust, Sync)."""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, TestCase, override_settings

from .import_utils import parse_object_id
from .models import Obj, Slg
from .test_bugfix_regressions import Fixtures


class ParseObjectIdTests(TestCase):
    def test_accepts_excel_floats_but_rejects_fractions(self):
        self.assertEqual(parse_object_id('12'), 12)
        self.assertEqual(parse_object_id('12.0'), 12)
        for bad in ('12.5', 'abc', '0', '-3', 'nan'):
            with self.assertRaises(ValueError, msg=bad):
                parse_object_id(bad)


class InvalidParameterTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.obj = Obj.objects.create(invnr='C1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        cls.staff = User.objects.create_user('staff', password='x', is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(codename='view_obj'))

    def test_unicode_digits_do_not_crash(self):
        self.assertEqual(self.client.get('/objekt_detail_partial/', {'id': '²'}).status_code, 404)
        for params in ({'sammlung': '²'}, {'person': '²'}, {'von': '²'}):
            self.assertLess(self.client.get('/api/ereignisse/', params).status_code, 500, params)

    def test_context_api_ignores_non_numeric_dates(self):
        response = self.client.get(f'/api/muenzen/{self.obj.pk}/kontext/', {'dat_von': 'abc'})
        self.assertEqual(response.status_code, 200)

    def test_json_array_body_is_400(self):
        self.client.force_login(self.staff)
        response = self.client.post('/export_coins/', '[]', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_duplicate_invnr_in_person_api_is_409(self):
        other = Slg.objects.create(name='Sammlung B')
        Obj.objects.create(invnr='C1', Slg=other, workflow=self.controlled)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/objekt/C1/personen/').status_code, 409)


class WebSocketTests(TestCase):
    def test_editor_mcp_rejects_websocket(self):
        from .editor_mcp import authenticated_app
        sent = []

        async def receive():
            return {'type': 'websocket.connect'}

        async def send(message):
            sent.append(message)

        asyncio.run(authenticated_app({'type': 'websocket', 'path': '/mcp/editor', 'headers': []}, receive, send))
        self.assertEqual(sent, [{'type': 'websocket.close', 'code': 1008}])


class AdminAndExportTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()

    def test_my_objects_admin_has_no_bulk_delete(self):
        from django.contrib import admin
        from .models import MyObjects
        superuser = User.objects.create_superuser('root', 'r@example.test', 'x')
        request = RequestFactory().get('/')
        request.user = superuser
        self.assertNotIn('delete_selected', admin.site._registry[MyObjects].get_actions(request))

    def test_lsno_export_uses_object_muenzstand_and_few_queries(self):
        from .models import Muenzstand
        from .resources import ObjLSNOResource
        stand = Muenzstand.objects.create(name='Stadt')
        for i in range(5):
            Obj.objects.create(invnr=f'L{i}', Slg=self.slg, workflow=self.controlled, idfk_Muenzstand=stand)
        resource = ObjLSNOResource()
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            dataset = resource.export(Obj.objects.all())
        # Zählung + Objekte + Prefetches – unabhängig von der Objektanzahl (vorher >16/Objekt)
        self.assertLessEqual(len(queries), 6)
        self.assertEqual(set(dataset['Münzstand']), {'Stadt'})

    def test_sync_with_empty_list(self):
        from .mtoa_sync import sync_objs_to_mtoa
        self.assertEqual(sync_objs_to_mtoa([]), (0, 0))


@override_settings(ELIGIUS_NOMISMA_CACHE_DIR=tempfile.mkdtemp())
class NomismaCacheTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()

    def test_write_error_falls_back_to_streaming(self):
        from . import nomisma_rdf
        request = RequestFactory().get('/')

        def broken(*args, **kwargs):
            yield 'x'
            raise OSError('Kein Speicherplatz')

        with patch.object(nomisma_rdf, 'iter_collection_rdf', broken):
            self.assertIsNone(nomisma_rdf.cached_dump(self.slg, request, force=True))
        leftovers = [p for p in Path(nomisma_rdf.cache_path(self.slg).parent).iterdir() if p.suffix == '.tmp']
        self.assertEqual(leftovers, [])

