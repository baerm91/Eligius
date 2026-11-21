"""robots.txt, Sitemap-Index/Teil-Sitemaps und Canonical-URLs."""
from xml.etree import ElementTree as ET

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from .models import Herstellung, Muenztyp, Obj, Objekttyp, Paket, Slg, Workflow
from .seo import canonical_url
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
                 'templates/slg/Objektliste_mtoa.html'), encoding='utf-8').read().split('{% block meta_tags %}')[1].split('{% endblock meta_tags %}')[0])
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
