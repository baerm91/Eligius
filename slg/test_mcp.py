from django.test import TestCase, SimpleTestCase, RequestFactory
from django.urls import reverse

from slg.models import (Obj, Slg, Muenztyp, MuenztypObjektAnzeige, MtoaPerson,
                        Person, PersonFunktion, Mzstaette, Nominal, Paket)
from slg.services import public_api
from slg.views import _get_filtered_mtoa_queryset, facet_api
from slg.signals import disable_mtoa_sync, enable_mtoa_sync


class PublicMCPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        disable_mtoa_sync()
        try:
            cls.collection = Slg.objects.create(name='Sammlung X')
            cls.other = Slg.objects.create(name='Sammlung Y')
            cls.mint = Mzstaette.objects.create(name='Siscia')
            cls.nominal = Nominal.objects.create(name='Follis')
            cls.ruler = PersonFunktion.objects.create(pk=1, name='Prägeherr')
            cls.depicted = PersonFunktion.objects.create(pk=2, name='Dargestellt')
            cls.valens = Person.objects.create(name='Valens')
            cls.niger = Person.objects.create(name='Pescennius Niger')
            cls.typ = Muenztyp.objects.create(muenztyptitel='Valens Siscia',
                titel='Valens', Objekttyp=None, Herstellung=None, workflow=None,
                Mzstaette=cls.mint, Nominal=cls.nominal, dat_von=364, dat_bis=378)
            cls.ids = []
            for index in range(5):
                classified = index != 3
                obj = Obj.objects.create(invnr=f'MCP-{index}', Slg=cls.collection if index < 4 else cls.other,
                    Typ=cls.typ if classified else None, Objekttyp=None, workflow=None,
                    freigabe=index % 2 == 0, TempTyp='INTERNAL-DRAFT', anmerkung='INTERNAL-NOTE')
                cls.ids.append(obj.pk)
                row = MuenztypObjektAnzeige.objects.create(obj_id=obj.pk, invnr=obj.invnr,
                    Slg=obj.Slg.name, slg_fk=obj.Slg, typ_fk=obj.Typ, typ='Valens Siscia' if classified else None,
                    mzstaette='Siscia' if index < 4 else 'Roma', mzstaette_fk=cls.mint if index < 4 else None,
                    nominal='Follis', nominal_fk=cls.nominal, datierung_von=364, datierung_bis=378,
                    rv_schlagworte='Victoria' if index in (0, 3) else 'Concordia')
                MtoaPerson.objects.create(mtoa=row, person=cls.niger if index == 2 else cls.valens,
                    funktion=cls.depicted if index == 1 else cls.ruler, appears_on_rev=index == 1)
            cls.public_package = Paket.objects.create(name='Public package', titel_oeffentlich='Public', online_freigegeben=True)
            cls.private_package = Paket.objects.create(name='INTERNAL-PACKAGE', titel_oeffentlich='INTERNAL-TITLE', online_freigegeben=False)
            Obj.objects.get(pk=cls.ids[0]).pakete.add(cls.public_package, cls.private_package)
        finally:
            enable_mtoa_sync()

    def test_browse_mcp_ids_and_expected_matches(self):
        cases = [
            ({'Praegeherren': ['Valens']}, {0, 3, 4}),
            ({'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']}, {0, 3}),
            ({'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia'], 'Nominal': ['Follis']}, {0, 3}),
            ({'Praegeherren': ['Pescennius Niger']}, {2}),
            ({'rv_schlagwort': ['Victoria']}, {0, 3}),
            ({'Slg': [self.collection.pk]}, {0, 1, 2, 3}),
            ({'Slg': [self.collection.pk], 'Praegeherren': ['Valens']}, {0, 3}),
            ({'dat_von': 370, 'dat_bis': 380}, {0, 1, 2, 3, 4}),
            ({'dat_von': 400, 'dat_bis': 410}, set()),
            ({'unbestimmt': True}, {3}),
            ({'unbestimmt': False}, {0, 1, 2, 4}),
            ({'Dargestellte_RV': ['Valens']}, {1}),
        ]
        for filters, indexes in cases:
            with self.subTest(filters=filters):
                request = public_api.filter_request(filters)
                rows, _, _ = _get_filtered_mtoa_queryset(request)
                browse_ids = set(rows.values_list('obj_id', flat=True))
                mcp_ids = set()
                page = 1
                while True:
                    result = public_api.search_objects(filters, page, 2)
                    mcp_ids.update(obj['id'] for obj in result['results'])
                    if not result['has_more']:
                        break
                    page += 1
                self.assertEqual(browse_ids, mcp_ids)
                self.assertEqual(mcp_ids, {self.ids[i] for i in indexes})

    def test_facet_person_roles_and_distribution(self):
        filters = {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']}
        distribution = public_api.get_distribution('Praegeherren', filters)
        self.assertEqual(distribution['total'], 2)
        self.assertEqual(distribution['results'], [{'name': 'Valens', 'count': 2, 'id': self.valens.pk, 'percentage': 100.0}])
        values = public_api.get_facets('Praegeherren', filters)['results']
        self.assertEqual({v['name']: v['count'] for v in values}, {'Valens': 2, 'Pescennius Niger': 1})
        response = facet_api(RequestFactory().get('/api/facet/', {
            'facet': 'Praegeherren', 'Praegeherren': 'Valens', 'Muenzstaette': 'Siscia'}))
        self.assertEqual(response.data, values)

    def test_private_package_never_returned_or_searchable(self):
        values = public_api.get_facets('Paket')['results']
        self.assertEqual(values, [{'name': 'Public', 'count': 1, 'id': self.public_package.pk}])
        self.assertEqual(public_api.search_objects({'Paket': [self.private_package.pk]})['total'], 0)

    def test_public_representation_and_policy(self):
        for object_id in self.ids:
            data = public_api.get_object(object_id)
            self.assertNotIn('INTERNAL', str(data))
            self.assertTrue(data['url'].startswith('https://example.test/objekt/'))
        self.assertEqual(public_api.search_objects()['total'], 5)

    def test_pagination_is_exhaustive_and_out_of_range_empty(self):
        self.assertEqual(public_api.search_objects(page=4, page_size=2)['results'], [])
        self.assertEqual(public_api.get_statistics()['total'], 5)
        first = public_api.get_facets('Praegeherren', page_size=1)
        self.assertTrue(first['has_more'])
        self.assertEqual(first['total'], 2)

    def test_lab_health(self):
        response = self.client.get(reverse('lab'))
        self.assertContains(response, 'https://example.test/mcp')
        self.assertContains(response, 'Connect your AI')
        self.assertEqual(self.client.get('/health').json()['status'], 'ok')


class MCPInputTests(SimpleTestCase):
    def test_rejects_orm_and_bad_values(self):
        for filters in ({'Typ__workflow__name': 'secret'}, {'sql': 'SELECT 1'},
                        {'Slg': {'model': 'Obj'}}, {'dat_von': 'bad'},
                        {'dat_von': 400, 'dat_bis': 300}, {'unbestimmt': 'maybe'}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                public_api.filter_request(filters)
        for page, size in ((0, 25), (1, 101), (1, 0)):
            with self.assertRaises(ValueError):
                public_api.page_bounds(page, size)

    def test_real_transport_handshake_tools_and_rebinding(self):
        from unittest.mock import patch
        from starlette.testclient import TestClient
        from djangoproject.asgi import application
        headers = {'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': '2025-03-26'}
        with TestClient(application) as client:
            response = client.post('/mcp', headers=headers, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                           'clientInfo': {'name': 'eligius-test', 'version': '1'}}})
            self.assertEqual(response.status_code, 200)
            self.assertIn('serverInfo', response.json()['result'])
            self.assertNotIn('mcp-session-id', response.headers)
            response = client.post('/mcp', headers=headers, json={
                'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
            tool_list = response.json()['result']['tools']
            self.assertEqual({t['name'] for t in tool_list}, {
                'search_objects', 'get_object', 'get_facets', 'get_distribution', 'get_statistics'})
            self.assertTrue(all(t['annotations']['readOnlyHint'] for t in tool_list))
            with patch('slg.services.public_api.get_statistics', return_value={'total': 7}):
                response = client.post('/mcp', headers=headers, json={
                    'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                    'params': {'name': 'get_statistics', 'arguments': {}}})
                self.assertNotIn('error', response.json())
                self.assertIn('7', str(response.json()['result']))
            response = client.post('/mcp', headers=dict(headers, Host='evil.example'), json={})
            self.assertEqual(response.status_code, 421)
            response = client.post('/mcp', headers=dict(headers, Origin='https://evil.example'), json={})
            self.assertEqual(response.status_code, 403)
