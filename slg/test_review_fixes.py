"""Regressionstests zur Fehlerliste "Mittel" (Suche, UI/JS, OAI/SEO, Performance & Deployment)."""
import re
from xml.etree import ElementTree as ET

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from .filters import apply_filters, build_filters
from .models import (Muenzstand, MuenztypObjektAnzeige, Nominal, Obj, Obj_Ref, Paket, Ref, SlgInformation,
                     stempelstellung_parts)
from .mtoa_sync import sync_objs_to_mtoa
from .services import public_api
from .test_bugfix_regressions import Fixtures

OAI = {'oai': 'http://www.openarchives.org/OAI/2.0/'}


def get(query):
    return RequestFactory().get('/browse/', query)


class FilterLogicTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.nominal = Nominal.objects.create(id=12, name='Denar')
        cls.other_nominal = Nominal.objects.create(id=1, name='Obol')
        cls.stand = Muenzstand.objects.create(name='Stadt')
        cls.typ.Nominal = cls.nominal
        cls.typ.save()
        cls.typed = Obj.objects.create(invnr='T1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        cls.untyped = Obj.objects.create(invnr='U1', Slg=cls.slg, idfk_Muenzstand=cls.stand,
                                         workflow=cls.controlled)

    def test_in_lookup_uses_whole_value_not_characters(self):
        general, _ = build_filters(get({'Nominal_id': '12'}))
        self.assertIn(('Typ__Nominal_id__in', ['12']), general[0].children)
        hits = apply_filters(get({'Nominal_id': '12'}), Obj.objects.all())
        self.assertEqual(list(hits), [self.typed])
        self.assertFalse(apply_filters(get({'Nominal_id': '1'}), Obj.objects.all()).exists())

    def test_unbestimmt_muenzstand_filters_on_object(self):
        hits = apply_filters(get({'unbestimmt': '1', 'Muenzstand': 'Stadt'}), Obj.objects.all())
        self.assertEqual(list(hits), [self.untyped])

    def test_muenztyp_filter_wildcard_and_limit(self):
        from .views import MuenztypFilterView
        self.assertEqual(MuenztypFilterView._wildcard_to_lookup('A?C'), ('iregex', 'A.C'))
        self.assertEqual(MuenztypFilterView._wildcard_to_lookup('^A_B'), ('istartswith', 'A_B'))
        self.assertEqual(MuenztypFilterView.MAX_LIMIT, 5000)

    def test_filter_request_rejects_bool_and_non_numeric_ids_but_ignores_empty(self):
        self.assertEqual(dict(public_api.filter_request({'dat_von': '', 'dat_bis': ''}).GET), {})
        for filters in ({'dat_von': True}, {'Slg': 'abc'}, {'Nominal_id': ['12', 'x']}):
            with self.assertRaises(ValueError):
                public_api.filter_request(filters)
        self.assertEqual(public_api.filter_request({'Slg': ' 3 '}).GET.getlist('Slg'), ['3'])

    def test_webmcp_page_context_accepts_regular_browse_urls(self):
        from .webmcp import _page_context
        url = reverse('Objektliste') + '?dat_von=&dat_bis=&Slg=abc&Nominal=Denar'
        context = _page_context(url)
        self.assertEqual(context['page_type'], 'browse')
        self.assertEqual(context['filters'], {'Nominal': ['Denar']})


class FacetTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.published = Paket.objects.create(name='intern-a', titel_oeffentlich='', online_freigegeben=True,
                                             slug='paket-a')
        cls.hidden = Paket.objects.create(name='intern-b', online_freigegeben=False, slug='paket-b')
        cls.published.vergleichspakete.add(cls.hidden)
        cls.ref = Ref.objects.create(abk='RIC', zitat='Roman Imperial Coinage')
        cls.obj = Obj.objects.create(invnr='F1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        cls.obj.pakete.add(cls.published, cls.hidden)
        Obj_Ref.objects.create(idfk_Obj=cls.obj, idfk_Ref=cls.ref, nummer='1', nach=False)
        sync_objs_to_mtoa([cls.obj.pk])

    def test_paket_facet_falls_back_to_internal_name(self):
        values = public_api.facet_values(get({}), 'Paket')
        self.assertEqual(values, [{'name': 'intern-a', 'count': 1, 'id': self.published.pk}])

    def test_ref_facet_counts_obj_ref_of_typed_objects(self):
        self.assertEqual(public_api.facet_values(get({}), 'Ref'), [{'name': 'RIC', 'count': 1}])

    def test_unpublished_comparison_packages_are_hidden(self):
        from .views import _get_package_comparison_packages
        self.assertEqual(_get_package_comparison_packages(self.published), [])


class TimelineTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.open_end = SlgInformation.objects.create(dat_von=1500, dat_bis=None, Slg=cls.slg, name='offen')
        cls.later = SlgInformation.objects.create(dat_von=1700, dat_bis=1710, Slg=cls.slg, name='später')

    def test_bis_keeps_events_without_end_and_sammlung_title(self):
        from .helpers import get_timeline_data
        data = get_timeline_data(get({'bis': '1600', 'sammlung': str(self.slg.pk)}))
        self.assertEqual([e['name'] for e in data['ereignisse']], ['offen'])
        self.assertEqual(data['title'], f'Geschichte der {self.slg.name}')

    def test_free_text_queries_are_not_cached(self):
        cache.clear()
        self.assertEqual(self.client.get('/api/ereignisse/', {'thema': 'x' * 50}).status_code, 200)
        self.assertFalse(any(str(key).find('timeline_api') >= 0 for key in getattr(cache, '_cache', {})))


class ExportAndSeoTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.slg.kulturpool_export_erlaubt = True
        cls.slg.save()
        cls.obj = Obj.objects.create(invnr='E1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled,
                                     stempelstellung=6)
        cls.other = Obj.objects.create(invnr='E2', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        cls.third = Obj.objects.create(invnr='E3', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)

    def oai(self, **params):
        root = ET.fromstring(self.client.get(reverse('oai_endpoint'), params).content)
        return root, root.find('oai:request', OAI), root.find('oai:error', OAI)

    def test_oai_error_echo_identifier_uri_and_root_set(self):
        _, request, error = self.oai(verb='ListRecords', metadataPrefix='bogus')
        self.assertEqual(error.get('code'), 'cannotDisseminateFormat')
        self.assertEqual(request.attrib, {'verb': 'ListRecords', 'metadataPrefix': 'bogus'})
        _, request, error = self.oai(verb='ListSets', resumptionToken='kaputt')
        self.assertEqual(error.get('code'), 'badResumptionToken')
        self.assertEqual(request.get('resumptionToken'), 'kaputt')
        _, request, error = self.oai(verb='GetRecord', metadataPrefix='edm', identifier='kein uri')
        self.assertEqual(error.get('code'), 'badArgument')
        self.assertEqual(request.attrib, {})
        root, _, _ = self.oai(verb='ListSets')
        self.assertEqual(root.findall('.//oai:setSpec', OAI)[0].text, 'eligius')

    def test_die_axis_without_hours(self):
        from .structured_data import _die_axis
        self.assertEqual(stempelstellung_parts(0), (None, 'unbekannt'))
        self.assertEqual(stempelstellung_parts('13'), (None, 'nicht feststellbar'))
        self.assertEqual(stempelstellung_parts(6), (6, None))
        self.assertNotIn('unitText', _die_axis(13))
        self.assertEqual(_die_axis(6)['unitText'], 'h')

    def test_ruler_meta_includes_functions_6_and_7(self):
        from types import SimpleNamespace
        from .seo import _ruler_names
        people = [SimpleNamespace(idfk_PersonFunktion_id=fn, idfk_Person=SimpleNamespace(name=name, pk=fn))
                  for fn, name in ((1, 'A'), (6, 'B'), (7, 'C'), (2, 'D'))]
        self.assertEqual(len(_ruler_names(people)), 3)

    def test_ttl_uses_object_uri_and_404s(self):
        self.assertEqual(self.client.get('/id/999999.ttl').status_code, 404)
        body = self.client.get(f'/id/{self.obj.pk}.ttl').content.decode()
        self.assertNotIn('127.0.0.1:8000/slg/150', body)
        self.assertIn(f'/objekt/{self.obj.pk}', body)

    def test_adjacent_invnrs_without_loading_collection(self):
        response = self.client.get(reverse('adjacent_invnrs'), {'invnr': 'E2', 'slg_id': self.slg.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data['prev1'], data['current'], data['next1']), ('E1', 'E2', 'E3'))
        self.assertEqual(data['next1_id'], self.third.pk)
        self.assertIsNone(data['prev2'])


class TemplateAndSettingsTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.obj = Obj.objects.create(invnr='D1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)

    def div_depth(self, client):
        html = client.get(f'/objekt/{self.obj.pk}/').content.decode()
        depth = 0
        for tag in re.findall(r'<div\b|</div>', html):
            depth += -1 if tag == '</div>' else 1
            self.assertGreaterEqual(depth, 0)
        return depth

    def test_detail_page_divs_balanced_for_all_visitors(self):
        self.assertEqual(self.div_depth(Client()), 0)
        staff = Client()
        staff.force_login(User.objects.create_superuser('s', 's@example.test', 'pw'))
        self.assertEqual(self.div_depth(staff), 0)

    def test_cors_middleware_runs_early(self):
        self.assertLess(settings.MIDDLEWARE.index('corsheaders.middleware.CorsMiddleware'),
                        settings.MIDDLEWARE.index('django.middleware.common.CommonMiddleware'))
