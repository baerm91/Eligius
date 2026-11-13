"""Read-only inventory of authority references; never changes source identifiers."""
import re
from collections import Counter
from urllib.parse import urlsplit


def identify_authority(value, *, allow_nomisma_id=False):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if allow_nomisma_id and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.'-]*", value):
        return ('nomisma', value)
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or url.username or url.password or url.port:
            return None
    except ValueError:
        return None
    if url.query or url.fragment:
        return None
    patterns = {
        'nomisma.org': ('nomisma', r"/id/([A-Za-z0-9_][A-Za-z0-9_.'-]*)/?"),
        'www.wikidata.org': ('wikidata', r'/(?:entity|wiki)/(Q[1-9][0-9]*)/?'),
        'wikidata.org': ('wikidata', r'/(?:entity|wiki)/(Q[1-9][0-9]*)/?'),
        'd-nb.info': ('gnd', r'/gnd/([0-9][0-9Xx-]*)/?'),
    }
    source = patterns.get(url.hostname)
    if source and (match := re.fullmatch(source[1], url.path)):
        return source[0], match[1]
    return None


def inventory(records):
    """Input: model, id, label, field, value. Keep unsupported links for review."""
    rows = []
    for record in records:
        ref = identify_authority(record['value'], allow_nomisma_id=record['field'] == 'name_nom_id')
        rows.append({**record, 'provider': ref[0] if ref else None,
                     'authority_id': ref[1] if ref else None,
                     'status': 'recognized' if ref else 'review_required'})
    return {
        'reference_count': len(rows),
        'unique_authorities': len({(r['provider'], r['authority_id']) for r in rows if r['provider']}),
        'by_provider': dict(Counter(r['provider'] or 'review_required' for r in rows)),
        'records': rows,
    }
