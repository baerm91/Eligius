"""robots.txt, Sitemaps, Canonical-URLs, Titel, Social-Preview-Tags und JSON-LD."""
import json
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


@override_settings(ELIGIUS_SEO_INDEXING=True)
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
        self.assertNotIn('X-Robots-Tag', response)
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

    def test_disabled_indexing_rejects_cached_sitemaps(self):
        sitemap_urls = ('/sitemap.xml', '/sitemap-objekte.xml')
        for url in sitemap_urls:
            self.locs(url)

        with override_settings(ELIGIUS_SEO_INDEXING=False):
            self.assertEqual(self.client.get('/robots.txt').content, b'User-agent: *\nDisallow: /\n')
            for url in sitemap_urls:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')

    @override_settings(ELIGIUS_SEO_INDEXING=False)
    def test_disabled_indexing_marks_html_json_and_redirects(self):
        html = self.client.get('/impressum/')
        self.assertContains(html, '<meta name="robots" content="noindex, nofollow">')
        self.assertContains(html, f'<link rel="canonical" href="{BASE}/impressum/">')
        self.assertEqual(html['X-Robots-Tag'], 'noindex, nofollow')

        for url, status in (('/health', 200), ('/impressum', 301)):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')

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
        self.assertNotIn('X-Robots-Tag', response)
        self.assertNotContains(response, '<meta name="robots"')
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


