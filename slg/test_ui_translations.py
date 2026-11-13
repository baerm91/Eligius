from html.parser import HTMLParser
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import path, reverse
from django.utils.translation import gettext
from django.views.decorators.cache import cache_page

from slg.services import ui_translations


@cache_page(60)
def cached_page(request):
    return HttpResponse(gettext('Sammlungen'))


urlpatterns = [path('cached/', cached_page)]


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.hrefs.append(dict(attrs).get('href'))


class UILanguageTests(SimpleTestCase):
    def test_browser_language_cookie_and_default(self):
        response = self.client.get('/about/')
        self.assertContains(response, '<html lang="de">')
        self.assertContains(response, '>Sammlungen</a>')
        english = self.client.get('/about/', HTTP_ACCEPT_LANGUAGE='en-GB,en;q=0.9')
        self.assertContains(english, '<html lang="en">')
        self.assertContains(english, '>Collections</a>')
        self.assertContains(english, '>Privacy policy</a>')
        self.assertEqual(english.headers['Content-Language'], 'en')
        self.assertIn('Accept-Language', english.headers['Vary'])
        self.assertEqual(Links(response.content.decode()).hrefs, Links(english.content.decode()).hrefs)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'de'
        self.assertContains(self.client.get('/about/', HTTP_ACCEPT_LANGUAGE='en'), '<html lang="de">')

    def test_switch_keeps_path_filters_and_next_page_preference(self):
        target = '/browse/?Slg=2&q=Marcus&page=3#results'
        response = self.client.post(reverse('set_language'), {'language': 'en', 'next': target})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], target)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'en')
        self.assertContains(self.client.get('/about/'), '>Collections</a>')
        self.client.post(reverse('set_language'), {'language': 'de', 'next': '/about/'})
        self.assertContains(self.client.get('/about/'), '>Sammlungen</a>')

    def test_switch_form_preserves_query(self):
        response = self.client.get('/about/?q=a%26b&page=2')
        self.assertContains(response, 'value="/about/?q=a%26b&amp;page=2"')

    def test_switch_does_not_reverse_duplicate_routes(self):
        for target in ('/', '/api/', '/objekt/42/', '/id/42.ttl', '/slg/2/nomisma.rdf'):
            response = self.client.post(reverse('set_language'), {'language': 'en', 'next': target})
            self.assertEqual(response['Location'], target)

    def test_switch_is_csrf_protected_and_redirect_is_local(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('set_language'), {'language': 'en'}).status_code, 403)
        response = self.client.post(reverse('set_language'), {'language': 'en', 'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], '/')
        response = self.client.post(reverse('set_language'), {'language': 'fr', 'next': '/'})
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, response.cookies)

    @override_settings(ROOT_URLCONF=__name__)
    def test_cached_pages_are_separated_by_language(self):
        cache.clear()
        for language, expected in [('en', b'Collections'), ('de', b'Sammlungen'), ('en', b'Collections')]:
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            self.assertEqual(self.client.get('/cached/').content, expected)
        cache.clear()


class UITranslationDraftTests(SimpleTestCase):
    def test_draft_never_modifies_catalogue(self):
        before = ui_translations.CATALOG.read_bytes()
        draft = ui_translations.draft_ui_translations(None, {'Sammlungen': 'Museum collections'})
        self.assertFalse(draft['persisted'])
        self.assertEqual(draft['changes'][0]['before'], 'Collections')
        self.assertIn('msgstr "Museum collections"', draft['po_entries'])
        self.assertEqual(ui_translations.CATALOG.read_bytes(), before)

    def test_draft_rejects_unknown_sources_and_markup(self):
        for changes in ({}, {'unknown': 'Test'}, {'Sammlungen': '<script>'}, {'Sammlungen': ''}):
            with self.assertRaises(ValueError):
                ui_translations.draft_ui_translations(None, changes)

    def test_translation_drafts_preserve_named_placeholders(self):
        source = 'Vergleich der Prägungen von %(ruler)s'
        draft = ui_translations.draft_ui_translations(None, {source: 'Coin comparison: %(ruler)s'})
        self.assertFalse(draft['persisted'])
        for target in ('Coin comparison', 'Coins: %(other)s', 'Coins: %(ruler)s %(ruler)s'):
            with self.assertRaises(ValueError):
                ui_translations.draft_ui_translations(None, {source: target})

    async def test_mcp_drafts_use_authenticated_editor_boundary(self):
        from slg import editor_mcp
        with patch('slg.services.editor_api.editor_user', side_effect=ValueError('Authentication required')):
            with self.assertRaises(ValueError):
                await editor_mcp.get_ui_translation_catalog()
            with self.assertRaises(ValueError):
                await editor_mcp.draft_ui_translations({'Sammlungen': 'Collections'})


class PublicTemplateLanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from slg.models import Slg, Obj, Muenztyp, Mzstaette, Nominal, MuenztypObjektAnzeige
        from slg.signals import disable_mtoa_sync, enable_mtoa_sync
        disable_mtoa_sync()
        try:
            cls.collection = Slg.objects.create(name='Sammlung mit langem deutschen Namen')
            mint = Mzstaette.objects.create(name='Wien')
            nominal = Nominal.objects.create(name='Pfennig')
            cls.coin_type = Muenztyp.objects.create(
                muenztyptitel='Unveränderte Typbeschreibung', titel='Deutscher Titel',
                Mzstaette=mint, Nominal=nominal, Objekttyp=None, Herstellung=None, workflow=None)
            cls.obj = Obj.objects.create(invnr='I18N-001', titel='Deutscher Titel',
                Slg=cls.collection, Typ=cls.coin_type, Objekttyp=None, workflow=None)
            MuenztypObjektAnzeige.objects.create(obj_id=cls.obj.pk, invnr=cls.obj.invnr,
                objekttitel='Deutscher Titel', Slg=cls.collection.name, slg_fk=cls.collection,
                typ_fk=cls.coin_type, nominal='Pfennig', nominal_fk=nominal,
                mzstaette='Wien', mzstaette_fk=mint)
        finally:
            enable_mtoa_sync()

    def test_browse_translates_labels_but_preserves_values_and_filter_contract(self):
        responses = {}
        for language in ('de', 'en'):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            responses[language] = self.client.get('/browse/', {'Nominal': 'Pfennig'})
            self.assertContains(responses[language], 'Pfennig')
            self.assertContains(responses[language], 'Deutscher Titel')
            self.assertContains(responses[language], 'name="Muenzstaette"')
            self.assertContains(responses[language], 'name="Nominal"')
        self.assertContains(responses['en'], 'Search category')
        self.assertContains(responses['en'], 'Manufacturing features')
        self.assertContains(responses['en'], 'Denomination:')
        self.assertContains(responses['de'], 'Suchkategorie')
        self.assertEqual(Links(responses['de'].content.decode()).hrefs,
                         Links(responses['en'].content.decode()).hrefs)

    def test_object_type_and_home_render_in_both_languages(self):
        for language in ('de', 'en'):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            for url in ('/', f'/objekt/{self.obj.pk}/', f'/typ/{self.coin_type.pk}/', '/sammlungen/'):
                with self.subTest(language=language, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, f'<html lang="{language}">')

    def test_javascript_catalogue_and_facet_data_are_language_safe(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'en'
        script = self.client.get(reverse('ui_javascript_catalog'))
        self.assertContains(script, 'Search mints')
        self.assertContains(script, '%(current)s of %(total)s')
        self.assertContains(script, 'Overall: %(start)s to %(end)s')
        self.assertContains(script, 'Rank %(rank)s (%(percentage)s of all coins issued by %(ruler)s)')
        self.assertEqual(script.headers['Content-Language'], 'en')
        response = self.client.get('/api/facet/', {'facet': 'Nominal'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Pfennig', response.content.decode())
        self.assertNotIn('Penny', response.content.decode())
