"""EDM RDF/XML mapping; never includes annotations or editorial fields."""
import re
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .identifiers import absolute_uri, object_uri
from .xml import clean_text, element, qname

EDM_SCHEMA = 'https://www.europeana.eu/schemas/edm/EDM.xsd'
HTTP_URL = URLValidator(schemes=['http', 'https'])
PERSON_AUTHORITY_FIELDS = ('DNB', 'VIAF', 'DB', 'OeBL', 'mmlo')


def valid_uri(value):
    if not value or not isinstance(value, str) or value != value.strip():
        return None
    if any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        HTTP_URL(value)
        parsed = urlsplit(value)
        if parsed.username or parsed.password:
            return None
    except (ValidationError, ValueError):
        return None
    return value


def authority_uri(value):
    """Only a field explicitly named name_nom_id may contain a bare Nomisma ID."""
    if valid_uri(value):
        return value
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', value):
        return 'http://nomisma.org/id/' + value
    return None


def resource(parent, prefix, name, uri):
    return element(parent, prefix, name, **{qname('rdf', 'resource'): uri})


def literal(parent, prefix, name, value, language=None):
    text = clean_text(value)
    if text:
        attributes = {'{http://www.w3.org/XML/1998/namespace}lang': language} if language else {}
        return element(parent, prefix, name, text, **attributes)


def date_label(row):
    if clean_text(row.datierung_verbale):
        return clean_text(row.datierung_verbale)
    def year(value):
        return f'{abs(value)} v. Chr.' if value < 0 else str(value)
    start, end = row.datierung_von, row.datierung_bis
    if start is not None and end is not None:
        return year(start) if start == end else f'{year(start)} – {year(end)}'
    return year(start if start is not None else end) if start is not None or end is not None else ''


def record_title(row):
    if clean_text(row.objekttitel):
        return clean_text(row.objekttitel)
    rulers = list(dict.fromkeys(clean_text(rel.person.name) for rel in row.mtoaperson_set.all()
                               if rel.funktion_id in (1, 6, 7)))
    parts = [clean_text(row.nominal or row.objekttyp), ' / '.join(rulers), date_label(row)]
    return ', '.join(p for p in parts if p) or f'Objekt {clean_text(row.invnr) or row.obj_id}'


def has_descriptive_title(row):
    return bool(clean_text(row.objekttitel or row.nominal or row.objekttyp) or date_label(row)
                or any(rel.funktion_id in (1, 6, 7) for rel in row.mtoaperson_set.all()))


def images(row, request):
    """Reuse MTOA's existing live-path/fallback resolver, no alternative guesses."""
    urls = row.get_bild_urls or {}
    result = []
    for side, label in (('av', 'Vorderseite'), ('rv', 'Rückseite')):
        if urls.get(side):
            uri = quote(absolute_uri(request, urls[side]), safe=":/?#[]@!$&'()*+,;=%")
            if valid_uri(uri) and uri not in [entry[0] for entry in result]:
                result.append((uri, label))
    return result


def typology_uris(obj):
    values = [obj.Typ.link] if obj.Typ else []
    if obj.Typ:
        # Konkordanz conveys related types, never asserted semantic identity.
        values += [typ.link for typ in obj.Typ.Konkordanz.all()]
    values += [ref.link for ref in obj.obj_ref_set.all()]
    return list(dict.fromkeys(uri for value in values if (uri := valid_uri(value))))


