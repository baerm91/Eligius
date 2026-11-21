"""Technische SEO-Basics: Sitemaps, robots.txt und Canonical-URLs.

Alle absoluten URLs werden aus ``settings.ELIGIUS_PUBLIC_BASE_URL`` gebaut
(Produktion: https://eligius.donau-uni.ac.at). Ist die Basis leer (lokal),
wird auf Schema und Host des Requests zurückgegriffen. Der ``Site``-Eintrag
aus ``django.contrib.sites`` wird bewusst NICHT verwendet, weil dessen
Domain in der Datenbank nicht zuverlässig gepflegt ist.
"""
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps import views as sitemap_views
from django.db.models import Exists, OuterRef
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import Resolver404, resolve, reverse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from .models import Muenztyp, Obj, Paket, Slg

KONTROLLIERT = 'kontrolliert'


# ---------------------------------------------------------------------------
# Basis-URL

def public_base_url(request=None):
    """Öffentliche Basis ohne abschließenden Slash, z. B. ``https://host``."""
    base = (getattr(settings, 'ELIGIUS_PUBLIC_BASE_URL', '') or '').rstrip('/')
    if base:
        return base
    if request is not None:
        return f'{request.scheme}://{request.get_host()}'
    return ''


def canonical_path(path):
    """Normalisiert einen Request-Pfad für ``rel=canonical``.

    ``slg.urls`` ist zusätzlich unter ``/api/`` eingebunden, wodurch jede
    öffentliche Seite (z. B. ``/api/pakete/<slug>/``) doppelt erreichbar ist.
    Liefert der Pfad ohne ``/api``-Präfix dieselbe View, ist das die kanonische
    Variante.
    """
    if path.startswith('/api/'):
        stripped = path[len('/api'):]
        try:
            original, plain = resolve(path), resolve(stripped)
        except Resolver404:
            return path
        if plain.func == original.func or (plain.url_name and plain.url_name == original.url_name):
            return stripped
    return path


def canonical_url(request):
    """Absolute kanonische URL der aktuellen Seite – ohne Query-Parameter."""
    return public_base_url(request) + canonical_path(request.path)


# ---------------------------------------------------------------------------
# Sitemaps

class EligiusSitemap(Sitemap):
    """Erzwingt Domain/Protokoll aus der öffentlichen Basis-URL statt aus ``Site``."""

    limit = 10000

    def __init__(self, base_url=''):
        self.base_url = (base_url or public_base_url()).rstrip('/')

    def get_protocol(self, protocol=None):
        if self.base_url:
            return urlsplit(self.base_url).scheme or 'https'
        return super().get_protocol(protocol)

    def get_domain(self, site=None):
        if self.base_url:
            parts = urlsplit(self.base_url)
            return parts.netloc + parts.path
        return super().get_domain(site)


class StaticViewSitemap(EligiusSitemap):
    changefreq = 'weekly'

    PAGES = {
        'index_slg': 1.0,
        'sammlungen_uebersicht': 0.9,
        'Objektliste': 0.8,
        'neuerschliessungen': 0.8,
        'timeline_view': 0.5,
        'about': 0.4,
        'lab': 0.4,
        'impressum': 0.1,
        'datenschutz': 0.1,
    }

    def items(self):
        return list(self.PAGES)

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return self.PAGES[item]


