"""Fill-only enrichment of GeoNames, GND and VIAF identifiers from explicit links.

Only identity links already published by Nomisma (skos:exactMatch/closeMatch) or,
when Nomisma has none, by the Wikidata item Nomisma links to are used. No name
matching. A value is proposed for automatic filling only if exactly one distinct
identifier results; everything else is left for editorial review.
"""
import re

PROPOSAL_SCHEMA = 'eligius-identifier-proposals-v1'
INVENTORY_SCHEMA = 'eligius-identifier-inventory-v1'

_GEONAMES = re.compile(r'^https?://(?:sws\.|www\.)?geonames\.org/([1-9][0-9]*)(?:/.*)?$')
_GND = re.compile(r'^https?://d-nb\.info/gnd/([0-9]{1,10}-?[0-9Xx])/?$')
_VIAF = re.compile(r'^https?://(?:www\.)?viaf\.org/viaf/([1-9][0-9]*)/?$')

# model label -> target field -> (identifier kind, Wikidata property)
TARGETS = {
    'slg.Mzstaette': {'geonames': ('geonames', 'P1566')},
    'slg.Person': {'DNB': ('gnd', 'P227'), 'VIAF': ('viaf', 'P214')},
}


def _clean(value):
    return value.strip() if isinstance(value, str) else ''


def geonames_id(value):
    value = _clean(value)
    if re.fullmatch(r'[1-9][0-9]*', value):
        return value
    match = _GEONAMES.match(value)
    return match[1] if match else None


def gnd_id(value):
    value = _clean(value)
    if re.fullmatch(r'[0-9]{1,10}-?[0-9Xx]', value):
        return value.upper()
    match = _GND.match(value)
    return match[1].upper() if match else None


def viaf_id(value):
    value = _clean(value)
    if re.fullmatch(r'[1-9][0-9]*', value):
        return value
    match = _VIAF.match(value)
    return match[1] if match else None


PARSERS = {'geonames': geonames_id, 'gnd': gnd_id, 'viaf': viaf_id}


def geonames_uri(value):
    """Europeana's dereferenceable GeoNames pattern: https://sws.geonames.org/{id}/."""
    identifier = geonames_id(value)
    return f'https://sws.geonames.org/{identifier}/' if identifier else None


def stored_value(kind, identifier):
    """Value as written into the Eligius field (geonames holds the bare ID)."""
    return {
        'geonames': identifier,
        'gnd': f'https://d-nb.info/gnd/{identifier}',
        'viaf': f'https://viaf.org/viaf/{identifier}',
    }[kind]


def classify_link(uri):
    """Return (kind, identifier) for GeoNames/GND/VIAF/Wikidata URIs, else None."""
    for kind, parser in (('geonames', lambda v: (_GEONAMES.match(v) or [None, None])[1]),
                         ('gnd', lambda v: (_GND.match(v) or [None, None])[1]),
                         ('viaf', lambda v: (_VIAF.match(v) or [None, None])[1])):
        identifier = parser(uri)
        if identifier:
            return kind, identifier.upper() if kind == 'gnd' else identifier
    match = re.match(r'^https?://(?:www\.)?wikidata\.org/(?:entity|wiki)/(Q[1-9][0-9]*)/?$', uri)
    return ('wikidata', match[1]) if match else None


def nomisma_links(rdf, identifier):
    """Explicit exact/close matches of the Nomisma concept, grouped by kind."""
    from rdflib import Graph, URIRef
    from rdflib.namespace import SKOS
    graph = Graph().parse(data=rdf, format='xml')
    subjects = [URIRef(f'{scheme}://nomisma.org/id/{identifier}') for scheme in ('http', 'https')]
    links = {}
    for subject in subjects:
        for predicate in (SKOS.exactMatch, SKOS.closeMatch):
            for obj in graph.objects(subject, predicate):
                found = classify_link(str(obj))
                if found:
                    links.setdefault(found[0], set()).add(found[1])
    return {kind: sorted(values) for kind, values in links.items()}


def wikidata_values(entity, prop):
    """Non-deprecated string values of a Wikidata property; preferred rank wins."""
    claims = [c for c in (entity or {}).get('claims', {}).get(prop, []) if c.get('rank') != 'deprecated']
    preferred = [c for c in claims if c.get('rank') == 'preferred']
    values = set()
    for claim in preferred or claims:
        value = claim.get('mainsnak', {}).get('datavalue', {}).get('value')
        if isinstance(value, str) and value.strip():
            values.add(value.strip())
    return values


def decide(model, record, links, entities):
    """Proposals for every target field of one inventory record.

    links: nomisma_links() result or None; entities: {Q-id: Wikidata entity}.
    """
    rows = []
    for field, (kind, prop) in TARGETS[model].items():
        parser = PARSERS[kind]
        current_raw = _clean(record.get(field))
        current = parser(current_raw) if current_raw else None
        direct = set((links or {}).get(kind, []))
        via = {}
        candidates = []
        for value in sorted(direct):
            candidates.append({'value': value, 'via': 'nomisma'})
        if not direct:
            for q in (links or {}).get('wikidata', []):
                for raw in sorted(wikidata_values(entities.get(q), prop)):
                    value = parser(raw)
                    if value and value not in via:
                        via[value] = q
                        candidates.append({'value': value, 'via': 'wikidata', 'wikidata': q})
        distinct = sorted({c['value'] for c in candidates})
        if current_raw:
            status = ('present' if current is None or not distinct or current in distinct
                      else 'present_differs')
        elif not distinct:
            status = 'none'
        elif len(distinct) == 1:
            status = 'auto'
        else:
            status = 'review'
        rows.append({
            'model': model, 'id': record['id'], 'label': record.get('label', ''),
            'name_nom_id': record.get('name_nom_id') or '', 'field': field, 'kind': kind,
            'current': current_raw, 'status': status,
            'value': stored_value(kind, distinct[0]) if status == 'auto' else None,
            'candidates': candidates,
        })
    return rows
