"""Gemeinsamer Daten-Cache für teure Browse-Auswertungen.

Der Seitencache (cache_page + csrf_protect) variiert per Cookie und trifft
deshalb kaum. Hier werden nur besucherunabhängige Ergebnisse gecacht:
Trefferzahl, Kartenpunkte, Facetten und Zeitverteilung.

Bewusst eng gefasst:
- nur die ungefilterte Ansicht und Ansichten mit genau EINEM Filterwert,
- nie Freitext (q, Legenden, Inventarnummer, Autocomplete-Begriff),
- Schlüssel aus den tatsächlich gesetzten Parametern (+ Sprache, wenn das
  Ergebnis übersetzte Labels enthält) und einer Generation, die bei
  MTOA-Schreibvorgängen hochgezählt wird. Sonst gilt die TTL.
"""
import hashlib

from django.core.cache import cache
from django.utils.translation import get_language

from slg.filters import is_valid_qparam

TTL = 60 * 5
GENERATION_KEY = 'browse-data:generation'

# Freitext: zu viele Varianten, kaum Wiederholungen.
FREE_TEXT_PARAMS = frozenset({'q', 'avleg', 'rvleg', 'invnr', 'term', 'num'})
# Beeinflussen die Treffermenge nicht (oder werden als Teil von `scope` geschlüsselt).
IGNORED_PARAMS = frozenset({'page', 'facet', 'include_current_facet', 'include_selected'})
# Modus statt Filter: zählt nicht gegen das Limit von einem Filterwert.
MODE_PARAMS = frozenset({'unbestimmt'})
MAX_FILTER_VALUES = 1


def _generation():
    return cache.get(GENERATION_KEY, 0)


def invalidate():
    """Alle Browse-Daten verwerfen (neue Generation statt Schlüssel-Suche)."""
    try:
        cache.incr(GENERATION_KEY)
    except ValueError:
        cache.set(GENERATION_KEY, 1, None)


def cache_key(request, scope, *, localized=False):
    """Schlüssel für diese Anfrage oder None, wenn sie nicht gecacht wird."""
    params = []
    filter_values = 0
    for name in sorted(request.GET):
        if name in IGNORED_PARAMS:
            continue
        values = [v for v in request.GET.getlist(name) if is_valid_qparam(v)]
        if not values:
            continue
        if name in FREE_TEXT_PARAMS:
            return None
        if name not in MODE_PARAMS:
            filter_values += len(values)
        params.append((name, tuple(sorted(values))))
    if filter_values > MAX_FILTER_VALUES:
        return None
    language = (get_language() or '') if localized else ''
    raw = repr((scope, language, params))
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]
    return f'browse-data:{_generation()}:{digest}'


def get_or_compute(request, scope, compute, *, localized=False):
    key = cache_key(request, scope, localized=localized)
    if key is None:
        return compute()
    value = cache.get(key)
    if value is None:
        value = compute()
        cache.set(key, value, TTL)
    return value
