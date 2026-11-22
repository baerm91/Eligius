"""Regressionstests für die Sicherheitsfixes (XSS, ORM-Traversal, SSRF, Rechte)."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from slg import admin as slg_admin
from slg.authentication import QueryParamTokenAuthentication
from slg.models import Obj, ObjektAenderung, Objekttyp, OffizinSymbol, Workflow


def _perm(codename):
    return Permission.objects.get(content_type__app_label='slg', codename=codename)


class SecurityFixturesMixin:
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        Workflow.objects.create(pk=1, name='neu', reihenfolge=1)
        cls.kontrolliert = Workflow.objects.create(pk=2, name='kontrolliert', reihenfolge=2)
        Objekttyp.objects.create(pk=1, name='Münze')
        cls.obj = Obj.objects.bulk_create([
            Obj(invnr='SEC-1', titel='Original', Objekttyp_id=1, workflow_id=1),
        ])[0]
        cls.plain_user = User.objects.create_user(username='plain', password='pw-plain-123')
        cls.staff_no_perm = User.objects.create_user(username='staff0', password='x', is_staff=True)
        cls.editor = User.objects.create_user(username='editor', password='x', is_staff=True)
        cls.editor.user_permissions.add(_perm('view_obj'), _perm('change_obj'))
        cls.superuser = User.objects.create_superuser(username='root', email='r@example.test', password='x')
        ObjektAenderung.objects.create(
            objekt=cls.obj, name='x', email='x@example.test', feld='titel',
            alter_wert='a', neuer_wert='b', begruendung='c', bearbeitet_von=cls.superuser,
        )


class ExportXlsxTests(SecurityFixturesMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_non_staff_is_rejected(self):
        self.client.force_authenticate(self.plain_user)
        self.assertEqual(self.client.get('/export_xlsx/').status_code, 403)

    def test_orm_traversal_to_password_is_rejected(self):
        self.client.force_authenticate(self.editor)
        for key in (
            'aenderungen__bearbeitet_von__password__startswith',
            'aenderungen__bearbeitet_von__auth_token__key__startswith',
            'aenderungen__bearbeitet_von__email__startswith',
        ):
            response = self.client.get('/export_xlsx/', {key: 'p'})
            self.assertEqual(response.status_code, 400, key)

    def test_valid_export_and_token_param_is_not_a_filter(self):
        self.client.force_authenticate(self.editor)
        response = self.client.get('/export_xlsx/', {'token': 'abc', 'workflow__id__exact': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])


class ObjektDetailPermissionTests(SecurityFixturesMixin, TestCase):
    url = '/api/objekt/SEC-1/'

    def setUp(self):
        self.client = APIClient()

    def test_plain_user_cannot_patch(self):
        self.client.force_authenticate(self.plain_user)
        self.assertEqual(self.client.patch(self.url, {'titel': 'x'}, format='json').status_code, 403)

    def test_staff_without_model_permission_cannot_patch(self):
        self.client.force_authenticate(self.staff_no_perm)
        self.assertEqual(self.client.patch(self.url, {'titel': 'x'}, format='json').status_code, 403)

    def test_editor_can_patch_descriptive_fields_but_not_workflow(self):
        self.client.force_authenticate(self.editor)
        response = self.client.patch(
            self.url, {'titel': 'Neu', 'workflow': self.kontrolliert.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.titel, 'Neu')
        self.assertEqual(self.obj.workflow_id, 1)

    def test_m2m_null_is_a_validation_error_not_500(self):
        self.client.force_authenticate(self.editor)
        response = self.client.patch(self.url, {'Herstellungsmerkmale': None}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_superuser_can_change_workflow(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.patch(self.url, {'workflow': self.kontrolliert.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.workflow_id, self.kontrolliert.pk)


class WriteEndpointPermissionTests(SecurityFixturesMixin, TestCase):
    def test_vocabulary_write_requires_staff(self):
        client = APIClient()
        client.force_authenticate(self.plain_user)
        self.assertEqual(client.post('/api/nominal/', {'name': 'X'}, format='json').status_code, 403)
        self.assertEqual(client.post('/api/muenztyp/konkordanz/', {}, format='json').status_code, 403)
        self.assertEqual(client.post('/api/muenztyp_from_concordia/', {}, format='json').status_code, 403)

    def test_obj_create_and_update_views_require_login(self):
        for url in ('/create/', f'/id/{self.obj.pk}/edit/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn('login', response['Location'])

    def test_obj_create_view_forbidden_for_non_staff(self):
        self.client.force_login(self.plain_user)
        self.assertEqual(self.client.get('/create/').status_code, 403)

    def test_mutating_admin_actions_require_change_permission(self):
        for func in (
            slg_admin.MuenztypAdmin.verkupfern, slg_admin.MuenztypAdmin.nummisieren,
            slg_admin.MuenztypAdmin.vermessingere, slg_admin.MuenztypAdmin.material_vom_nominal,
            slg_admin.MuenztypAdmin.transpadana, slg_admin.material_von_nominal_uebernehmen,
            slg_admin.material_von_muenztyp_uebernehmen, slg_admin.ObjAdmin.sync_mtoa_selected,
            slg_admin.MyObjectsAdmin.SlgHlHaupt,
        ):
            self.assertEqual(getattr(func, 'allowed_permissions', None), ('change',), func.__name__)

    def test_download_legenden_requires_change_permission(self):
        viewer = get_user_model().objects.create_user(username='viewer', password='x', is_staff=True)
        viewer.user_permissions.add(_perm('view_obj'))
        self.client.force_login(viewer)
        response = self.client.post(f'/admin/slg/obj/{self.obj.pk}/change/', {'_download_legenden': '1'})
        self.assertEqual(response.status_code, 403)


class TypeLinkSafetyTests(TestCase):
    def test_only_exact_allowed_hosts(self):
        ok = [
            'https://numismatics.org/ocre/id/ric.1(2).aug.1',
            'numismatics.org/ocre/id/x',
            'https://rpc.ashmus.ox.ac.uk/coins/1/1',
        ]
        bad = [
            'http://evil.example/numismatics.org/',
            'http://numismatics.org.evil.example/',
            'http://127.0.0.1/?x=rpc.ashmus.ox.ac.uk/',
            'file:///etc/passwd#numismatics.org/',
            'http://user@numismatics.org/',
            'http://numismatics.org:8080/',
        ]
        for link in ok:
            self.assertIsNotNone(slg_admin._normalize_type_link(link)[0], link)
        for link in bad:
            self.assertIsNone(slg_admin._normalize_type_link(link)[0], link)

    def test_sparql_iri_injection_rejected(self):
        with self.assertRaises(ValueError):
            slg_admin._safe_sparql_iri('http://numismatics.org/x> ?p ?o } SELECT * WHERE { ?s ?p ?o')

    def test_process_download_infos_does_no_request_for_foreign_host(self):
        obj = mock.Mock(link='http://169.254.169.254/latest/numismatics.org/')
        with mock.patch.object(slg_admin.requests, 'get') as get:
            success, _ = slg_admin.process_download_infos(obj)
        self.assertFalse(success)
        get.assert_not_called()

    def test_safe_get_blocks_redirect_to_foreign_host(self):
        redirect = mock.Mock(is_redirect=True, is_permanent_redirect=False,
                             headers={'Location': 'http://127.0.0.1/admin'})
        with mock.patch.object(slg_admin.requests, 'get', return_value=redirect) as get:
            with self.assertRaises(RuntimeError):
                slg_admin._safe_get('https://rpc.ashmus.ox.ac.uk/coins/1', ('rpc.ashmus.ox.ac.uk',))
        self.assertEqual(get.call_count, 1)


class EscapingTests(TestCase):
    def test_offizin_symbol_html_is_escaped(self):
        symbol = OffizinSymbol(name='<script>alert(1)</script>', svg_link='javascript:alert(1)',
                               uri_reference='" onmouseover="alert(1)')
        html = symbol.get_svg_html()
        self.assertNotIn('<script>', html)
        self.assertNotIn('javascript:', html)
        self.assertNotIn('onmouseover="', html)

    def test_json_for_script_prevents_script_breakout(self):
        from slg.views import json_for_script
        payload = json_for_script({'name': '</script><script>alert(1)</script>'})
        self.assertNotIn('</script>', payload)


class TokenAuthTests(SecurityFixturesMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.token = Token.objects.create(user=self.editor)
        self.factory = RequestFactory()

    def _auth(self, request):
        from rest_framework.request import Request
        return QueryParamTokenAuthentication().authenticate(Request(request))

    def test_query_param_token_disabled_by_default(self):
        self.assertIsNone(self._auth(self.factory.get('/', {'token': self.token.key})))

    @override_settings(ELIGIUS_ALLOW_QUERY_PARAM_TOKEN_AUTH=True)
    def test_query_param_token_opt_in(self):
        user, _ = self._auth(self.factory.get('/', {'token': self.token.key}))
        self.assertEqual(user, self.editor)

    def test_x_auth_token_header(self):
        user, _ = self._auth(self.factory.get('/', HTTP_X_AUTH_TOKEN=self.token.key))
        self.assertEqual(user, self.editor)

    def test_obtain_auth_token_is_throttled(self):
        client = APIClient()
        statuses = [
            client.post('/api/api-token-auth/', {'username': 'plain', 'password': 'wrong'}, format='json').status_code
            for _ in range(25)
        ]
        self.assertIn(429, statuses)
