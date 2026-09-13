import json

from asgiref.sync import async_to_sync
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from slg.mcp_server import mcp
from slg.services import public_api
from slg.services.search import _get_filtered_mtoa_queryset


def remote_payload(name, arguments):
    result = async_to_sync(mcp.call_tool)(name, arguments)
    return result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)


@override_settings(ELIGIUS_WEBMCP_ENABLED=True)
class WebMCPTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        # The same domain fixtures used by Remote MCP, committed so real async
        # SDK callbacks can query them on their own database connections.
        from slg.test_mcp import PublicMCPTests
        PublicMCPTests.setUpTestData.__func__(type(self))

    def post_tool(self, name, arguments, navigation=False):
        return self.client.post(reverse('webmcp_navigation' if navigation else 'webmcp_data',
            kwargs={'tool_name': name}), json.dumps(arguments), content_type='application/json')

    def test_schemas_are_identical_to_remote_mcp(self):
        manifest = self.client.get(reverse('webmcp_manifest')).json()
        remote = {t.name: t.input_schema for t in async_to_sync(mcp.list_tools)()}
        self.assertEqual({t['name']: t['inputSchema'] for t in manifest['data_tools']}, remote)
        self.assertEqual(len(manifest['ui_tools']), 6)
        self.assertTrue(all(t['annotations']['readOnlyHint'] for t in manifest['data_tools']))

    def test_browse_remote_webmcp_parity_across_pages(self):
        cases = [
            {}, {'Praegeherren': ['Valens']},
            {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']},
            {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia'], 'Nominal': ['Follis']},
            {'Praegeherren': ['Pescennius Niger']}, {'rv_schlagwort': ['Victoria']},
            {'Slg': [self.collection.pk]}, {'Slg': [self.collection.pk], 'Praegeherren': ['Valens']},
            {'dat_von': 370, 'dat_bis': 380}, {'unbestimmt': True},
        ]
        for filters in cases:
            with self.subTest(filters=filters):
                rows, _, _ = _get_filtered_mtoa_queryset(public_api.filter_request(filters))
                expected = set(rows.values_list('obj_id', flat=True))
                found = set()
                page = 1
                while True:
                    arguments = {'filters': filters, 'page': page, 'page_size': 2}
                    remote = remote_payload('search_objects', arguments)
                    response = self.post_tool('search_objects', arguments)
                    self.assertEqual(response.status_code, 200, response.content)
                    web = response.json()
                    self.assertEqual(web, remote)
                    found.update(item['id'] for item in web['results'])
                    if not web['has_more']:
                        break
                    page += 1
                self.assertEqual(found, expected)

    def test_all_data_tools_share_outputs_and_public_policy(self):
        filters = {'Praegeherren': ['Valens'], 'Muenzstaette': ['Siscia']}
        for name, arguments in (
            ('get_facets', {'facet': 'Praegeherren', 'filters': filters}),
            ('get_distribution', {'dimension': 'Praegeherren', 'filters': filters}),
            ('get_statistics', {'filters': filters}),
            ('get_object', {'object_id': self.ids[0]}),
        ):
            with self.subTest(name=name):
                response = self.post_tool(name, arguments)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json(), remote_payload(name, arguments))
                self.assertNotIn('INTERNAL', response.content.decode())
        values = self.post_tool('get_facets', {'facet': 'Paket'}).json()['results']
        self.assertEqual([v['id'] for v in values], [self.public_package.pk])
        self.assertEqual(self.post_tool('search_objects', {'filters': {'Paket': [self.private_package.pk]}}).json()['total'], 0)

    def test_navigation_and_browse_encoding(self):
        for name, arguments, url in (
            ('navigate_to_object', {'object_id': self.ids[0]}, reverse('Objekt', kwargs={'id': self.ids[0]})),
            ('navigate_to_coin_type', {'type_id': self.typ.pk}, reverse('Typ', kwargs={'id': self.typ.pk})),
            ('open_collection', {'collection_id': self.collection.pk}, reverse('Sammlung', kwargs={'id': self.collection.pk})),
            ('clear_browse_filters', {}, reverse('Objektliste')),
        ):
            self.assertEqual(self.post_tool(name, arguments, True).json(), {'url': url})
        filters = {'Praegeherren': ['Valens', 'Name & Sonderzeichen'], 'unbestimmt': True}
        result = self.post_tool('set_browse_filters', {'filters': filters}, True)
        self.assertEqual(result.json(), {'url': '/browse/?Praegeherren=Valens&Praegeherren=Name+%26+Sonderzeichen&unbestimmt=True'})

    def test_current_context_and_no_account_parameter_leaks(self):
        for url, expected in (
            ('/browse/?Praegeherren=Valens&Praegeherren=Pescennius+Niger&page=4&auth_token=SECRET',
             {'page_type': 'browse', 'filters': {'Praegeherren': ['Valens', 'Pescennius Niger']}}),
            (f'/objekt/{self.ids[0]}/', {'page_type': 'object', 'object_id': self.ids[0],
                                       'type_id': self.typ.pk, 'collection_id': self.collection.pk}),
            (f'/typ/{self.typ.pk}/', {'page_type': 'coin_type', 'type_id': self.typ.pk}),
            (f'/slg/{self.collection.pk}/', {'page_type': 'collection', 'collection_id': self.collection.pk}),
            ('/admin/?token=SECRET', {'page_type': 'other'}),
        ):
            response = self.client.get(reverse('webmcp_context'), {'url': url})
            self.assertEqual(response.json(), expected)
        self.assertEqual(self.client.get(reverse('webmcp_context'), {'url': 'https://evil.example/'}).status_code, 400)

    def test_bad_filters_ids_and_generic_actions_are_rejected(self):
        for name, arguments in (
            ('search_objects', {'filters': {'Typ__workflow_id': 1}}),
            ('search_objects', {'page_size': 101}),
            ('get_object', {'object_id': 999999}), ('run_orm', {}),
        ):
            self.assertEqual(self.post_tool(name, arguments).status_code, 400)
        for name, arguments in (
            ('navigate_url', {'url': 'https://evil.example'}),
            ('navigate_to_object', {'object_id': '../admin'}),
            ('navigate_to_object', {'object_id': 999999}),
            ('navigate_to_object', {'object_id': self.ids[0], 'url': '/admin/'}),
            ('set_browse_filters', {'filters': {'sql': 'SELECT 1'}}),
        ):
            self.assertEqual(self.post_tool(name, arguments, True).status_code, 400)
        path = reverse('webmcp_data', kwargs={'tool_name': 'search_objects'})
        self.assertEqual(self.client.get(path).status_code, 405)
        self.assertEqual(self.client.post(path, '[]', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(path, '{', content_type='application/json').status_code, 400)

    @override_settings(ELIGIUS_WEBMCP_ENABLED=False)
    def test_disabled_feature_has_no_script_or_endpoints(self):
        self.assertEqual(self.client.get(reverse('webmcp_manifest')).status_code, 404)
        response = self.client.get(reverse('lab'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'eligius-webmcp.js')