def serialize_edm(row, obj, request):
    root = ET.Element(qname('rdf', 'RDF'))
    cho_uri = object_uri(request, row.obj_id) + '#providedCHO'
    aggregation_uri = object_uri(request, row.obj_id) + '#aggregation'
    cho = element(root, 'edm', 'ProvidedCHO', **{qname('rdf', 'about'): cho_uri})
    literal(cho, 'dc', 'title', record_title(row), 'de')
    literal(cho, 'dc', 'identifier', row.invnr)
    resource(cho, 'dcterms', 'isPartOf', absolute_uri(request, obj.Slg.get_absolute_url()))
    collection_authority = valid_uri(obj.Slg.nomisma_collection_uri)
    if collection_authority:
        resource(cho, 'dcterms', 'isPartOf', collection_authority)
    literal(cho, 'dcterms', 'isPartOf', obj.Slg.name, 'de')
    literal(cho, 'dcterms', 'temporal', date_label(row), 'de')

    contexts = {}
    def controlled(prefix, name, text, model, context='Concept'):
        literal(cho, prefix, name, text, 'de')
        uri = authority_uri(model.name_nom_id) if model else None
        if uri:
            resource(cho, prefix, name, uri)
            contexts[uri] = (context, clean_text(text or model.name))

    controlled('dc', 'type', row.objekttyp, row.objekttyp_fk)
    controlled('dc', 'type', row.nominal, row.nominal_fk)
    controlled('dcterms', 'medium', row.metall, row.metall_fk)
    controlled('dcterms', 'spatial', row.mzstaette, row.mzstaette_fk, 'Place')
    controlled('dcterms', 'spatial', row.region, row.region_fk, 'Place')
    controlled('dc', 'subject', row.herstellung, row.herstellung_fk)
    if row.mzstaette_fk:
        mint = row.mzstaette_fk
        for field in ('geonames', 'ndpikmk'):
            value = getattr(mint, field)
            uri = valid_uri(value)
            if field == 'geonames' and value and value.isdigit():
                uri = f'https://www.geonames.org/{value}'
            if uri:
                resource(cho, 'dcterms', 'spatial', uri)
                contexts[uri] = ('Place', clean_text(row.mzstaette))

    literal(cho, 'dc', 'subject', row.typ, 'de')
    for uri in typology_uris(obj):
        resource(cho, 'dc', 'subject', uri)
    for side, name in (('av', 'Vorderseite'), ('rv', 'Rückseite')):
        # MTOA already resolves object/type precedence and Offizin placeholders.
        description = getattr(row, side + '_bildtyp')
        if clean_text(description):
            literal(cho, 'dc', 'description', f'{name}: {clean_text(description)}', 'de')
        mint_mark = getattr(row, side + '_beizeichen')
        if clean_text(mint_mark):
            literal(cho, 'dc', 'description', f'{name}, Beizeichen: {clean_text(mint_mark)}', 'de')
        legend = getattr(row, side + '_legende')
        if clean_text(legend):
            literal(cho, 'dc', 'description', f'{name}, Legende: {clean_text(legend)}', 'de')
    for label, value, unit in (('Gewicht', row.gewicht, 'g'), ('Durchmesser', row.durchmesser, 'mm'),
                               ('Stempelstellung', row.stempelstellung, 'h')):
        if value is not None and value != '':
            literal(cho, 'dcterms', 'extent', f'{label}: {value} {unit}', 'de')

    seen_people = set()
    for rel in row.mtoaperson_set.all():
        # Role IDs 1/6/7 are minting authorities; 2 is a depicted person,
        # as in MTOA.get_praegeherren/get_dargestellte_av/get_dargestellte_rv.
        predicate = 'creator' if rel.funktion_id in (1, 6, 7) else ('subject' if rel.funktion_id == 2 else 'contributor')
        key = (rel.person_id, predicate)
        if key in seen_people:
            continue
        seen_people.add(key)
        person = rel.person
        literal(cho, 'dc', predicate, person.name, 'de')
        uris = [authority_uri(person.name_nom_id)]
        uris += [valid_uri(getattr(person, field)) for field in PERSON_AUTHORITY_FIELDS]
        for uri in dict.fromkeys(uri for uri in uris if uri):
            resource(cho, 'dc', predicate, uri)
            contexts[uri] = ('Agent', clean_text(person.name))
    element(cho, 'edm', 'type', 'IMAGE')

    views = images(row, request)
    image_rights = valid_uri(obj.Slg.kulturpool_rights_uri) or valid_uri(obj.Slg.bildrechte_lizenz)
    for uri, label in views:
        web = element(root, 'edm', 'WebResource', **{qname('rdf', 'about'): uri})
        literal(web, 'dc', 'description', label, 'de')
        if image_rights:
            resource(web, 'edm', 'rights', image_rights)

    aggregation = element(root, 'ore', 'Aggregation', **{qname('rdf', 'about'): aggregation_uri})
    resource(aggregation, 'edm', 'aggregatedCHO', cho_uri)
    literal(aggregation, 'edm', 'dataProvider', obj.Slg.name)
    # Europeana's RDF/XML XSD requires this property order on Aggregation.
    for uri, _ in views[1:]:
        resource(aggregation, 'edm', 'hasView', uri)
    resource(aggregation, 'edm', 'isShownAt', object_uri(request, row.obj_id))
    if views:
        resource(aggregation, 'edm', 'isShownBy', views[0][0])
        urls = row.get_bild_urls or {}
        thumbnail = urls.get('thumbnail_av') or urls.get('thumbnail_rv')
        if thumbnail:
            uri = quote(absolute_uri(request, thumbnail), safe=":/?#[]@!$&'()*+,;=%")
            if valid_uri(uri):
                resource(aggregation, 'edm', 'object', uri)
    element(aggregation, 'edm', 'provider', 'Eligius')
    metadata_rights = valid_uri(obj.Slg.kulturpool_metadata_rights_uri)
    if metadata_rights:
        # Rights on the metadata aggregation, never on the physical coin or images.
        resource(aggregation, 'dc', 'rights', metadata_rights)
    if image_rights:
        resource(aggregation, 'edm', 'rights', image_rights)
    for uri, (kind, label) in contexts.items():
        node = element(root, 'skos' if kind == 'Concept' else 'edm', kind, **{qname('rdf', 'about'): uri})
        literal(node, 'skos', 'prefLabel', label, 'de')
    return root
