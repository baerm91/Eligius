"""Machine-readable rights for Kulturpool/Europeana.

Europeana and Kulturpool expect the canonical http:// form of Creative Commons
and RightsStatements.org URIs. Free text is only recognised when the whole
value is an unambiguous licence label such as "CC BY-NC 4.0"; anything else
produces no rights statement rather than a guessed one.
"""
import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

HTTP_URL = URLValidator(schemes=['http', 'https'])
CANONICAL_HOSTS = ('creativecommons.org', 'rightsstatements.org')
CC_VERSIONS = ('1.0', '2.0', '2.5', '3.0', '4.0')
CC_LICENCES = ('by', 'by-sa', 'by-nd', 'by-nc', 'by-nc-sa', 'by-nc-nd')
CC_LABEL = re.compile(
    r'(?:creative\s+commons|cc)[\s-]+(?P<terms>by(?:[\s-]+(?:nc|sa|nd)){0,2})'
    r'(?:[\s-]+(?:v(?:ersion)?\s*)?(?P<version>\d\.\d))?', re.IGNORECASE)
CC0_LABEL = re.compile(r'(?:cc\s*0|cc[\s-]+zero|creative\s+commons\s+zero)(?:[\s-]+(?:v\s*)?1\.0)?',
                       re.IGNORECASE)
PDM_LABEL = re.compile(r'(?:public\s+domain\s+mark|pdm)(?:[\s-]+(?:v\s*)?1\.0)?', re.IGNORECASE)


def _plain_uri(value):
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        HTTP_URL(value)
        parsed = urlsplit(value)
    except (ValidationError, ValueError):
        return None
    if parsed.username or parsed.password:
        return None
    return value


def canonical_rights_uri(value):
    """Normalise CC/RightsStatements URIs; keep other valid URIs unchanged."""
    uri = _plain_uri(value)
    if not uri:
        return None
    parsed = urlsplit(uri)
    host = parsed.hostname or ''
    if host.startswith('www.'):
        host = host[4:]
    if host not in CANONICAL_HOSTS:
        return uri
    path = re.sub(r'/(?:deed(?:\.[A-Za-z-]+)?|legalcode(?:\.[A-Za-z-]+)?)/?$', '/', parsed.path)
    if not path.endswith('/'):
        path += '/'
    return f'http://{host}{path}'


def licence_from_label(text):
    """Map an exact licence label to its canonical URI, or return None."""
    if not text or not isinstance(text, str):
        return None
    label = re.sub(r'\s+', ' ', text).strip().rstrip('.').strip()
    if CC0_LABEL.fullmatch(label):
        return 'http://creativecommons.org/publicdomain/zero/1.0/'
    if PDM_LABEL.fullmatch(label):
        return 'http://creativecommons.org/publicdomain/mark/1.0/'
    match = CC_LABEL.fullmatch(label)
    if not match:
        return None
    terms = re.split(r'[\s-]+', match['terms'].lower())
    if len(set(terms)) != len(terms) or ('sa' in terms and 'nd' in terms):
        return None
    ordered = ['by'] + [t for t in ('nc', 'sa', 'nd') if t in terms]
    code = '-'.join(ordered)
    version = match['version'] or None
    if code not in CC_LICENCES or version not in CC_VERSIONS:
        # Without an explicit version the licence is ambiguous.
        return None
    return f'http://creativecommons.org/licenses/{code}/{version}/'


def image_rights_uri(slg):
    """Explicit Kulturpool URI first, then the displayed licence field (URI or exact label)."""
    configured = canonical_rights_uri(slg.kulturpool_rights_uri)
    if configured:
        return configured
    legacy = slg.bildrechte_lizenz
    return canonical_rights_uri(legacy) or licence_from_label(legacy)


def metadata_rights_uri(slg):
    return canonical_rights_uri(slg.kulturpool_metadata_rights_uri)