class StructuredDataTests(TestCase):
    """schema.org/JSON-LD auf Start-, Objekt-, Sammlungs-, Typ- und Paketseiten."""

    @classmethod
    def setUpTestData(cls):
        disable_mtoa_sync()
        try:
            controlled = Workflow.objects.create(name='kontrolliert', reihenfolge=1)
            Herstellung.objects.create(id=1, name='Geprägt')
            Objekttyp.objects.create(id=1, name='Münze')
            ruler_role = PersonFunktion.objects.create(id=1, name='Prägeherr')
            depicted = PersonFunktion.objects.create(id=2, name='Dargestellte Person')
            cls.slg = Slg.objects.create(
                name='Stift Heiligenkreuz', beschreibung='Kurz.', bildrechte_lizenz='CC BY-NC 4.0',
                bildurl='https://images.example.test/', bild_endung_av='_a', bild_endung_rv='_r',
                nomisma_export_erlaubt=True, nomisma_collection_uri='http://nomisma.org/id/heiligenkreuz')
            cls.typ = Muenztyp.objects.create(
                muenztyptitel='RIC II.1 Domitian 101', titel='Domitianus', workflow=controlled,
                link='http://numismatics.org/ocre/id/ric.2_1(2).dom.101',
                Nominal=Nominal.objects.create(name='Denar', name_nom_id='denarius'),
                Metall=Metall.objects.create(name='Silber', name_nom_id='ar'),
                Mzstaette=Mzstaette.objects.create(name='Rom', name_nom_id='rome', geonames='3169070'),
                dat_verb='82 n. Chr.', avleg='IMP CAES DOMITIANVS AVG P M')
            Mztyp_Person.objects.create(
                Mztyp=cls.typ, idfk_PersonFunktion=ruler_role, appears_on_rev=False,
                idfk_Person=Person.objects.create(name='Domitianus', name_nom_id='domitian',
                                                  VIAF='https://viaf.org/viaf/12345'))
            Mztyp_Person.objects.create(Mztyp=cls.typ, idfk_Person=Person.objects.create(name='Minerva'),
                                        idfk_PersonFunktion=depicted, appears_on_rev=True)
            cls.obj = Obj.objects.create(invnr='H1', Slg=cls.slg, Typ=cls.typ, workflow=controlled,
                                         gewicht=3.2, durchmesser=19)
            cls.paket = Paket.objects.create(name='Fund Carnuntum', online_freigegeben=True)
        finally:
            enable_mtoa_sync()

    def setUp(self):
        cache.clear()

    def graph(self, url, **extra):
        response = self.client.get(url, **extra)
        self.assertEqual(response.status_code, 200, url)
        html = response.content.decode()
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        self.assertEqual(len(blocks), 1, url)
        data = json.loads(blocks[0])
        self.assertEqual(data['@context'], 'https://schema.org')
        return {(n['@type'] if isinstance(n['@type'], str) else n['@type'][0]): n for n in data['@graph']}, html

    def crumbs(self, nodes):
        return [(item['name'], item['item']) for item in nodes['BreadcrumbList']['itemListElement']]

    def test_home(self):
        nodes, _ = self.graph('/')
        self.assertEqual(nodes['WebSite']['potentialAction']['target']['urlTemplate'],
                         f'{BASE}/browse/?q={{search_term_string}}')
        self.assertEqual(nodes['WebSite']['publisher'], {'@id': f'{BASE}/#organization'})
        self.assertEqual(nodes['Organization']['parentOrganization']['name'], 'Universität für Weiterbildung Krems')

    def test_object(self):
        nodes, html = self.graph(f'/objekt/{self.obj.id}/')
        art = nodes['VisualArtwork']
        self.assertEqual(art['@id'], f'{BASE}/objekt/{self.obj.id}/#object')
        self.assertEqual(art['identifier']['value'], 'H1')
        self.assertEqual(art['artMedium'], 'Silber')
        self.assertEqual(art['temporalCoverage'], '82 n. Chr.')
        self.assertEqual(art['locationCreated']['sameAs'],
                         ['http://nomisma.org/id/rome', 'https://www.geonames.org/3169070'])
        self.assertEqual(art['creator'][0]['name'], 'Domitianus')
        self.assertEqual(art['creator'][0]['sameAs'], ['http://nomisma.org/id/domitian', 'https://viaf.org/viaf/12345'])
        self.assertEqual(art['about'][0]['name'], 'Minerva')
        self.assertEqual(art['exampleOfWork']['sameAs'], ['http://numismatics.org/ocre/id/ric.2_1(2).dom.101'])
        self.assertEqual(art['isPartOf']['@id'], f'{BASE}/slg/{self.slg.id}/#collection')
        self.assertEqual(art['isPartOf']['sameAs'], ['http://nomisma.org/id/heiligenkreuz'])
        nominal = next(p for p in art['additionalProperty'] if p['name'] == 'Nominal')
        self.assertEqual(nominal['valueReference']['sameAs'], ['http://nomisma.org/id/denarius'])
        weight = next(p for p in art['additionalProperty'] if p['name'] == 'Gewicht')
        self.assertEqual((weight['value'], weight['unitCode']), (3.2, 'GRM'))
        self.assertEqual(len(art['image']), 2)
        self.assertTrue(art['image'][0]['contentUrl'].startswith('https://images.example.test/'))
        self.assertEqual(art['image'][0]['license'], 'http://creativecommons.org/licenses/by-nc/4.0/')
        self.assertEqual(art['image'][0]['creditText'], 'Stift Heiligenkreuz')
        self.assertEqual(self.crumbs(nodes), [
            ('Startseite', f'{BASE}/'),
            ('Stift Heiligenkreuz', f'{BASE}/slg/{self.slg.id}/'),
            ('H1 – Domitianus', f'{BASE}/objekt/{self.obj.id}/'),
        ])
        # Breadcrumbs nur als Markup, nicht sichtbar.
        self.assertNotIn('breadcrumb', re.sub(r'<script type="application/ld\+json">.*?</script>', '', html, flags=re.S).lower())

    def test_object_english_labels(self):
        nodes, _ = self.graph(f'/objekt/{self.obj.id}/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(nodes['BreadcrumbList']['itemListElement'][0]['name'], 'Home')
        self.assertEqual(nodes['VisualArtwork']['image'][0]['name'], 'Obverse')

    def test_collection_dataset(self):
        nodes, _ = self.graph(f'/slg/{self.slg.id}/')
        dataset = nodes['Dataset']
        self.assertEqual(dataset['@type'], ['Dataset', 'Collection'])
        self.assertGreaterEqual(len(dataset['description']), 50)
        self.assertEqual(dataset['collectionSize'], 1)
        self.assertEqual(dataset['distribution'][0]['contentUrl'], f'{BASE}/slg/{self.slg.id}/nomisma.rdf')
        self.assertEqual(dataset['includedInDataCatalog']['name'], 'Eligius')
        self.assertEqual([name for name, _ in self.crumbs(nodes)], ['Startseite', 'Sammlungen', 'Stift Heiligenkreuz'])

    def test_type_and_package_breadcrumbs(self):
        nodes, _ = self.graph(f'/typ/{self.typ.id}/')
        self.assertEqual(self.crumbs(nodes)[-1],
                         ('Domitianus, Denar, Rom – RIC II.1 Domitian 101', f'{BASE}/typ/{self.typ.id}/'))
        nodes, _ = self.graph(f'/pakete/{self.paket.slug}/')
        self.assertEqual(self.crumbs(nodes)[-1], ('Fund Carnuntum', f'{BASE}/pakete/{self.paket.slug}/'))

    def test_script_breakout_is_escaped(self):
        Slg.objects.filter(pk=self.slg.pk).update(name='</script><script>alert(1)</script>')
        nodes, html = self.graph(f'/slg/{self.slg.id}/')
        self.assertNotIn('<script>alert(1)', html.split('application/ld+json">', 1)[1].split('</script>', 1)[0])
        self.assertEqual(nodes['Dataset']['name'], '</script><script>alert(1)</script>')
