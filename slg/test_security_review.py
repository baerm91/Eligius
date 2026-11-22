"""Regressionstests für das Security-Review (Punkte 5–12)."""
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .export_safety import neutralize_formula
from .filters import apply_filters
from .forms import DetailUpdateForm, StaffDetailUpdateForm
from .models import OffizinSymbol, Obj, Paket, Person, SlgInformation
from .test_bugfix_regressions import Fixtures


class FormulaInjectionTests(TestCase):
    def test_neutralizes_formulas_but_keeps_numbers(self):
        self.assertEqual(neutralize_formula('=HYPERLINK("x")'), "'=HYPERLINK(\"x\")")
        self.assertEqual(neutralize_formula('@SUM(A1)'), "'@SUM(A1)")
        self.assertEqual(neutralize_formula('-44'), '-44')
        self.assertEqual(neutralize_formula(-44), -44)
        self.assertEqual(neutralize_formula('Denar'), 'Denar')


class InternalEndpointPermissionTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.plain = User.objects.create_user('plain', password='x')

    def test_plain_user_is_rejected(self):
        self.client.force_login(self.plain)
        for method, url in (('post', reverse('export_coins_api')),
                            ('post', reverse('export_coin_states_api')),
                            ('get', reverse('export-obj-lsno'))):
            response = getattr(self.client, method)(url, {'invnrs': ['X']}, content_type='application/json') \
                if method == 'post' else self.client.get(url)
            self.assertEqual(response.status_code, 403, url)
        for url in (reverse('catalog_generate') + '?obj_ids=1', reverse('excel_ocre_enrich')):
            self.assertIn(self.client.get(url).status_code, (302, 403), url)


class BeizeichenHtmlTests(TestCase):
    def test_question_mark_in_symbol_url_is_not_replaced(self):
        from .views import render_beizeichen_html
        OffizinSymbol.objects.create(name='M1', svg_link='https://img.example.test/s.svg?v=1')
        html, used = render_beizeichen_html('[M1] ? <b>', None, 'Offizin')
        self.assertIn('s.svg?v=1', html)
        self.assertIn('Offizin', html)
        self.assertIn('&lt;b&gt;', html)
        self.assertTrue(used)

    def test_brackets_cannot_break_out_of_attributes(self):
        from .views import render_beizeichen_html
        OffizinSymbol.objects.create(name='X" onerror="alert(1)', svg_link='https://img.example.test/x.svg')
        html, _ = render_beizeichen_html('[X" onerror="alert(1)]', None, None)
        self.assertNotIn('onerror="alert', html)


class PaketFilterTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.hidden = Paket.objects.create(name='intern', online_freigegeben=False, slug='intern')
        cls.obj = Obj.objects.create(invnr='P1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        cls.obj.pakete.add(cls.hidden)

    def test_unpublished_package_does_not_filter(self):
        request = RequestFactory().get('/', {'Paket': str(self.hidden.pk)})
        self.assertFalse(apply_filters(request, Obj.objects.all()).exists())
        Paket.objects.filter(pk=self.hidden.pk).update(online_freigegeben=True)
        self.assertTrue(apply_filters(request, Obj.objects.all()).exists())


class DetailUpdateFormTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.obj = Obj.objects.create(invnr='U1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        cls.staff = User.objects.create_user('staff', password='x', is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(codename='change_obj'))

    def test_staff_form_hides_privileged_fields(self):
        fields = set(StaffDetailUpdateForm().fields)
        for name in ('workflow', 'freigabe', 'Slg', 'pakete', 'faelschung', 'fmid', 'interne_anmerkungen'):
            self.assertNotIn(name, fields)
        self.assertNotIn('idfk_Ref', DetailUpdateForm().fields)

    def test_missing_object_is_404(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/id/999999/update/').status_code, 404)


class MatchPersonenTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.person = Person.objects.create(name='Domitian')
        cls.event = SlgInformation.objects.create(Slg=cls.slg, name='E', raw_personen='')
        cls.event.person.add(cls.person)

    def test_empty_raw_personen_keeps_links_and_requires_change(self):
        from .admin import match_personen_exact
        self.assertEqual(match_personen_exact.allowed_permissions, ['change'])
        model_admin = admin.site._registry[SlgInformation]
        with patch.object(model_admin, 'message_user'):
            match_personen_exact(model_admin, None, SlgInformation.objects.all())
        self.assertEqual(list(self.event.person.all()), [self.person])


class PersonLinkDownloadTests(Fixtures, TestCase):
    def test_invalid_gnd_never_fetches(self):
        from .admin import PersonView
        person = Person.objects.create(name='X', DNB='http://evil.example/../x')
        view = admin.site._registry[Person]
        self.assertIsInstance(view, PersonView)
        with patch('slg.admin.requests.get') as get, patch.object(view, 'message_user'):
            view._download_person_links(None, person)
        get.assert_not_called()
