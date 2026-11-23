"""Real-browser regression tests, run explicitly in the browser-smoke CI job."""
import base64
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from playwright.sync_api import expect, sync_playwright

from slg.models import Mzstaette, Mztyp_Person, Nominal, Obj, Person, RvBildtyp
from slg.test_bugfix_regressions import Fixtures

# Browser-only response for fixture image URLs. The application still serves real data.
IMAGE = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMBAuUAAAAASUVORK5CYII='
)


class BrowserSmokeTests(Fixtures, StaticLiveServerTestCase):
    def setUp(self):
        cache.clear()
        self.base_data()
        self.staff = User.objects.create_superuser('browser-editor')
        mint = Mzstaette.objects.create(name='Rom', name_en='Rome', lat=41.9, long=12.49)
        self.typ.Mzstaette = mint
        self.typ.Nominal = Nominal.objects.create(name='Denar')
        self.typ.rv_bildtyp = RvBildtyp.objects.create(name='Victoria mit Palmzweig')
        self.typ.dat_von, self.typ.dat_bis = 150, 160
        self.typ.save()
        ruler = Person.objects.create(name='Marcus Aurelius')
        Mztyp_Person.objects.create(Mztyp=self.typ, idfk_Person=ruler,
                                    idfk_PersonFunktion=self.ruler_fn, appears_on_rev=False)
        for index in range(34):
            obj = Obj.objects.create(
                invnr=f'SMOKE-{index:02}', Slg=self.slg, Typ=self.typ, workflow=self.controlled,
                dat_von=150, dat_bis=160,
            )
            if index == 0:
                self.obj = obj
        self.client.force_login(self.staff)
        self.staff_session = self.client.cookies['sessionid'].value
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(channel=os.environ.get('ELIGIUS_SMOKE_BROWSER'),
                                             args=['--enable-unsafe-swiftshader'])
        self.addCleanup(browser.close)
        self.context = browser.new_context(viewport={'width': 1280, 'height': 900})
        self.addCleanup(self.context.close)
        self.context.add_cookies([{'name': 'django_language', 'value': 'de', 'url': self.live_server_url}])
        self.context.route('**/*', self.route)
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.addCleanup(self.save_artifacts)

    def route(self, route):
        url = route.request.url
        host = urlsplit(url).hostname
        if url.startswith(self.live_server_url + '/'):
            route.continue_()
        elif host == 'img.example.test':
            route.fulfill(content_type='image/png', body=IMAGE)
        elif host == 'tiles.openfreemap.org' and '/styles/' in url:
            route.fulfill(json={'version': 8, 'sources': {}, 'layers': []},
                          headers={'Access-Control-Allow-Origin': '*'})
        else:
            route.abort()

    def save_artifacts(self):
        folder = Path('browser-smoke-artifacts')
        folder.mkdir(exist_ok=True)
        name = self._testMethodName
        if not self.page.is_closed():
            self.page.screenshot(path=folder / f'{name}.png', timeout=5000)
        self.context.tracing.stop(path=folder / f'{name}.zip')

    def open_page(self, route):
        response = self.page.goto(self.live_server_url + route, wait_until='domcontentloaded')
        self.assertEqual(response.status, 200)
        if self.page.locator('.cc-deny').count():
            self.page.locator('.cc-deny').click()

    def detail_url(self):
        return f'/objekt/{self.obj.pk}/'

    def test_home_loads_collection_cards(self):
        self.open_page('/')
        expect(self.page.locator('#collectionsGrid .prem-collection-card').first).to_contain_text(self.slg.name)
        self.assertFalse(self.errors, self.errors)

    def test_language_switch_keeps_browse_filter(self):
        self.open_page('/browse/?Muenzstaette=Rom')
        self.page.get_by_role('button', name='English').click()
        expect(self.page.locator('html')).to_have_attribute('lang', 'en')
        self.assertIn('Muenzstaette=Rom', self.page.url)
        expect(self.page.locator('.browse-count')).to_contain_text('34')

    def test_open_filter_and_select2_with_keyboard(self):
        self.open_page('/browse/')
        toggle = self.page.locator('[data-bs-target="#offcanvasFilter"]')
        toggle.focus()
        self.page.keyboard.press('Enter')
        panel = self.page.locator('#offcanvasFilter')
        expect(panel).to_be_focused()
        facet_toggle = panel.locator('[data-bs-target="#muenzstaettenCollapse"]')
        facet_toggle.focus()
        self.page.keyboard.press('Enter')
        entry = panel.locator('#muenzstaettenCollapse .select2-search__field')
        expect(entry).to_be_visible()
        entry.focus()
        self.page.keyboard.type('Rom')
        expect(panel.get_by_role('treeitem', name=re.compile(r'^Rom \('))).to_be_visible(timeout=10000)
        expect(panel.locator('.select2-results__option--highlighted')).to_contain_text('Rom')
        self.page.keyboard.press('Enter')
        expect(self.page).to_have_url(re.compile(r'Muenzstaette=Rom'))
        expect(panel.locator('.select2-selection__choice')).to_contain_text('Rom')
        expect(entry).to_be_focused()
        dropdown = panel.locator('.select2-container--open')
        if dropdown.count():
            self.page.keyboard.press('Escape')
            expect(dropdown).to_have_count(0)
            expect(panel).to_be_visible()
        self.page.keyboard.press('Escape')
        expect(panel).to_be_hidden()
        expect(toggle).to_be_focused()

    def test_map_fullscreen_restores_focus_and_chart_table_loads(self):
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.open_page('/browse/')
        expect(self.page.locator('#mintMap .leaflet-control-zoom-in')).to_be_visible()
        expect(self.page.get_by_role('slider', name='Frühestes Prägejahr')).to_be_visible()
        expect(self.page.get_by_role('slider', name='Spätestes Prägejahr')).to_be_visible()
        show = self.page.locator('#customFullscreenBtn')
        show.focus()
        self.page.keyboard.press('Enter')
        expect(self.page.locator('#exitFullscreenBtn')).to_be_focused()
        self.page.keyboard.press('Escape')
        expect(show).to_be_focused()
        expect(show).to_have_attribute('aria-expanded', 'false')
        expect(self.page.locator('#objectsBarChart canvas').first).to_be_visible()
        details = self.page.locator('#browse-chart-data')
        details.locator('summary').focus()
        self.page.keyboard.press('Enter')
        expect(details.get_by_role('columnheader', name='Gewichtete Stückzahl')).to_be_visible()
        data_row = details.locator('tbody tr').first
        expect(data_row).to_be_visible()
        data_row.scroll_into_view_if_needed()

    def test_browse_loads_second_page(self):
        self.open_page('/browse/')
        expect(self.page.locator('.infinite-item')).to_have_count(30)
        self.page.locator('#load-more').scroll_into_view_if_needed()
        expect(self.page.locator('.infinite-item')).to_have_count(34)
        expect(self.page.locator('#load-more')).to_have_count(0)

    def test_object_feedback_modal_restores_focus(self):
        self.open_page(self.detail_url())
        trigger = self.page.locator('[data-bs-target="#editModal"]')
        trigger.focus()
        self.page.keyboard.press('Enter')
        modal = self.page.locator('#editModal')
        expect(modal.locator('#name')).to_be_focused()
        self.page.keyboard.press('Escape')
        expect(modal).to_be_hidden()
        expect(trigger).to_be_focused()

    def test_gallery_opens_and_closes_with_keyboard(self):
        self.open_page(self.detail_url())
        trigger = self.page.locator('#captions .item').first
        trigger.focus()
        self.page.keyboard.press('Enter')
        dialog = self.page.locator('.lg-outer[role="dialog"]')
        expect(dialog).to_be_visible()
        close = dialog.locator('.lg-close')
        expect(close).to_be_focused()
        expect(dialog.get_by_role('img', name=re.compile(r'^Avers:'))).to_have_count(1)
        expect(dialog.get_by_role('link', name='Bild herunterladen')).to_be_visible()
        self.page.keyboard.press('Enter')
        expect(dialog).to_have_count(0)
        expect(trigger).to_be_focused()

    def test_staff_motif_statistics_load(self):
        self.context.add_cookies([
            {'name': 'sessionid', 'value': self.staff_session, 'url': self.live_server_url}
        ])
        self.open_page(self.detail_url())
        expect(self.page.locator('#contextAnalysisTitle')).to_contain_text('Marcus Aurelius')
        self.page.locator('#matrixViewBtn').click()
        expect(self.page.locator('#matrixContainer')).to_contain_text('Denar')
        expect(self.page.locator('#matrixContainer svg').first).to_be_visible()
        self.assertFalse(self.errors, self.errors)
