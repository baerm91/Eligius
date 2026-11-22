"""Regressionstests für das Review (Punkte 17–20: Logik, Templates, Formulare)."""
from django.core.cache import cache
from django.test import RequestFactory, TestCase

from .filters import filter_context_key
from .models import AvBeizeichen, Kontaktanfrage, Obj, ObjektAenderung
from .test_bugfix_regressions import Fixtures


class FilterContextTests(TestCase):
    def test_only_true_selects_unbestimmt_paths(self):
        for value, expected in (('True', 'unbestimmt'), ('False', 'default'), ('Alle', 'default'), ('', 'default')):
            request = RequestFactory().get('/', {'unbestimmt': value})
            self.assertEqual(filter_context_key(request), expected, value)


class TemplateLinkTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.beizeichen = AvBeizeichen.objects.create(name='Stern & Mond')
        cls.typ.av_beizeichen = cls.beizeichen
        cls.typ.avleg = 'IMP CAES'
        cls.typ.save()
        cls.obj = Obj.objects.create(invnr="A'1", Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)

    def test_type_page_links_beizeichen_by_name(self):
        html = self.client.get(f'/typ/{self.typ.pk}/').content.decode()
        self.assertIn('/browse/?av_beizeichen=Stern%20%26%20Mond', html)
        self.assertIn('/browse/?avleg=IMP%20CAES" title="Browse">IMP CAES</a>', html)

    def test_detail_page_escapes_js_and_drops_unsupported_filters(self):
        html = self.client.get(f'/objekt/{self.obj.pk}/').content.decode()
        for unsupported in ('?av_offizin=', '?rv_offizin=', '?av_bildrand=', '?rv_bildrand=', '?avleg=-'):
            self.assertNotIn(unsupported, html)


class PublicFormTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.obj = Obj.objects.create(invnr='K1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)

    def setUp(self):
        cache.clear()

    def contact(self, **overrides):
        data = {'name': 'A', 'email': 'a@example.test', 'betreff': 'B', 'nachricht': 'C', **overrides}
        return self.client.post('/kontakt/', data)

    def test_contact_validation_honeypot_and_rate_limit(self):
        self.contact(email='keine-adresse')
        self.contact(nachricht='x' * 6000)
        self.contact(website='http://spam.example')
        self.assertEqual(Kontaktanfrage.objects.count(), 0)
        for _ in range(7):
            self.contact()
        self.assertEqual(Kontaktanfrage.objects.count(), 5)

    def test_change_suggestion_rejects_unknown_field_without_raw_errors(self):
        url = f'/objekt/{self.obj.pk}/aenderung/'
        data = {'name': 'A', 'email': 'a@example.test', 'feld': 'workflow', 'neuer_wert': 'x', 'begruendung': 'y'}
        self.client.post(url, data)
        self.assertEqual(ObjektAenderung.objects.count(), 0)
        self.client.post(url, {**data, 'feld': 'titel'})
        self.assertEqual(ObjektAenderung.objects.count(), 1)

    def test_about_is_served_by_cached_route(self):
        from django.urls import resolve
        from . import views
        # Die gecachte Route aus slg.urls (cache_page-Wrapper), nicht die rohe View.
        self.assertIsNot(resolve('/about/').func, views.about)
        self.assertEqual(self.client.get('/about/').status_code, 200)
