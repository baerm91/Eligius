"""Shared helpers for rendering and parsing requests."""

import html as html_lib
import json
import logging
import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

from ..models import OffizinSymbol

logger = logging.getLogger(__name__)


def _request_object(request):
    """request.data als Objekt/QueryDict; ein JSON-Array o. Ä. ergibt HTTP 400 statt 500."""
    from rest_framework.exceptions import ParseError
    data = request.data
    if data is None or data == '':
        return {}
    if not hasattr(data, 'get'):
        raise ParseError('JSON-Objekt erwartet.')
    return data


_JSON_SCRIPT_ESCAPES = {
    ord('<'): '\\u003C',
    ord('>'): '\\u003E',
    ord('&'): '\\u0026',
    0x2028: '\\u2028',
    0x2029: '\\u2029',
}


def json_for_script(value):
    """JSON, das gefahrlos direkt in einen <script>-Block eingebettet werden kann."""
    return mark_safe(json.dumps(value).translate(_JSON_SCRIPT_ESCAPES))


_BEIZEICHEN_TOKEN_RE = re.compile(r'\[([^\]]+)\]')


def render_beizeichen_html(raw_text, symbol_html=None, offizin_name=None):
    """Baut die Beizeichen-HTML in einem Durchgang auf dem Rohtext auf.

    Platzhalter ([Offizinszeichen], [Monogramm], [Symbolname]) und "?" werden nur
    im Text zwischen den eingesetzten Symbolen ersetzt – nie in bereits
    erzeugtem HTML (Attribut-Breakout, "?" in Symbol-URLs).
    Rückgabe: (SafeString, ob "?" durch den Offizin-Namen ersetzt wurde).
    """
    raw = raw_text or ''
    offizin_used = False

    def text(part):
        nonlocal offizin_used
        if offizin_name and '?' in part:
            offizin_used = True
            return str(escape(offizin_name)).join(str(escape(p)) for p in part.split('?'))
        return str(escape(part))

    parts, pos = [], 0
    for match in _BEIZEICHEN_TOKEN_RE.finditer(raw):
        parts.append(text(raw[pos:match.start()]))
        name = match.group(1)
        if name in ('Offizinszeichen', 'Monogramm') and symbol_html:
            parts.append(str(symbol_html))
        else:
            symbol = OffizinSymbol.objects.filter(name=name).first()
            parts.append(str(symbol.get_svg_html()) if symbol else text(match.group(0)))
        pos = match.end()
    parts.append(text(raw[pos:]))
    return mark_safe(''.join(parts)), offizin_used


def replace_monogram_references(text):
    """
    Ersetzt Monogramm-Referenzen in eckigen Klammern durch entsprechende SVG-Symbole.
    
    Beispiel: "[Lorber Monogram 219]" wird durch das SVG-Symbol für "Lorber Monogram 219" ersetzt.
    """
    if not text:
        return text

    # Finde alle [Name] Muster im Text
    pattern = r'\[([^\]]+)\]'
    matches = re.findall(pattern, text)

    for match in matches:
        try:
            # Suche nach dem OffizinSymbol mit dem Namen
            symbol = OffizinSymbol.objects.get(name=html_lib.unescape(match))
            # Ersetze [Name] durch das SVG-HTML
            text = text.replace(f'[{match}]', symbol.get_svg_html())
        except OffizinSymbol.DoesNotExist:
            # Wenn das Symbol nicht gefunden wird, lasse den Text unverändert
            # Optional: Logge eine Warnung
            logger.warning(f"OffizinSymbol mit dem Namen '{match}' nicht gefunden.")
            continue
        except Exception as e:
            # Für andere Fehler, logge sie aber lasse den Text unverändert
            logger.error(f"Fehler beim Ersetzen von '{match}': {e}")
            continue

    return text
