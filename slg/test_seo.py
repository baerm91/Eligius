"""robots.txt, Sitemaps, Canonical-URLs, Titel und Social-Preview-Tags."""
import re
from xml.etree import ElementTree as ET

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from .models import (Herstellung, Metall, Muenztyp, Mztyp_Person, Mzstaette, Nominal, Obj, Objekttyp, Paket,
                     Person, PersonFunktion, Slg, Workflow)
from .seo import canonical_url, clean_text, muenztyp_meta
from .signals import disable_mtoa_sync, enable_mtoa_sync

BASE = 'https://example.test'
SM = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


class SeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        disable_mtoa_sync()
        try:
            cls.controlled = Workflow.objects.create(name='kontrolliert', reihenfolge=1)
            cls.draft = Workflow.objects.create(name='Entwurf', reihenfolge=2)
            Herstellung.objects.create(id=1, name='Geprägt')
            Objekttyp.objects.create(id=1, name='Münze')
            cls.slg = Slg.objects.create(name='Testsammlung')
            cls.typ = Muenztyp.objects.create(muenztyptitel='T1', titel='Typ mit Objekt', workflow=cls.controlled)
            cls.empty_typ = Muenztyp.objects.create(muenztyptitel='T2', titel='Leerer Typ', workflow=cls.controlled)
            cls.ok = Obj.objects.create(invnr='A1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
            cls.open = Obj.objects.create(invnr='A2', Slg=cls.slg, Typ=cls.typ, workflow=cls.draft)
            cls.paket = Paket.objects.create(name='Öffentliches Paket', online_freigegeben=True)
            cls.intern = Paket.objects.create(name='Internes Paket', online_freigegeben=False)
        finally:
            enable_mtoa_sync()

    def setUp(self):
        cache.clear()

    def locs(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return [el.text for el in ET.fromstring(response.content).iter(f'{SM}loc')]

    def test_robots_txt(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        body = response.content.decode()
        self.assertIn(f'Sitemap: {BASE}/sitemap.xml', body)
        for path in ('/admin/', '/api/', '/ajax/', '/export_xlsx/', '/objekt_detail_partial/', '/select2/', '/browse/*&'):
            self.assertIn(f'Disallow: {path}\n', body)
        self.assertNotIn('Disallow: /objekt/\n', body)
        self.assertNotIn('Disallow: /typ/', body)

    def test_sitemap_index_lists_sections(self):
        locs = self.locs('/sitemap.xml')
        for section in ('static', 'sammlungen', 'pakete', 'typen', 'objekte'):
            self.assertIn(f'{BASE}/sitemap-{section}.xml', locs)

    def test_section_contents(self):
        self.assertIn(f'{BASE}/', self.locs('/sitemap-static.xml'))
        self.assertIn(f'{BASE}/about/', self.locs('/sitemap-static.xml'))
        self.assertEqual(self.locs('/sitemap-sammlungen.xml'), [f'{BASE}/slg/{self.slg.id}/'])
        self.assertEqual(self.locs('/sitemap-pakete.xml'), [f'{BASE}/pakete/{self.paket.slug}/'])
        self.assertEqual(self.locs('/sitemap-typen.xml'), [f'{BASE}/typ/{self.typ.id}/'])
        self.assertEqual(self.locs('/sitemap-objekte.xml'), [f'{BASE}/objekt/{self.ok.id}/'])

    def test_reverse_uses_public_paths(self):
        from django.urls import reverse
        self.assertEqual(reverse('index_slg'), '/')
        self.assertEqual(reverse('paket_detail', kwargs={'slug': 'x'}), '/pakete/x/')
        self.assertEqual(reverse('slg_api:paket_detail', kwargs={'slug': 'x'}), '/api/pakete/x/')

    def test_browse_template_noindex_only_with_parameters(self):
        from django.template.loader import render_to_string
        from django.template import engines
        tpl = engines['django'].from_string(
            open(__import__('os').path.join(__import__('os').path.dirname(__file__),
                 'templates/slg/Objektliste_mtoa.html'), encoding='utf-8').read().replace('\r\n', '\n').split('{% block meta_tags %}')[1].split('{% endblock meta_tags %}')[0].join(['{% load i18n seo_tags %}', '']))
        rf = RequestFactory()
        self.assertNotIn('noindex', tpl.render({'request': rf.get('/browse/')}))
        self.assertIn('noindex, follow', tpl.render({'request': rf.get('/browse/?page=2')}))

    def test_unknown_section_404(self):
        self.assertEqual(self.client.get('/sitemap-gibtsnicht.xml').status_code, 404)

    @override_settings(ELIGIUS_PUBLIC_BASE_URL='')
    def test_request_host_fallback(self):
        self.assertIn('http://testserver/sitemap-objekte.xml', self.locs('/sitemap.xml'))
        self.assertEqual(self.locs('/sitemap-objekte.xml'), [f'http://testserver/objekt/{self.ok.id}/'])

    def test_canonical_url_strips_query_and_api_prefix(self):
        rf = RequestFactory()
        self.assertEqual(canonical_url(rf.get('/browse/?page=2&slg=3')), f'{BASE}/browse/')
        self.assertEqual(canonical_url(rf.get('/api/about/')), f'{BASE}/about/')
        self.assertEqual(canonical_url(rf.get(f'/api/pakete/{self.paket.slug}/')), f'{BASE}/pakete/{self.paket.slug}/')
        self.assertEqual(canonical_url(rf.get('/api/stats/')), f'{BASE}/api/stats/')

    def test_canonical_tag_rendered(self):
        response = self.client.get('/impressum/?utm_source=x')
        self.assertContains(response, f'<link rel="canonical" href="{BASE}/impressum/">', html=False)


class SeoMetaTests(TestCase):
    """Titel, Meta-Descriptions und Social-Preview-Tags."""

    @classmethod
    def setUpTestData(cls):
        disable_mtoa_sync()
        try:
            cls.controlled = Workflow.objects.create(name='kontrolliert', reihenfolge=1)
            Herstellung.objects.create(id=1, name='Geprägt')
            Objekttyp.objects.create(id=1, name='Münze')
            ruler_role = PersonFunktion.objects.create(id=1, name='Prägeherr')
            depicted = PersonFunktion.objects.create(id=2, name='Dargestellte Person')
            cls.slg = Slg.objects.create(name='Stift Heiligenkreuz', beschreibung='')
            cls.typ = Muenztyp.objects.create(
                muenztyptitel='RIC II.1 Domitian 101', titel='Domitianus', workflow=cls.controlled,
                Nominal=Nominal.objects.create(name='Denar'), Metall=Metall.objects.create(name='Silber'),
                Mzstaette=Mzstaette.objects.create(name='Rom'), dat_verb='82 n. Chr.',
                avleg='IMP CAES DOMITIANVS AVG P M', rvleg='TR POT COS VIII P P')
            other = Muenztyp.objects.create(muenztyptitel='BMC 12', titel='Domitianus', workflow=cls.controlled)
            cls.typ.Konkordanz.add(other)
            Mztyp_Person.objects.create(Mztyp=cls.typ, idfk_Person=Person.objects.create(name='Domitianus'),
                                        idfk_PersonFunktion=ruler_role, appears_on_rev=False)
            Mztyp_Person.objects.create(Mztyp=cls.typ, idfk_Person=Person.objects.create(name='Minerva'),
                                        idfk_PersonFunktion=depicted, appears_on_rev=True)
            Obj.objects.create(invnr='H1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
            cls.paket = Paket.objects.create(name='Fund Carnuntum', online_freigegeben=True,
                                             beschreibung='<p>Ein Schatzfund &amp; seine Münzen.</p>')
        finally:
            enable_mtoa_sync()

    def setUp(self):
        cache.clear()

    def meta(self, response, attr, key):
        match = re.search(rf'<meta {attr}="{re.escape(key)}" content="([^"]*)"', response.content.decode())
        return match.group(1) if match else None

    def test_muenztyp_meta_uses_search_terms(self):
        meta = muenztyp_meta(self.typ, self.typ.mztyp_person_set.select_related('idfk_Person'), 1)
        self.assertEqual(meta['title'], 'Domitianus, Denar, Rom – RIC II.1 Domitian 101')
        self.assertTrue(meta['description'].startswith(
            'Münztyp RIC II.1 Domitian 101, Domitianus, Denar (Silber), Münzstätte Rom, 82 n. Chr., '
            'Konkordanz: BMC 12.'), meta['description'])
        self.assertIn('1 Objekt im digitalen Münzkabinett Eligius.', meta['description'])
        self.assertNotIn('Minerva', meta['title'])
        self.assertLessEqual(len(meta['description']), 160)

    def test_muenztyp_meta_without_data(self):
        typ = Muenztyp.objects.create(muenztyptitel='unbestimmt', workflow=self.controlled)
        self.assertEqual(muenztyp_meta(typ)['title'], f'Münztyp {typ.id}')

    def test_clean_text(self):
        self.assertEqual(clean_text('<p>A &amp; B\n  C</p>'), 'A & B C')
        self.assertEqual(clean_text('wort ' * 50, limit=20), 'wort wort wort…')

    def test_typ_page(self):
        response = self.client.get(f'/typ/{self.typ.id}/')
        self.assertContains(response, '<title>Domitianus, Denar, Rom – RIC II.1 Domitian 101 | Eligius</title>')
        self.assertEqual(self.meta(response, 'property', 'og:title'), 'Domitianus, Denar, Rom – RIC II.1 Domitian 101')
        self.assertEqual(self.meta(response, 'property', 'og:type'), 'article')
        self.assertEqual(self.meta(response, 'property', 'og:url'), f'{BASE}/typ/{self.typ.id}/')
        self.assertEqual(self.meta(response, 'name', 'twitter:card'), 'summary')
        self.assertEqual(response.content.decode().count('name="description"'), 1)

    def test_typ_page_english(self):
        response = self.client.get(f'/typ/{self.typ.id}/', HTTP_ACCEPT_LANGUAGE='en')
        description = self.meta(response, 'name', 'description')
        self.assertTrue(description.startswith('Coin type RIC II.1 Domitian 101'), description)
        self.assertIn('Mint Rom', description)
        self.assertEqual(self.meta(response, 'property', 'og:locale'), 'en_GB')

    def test_sammlung_page(self):
        response = self.client.get(f'/slg/{self.slg.id}/')
        self.assertContains(response, '<title>Stift Heiligenkreuz – Münzsammlung | Eligius</title>')
        self.assertEqual(self.meta(response, 'name', 'description'),
                         '1 Münze und numismatisches Objekt der Sammlung „Stift Heiligenkreuz“ – '
                         'digital erschlossen und frei recherchierbar in Eligius.')
        Slg.objects.filter(pk=self.slg.pk).update(beschreibung='<b>Älteste</b> Sammlung', cover='/media/cover.jpg')
        response = self.client.get(f'/slg/{self.slg.id}/')
        self.assertEqual(self.meta(response, 'name', 'description'), 'Älteste Sammlung')
        self.assertEqual(self.meta(response, 'property', 'og:image'), f'{BASE}/media/cover.jpg')
        self.assertEqual(self.meta(response, 'name', 'twitter:card'), 'summary_large_image')

    def test_paket_page(self):
        response = self.client.get(f'/pakete/{self.paket.slug}/')
        self.assertContains(response, '<title>Fund Carnuntum | Eligius</title>')
        self.assertEqual(self.meta(response, 'name', 'description'), 'Ein Schatzfund &amp; seine Münzen.')
        self.assertEqual(self.meta(response, 'property', 'og:title'), 'Fund Carnuntum')

    def test_static_pages(self):
        response = self.client.get('/about/')
        self.assertContains(response, '<title>Über das Projekt | Eligius</title>')
        self.assertIn('Klöster', self.meta(response, 'name', 'description'))
        self.assertTrue(self.meta(response, 'property', 'og:image').endswith('img/hero_coin.png'))
        self.assertEqual(self.meta(response, 'name', 'twitter:card'), 'summary')
        english = self.client.get('/about/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertContains(english, '<title>About the project | Eligius</title>')
        response = self.client.get('/sammlungen/')
        self.assertContains(response, '<title>Numismatische Sammlungen | Eligius</title>')
        self.assertIn('Münzsammlungen', self.meta(response, 'name', 'description'))
        response = self.client.get('/impressum/')
        self.assertIn('digitale Münzkabinett', self.meta(response, 'name', 'description'))