class SammlungSitemap(EligiusSitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Slg.objects.only('id').order_by('id')


class PaketSitemap(EligiusSitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return (
            Paket.objects
            .filter(online_freigegeben=True)
            .exclude(slug__isnull=True).exclude(slug='')
            .only('id', 'slug')
            .order_by('id')
        )

    def location(self, item):
        return reverse('paket_detail', kwargs={'slug': item.slug})


class MuenztypSitemap(EligiusSitemap):
    """Münztypen mit mindestens einem zugeordneten Objekt (keine leeren Typseiten)."""

    changefreq = 'monthly'
    priority = 0.7

    def items(self):
        return (
            Muenztyp.objects
            .filter(Exists(Obj.objects.filter(Typ=OuterRef('pk'))))
            .only('id', 'modified_at')
            .order_by('id')
        )

    def lastmod(self, item):
        return item.modified_at


class ObjektSitemap(EligiusSitemap):
    """Nur Objekte mit Workflow-Status „kontrolliert“."""

    changefreq = 'monthly'
    priority = 0.6

    def items(self):
        return (
            Obj.objects
            .filter(workflow__name__iexact=KONTROLLIERT)
            .only('id', 'modified_at')
            .order_by('id')
        )

    def lastmod(self, item):
        return item.modified_at


SITEMAPS = {
    'static': StaticViewSitemap,
    'sammlungen': SammlungSitemap,
    'pakete': PaketSitemap,
    'typen': MuenztypSitemap,
    'objekte': ObjektSitemap,
}

SITEMAP_CACHE_SECONDS = 60 * 60


@require_GET
@cache_page(SITEMAP_CACHE_SECONDS)
def sitemap_index(request):
    """Sitemap-Index unter /sitemap.xml.

    Eigene Variante von ``django.contrib.sitemaps.views.index``, weil die
    Django-Version die Domain aus dem ``Site``-Modell liest.
    """
    base = public_base_url(request)
    entries = []
    for section, sitemap_cls in SITEMAPS.items():
        sitemap = sitemap_cls(base)
        url = base + reverse('sitemap_section', kwargs={'section': section})
        num_pages = sitemap.paginator.num_pages
        if num_pages == 0:
            continue
        entries.append({'location': url, 'last_mod': None})
        for page in range(2, num_pages + 1):
            entries.append({'location': f'{url}?p={page}', 'last_mod': None})
    return TemplateResponse(
        request,
        'sitemap_index.xml',
        {'sitemaps': entries},
        content_type='application/xml',
    )


@require_GET
@cache_page(SITEMAP_CACHE_SECONDS)
def sitemap_section(request, section):
    base = public_base_url(request)
    sitemaps = {name: cls(base) for name, cls in SITEMAPS.items()}
    return sitemap_views.sitemap(request, sitemaps=sitemaps, section=section)


# ---------------------------------------------------------------------------
# robots.txt

ROBOTS_DISALLOW = [
    # Verwaltung / Bearbeitung
    '/admin/',
    '/adminactions/',
    '/create/',
    '/id/*/update/',
    '/id/*/edit/',
    '/objekt/*/aenderung/',
    # APIs, AJAX, Exporte, Fragmente
    '/api/',
    '/api-token-auth/',
    '/ajax/',
    '/select2/',
    '/export_xlsx/',
    '/export-obj-lsno/',
    '/export_coins/',
    '/export_coin_states/',
    '/objekt_detail_partial/',
    '/konkordanzen_bulk/',
    '/muenztyp/',
    '/muenztyp_from_concordia/',
    '/muenztyp_filter/',
    '/objekt/$',
    '/objekte/bulk/',
    '/slgteil/',
    '/avbildtyp/',
    '/rvbildtyp/',
    '/mzstaette/',
    '/nominal/',
    '/person/$',
    '/herstellungsmerkmale/',
    '/sek_merkmale/',
    '/muenzstand/',
    '/avbeizeichen/',
    '/avoffizin/',
    '/rvbeizeichen/',
    '/rvoffizin/',
    '/workflow/',
    '/ref/',
    '/person_coin_images/',
    '/avschlagwort/',
    '/avbildtyp-schlagwort/',
    '/*/modal/',
    '/i18n/',
    # Interne Werkzeuge
    '/tools/',
    '/catalog/',
    '/health',
    '/mcp',
    # Filterkombinationen der Objektliste (mehrere Parameter) schonen das Crawl-Budget;
    # einfache Einstiege wie /browse/ oder /browse/?page=2 bleiben erreichbar.
    '/browse/*&',
]


@require_GET
def robots_txt(request):
    lines = ['User-agent: *']
    lines += [f'Disallow: {path}' for path in ROBOTS_DISALLOW]
    lines += ['', f'Sitemap: {public_base_url(request)}{reverse("sitemap_index")}', '']
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')
