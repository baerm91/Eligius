"""EDM RDF/XML mapping; never includes annotations or editorial fields."""
import re
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree as ET

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .identifiers import absolute_uri, image_redirect_uri, object_uri
from .rights import image_rights_uri, metadata_rights_uri
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


IMAGE_VARIANTS = (('av', 'av', 'Vorderseite'), ('rv', 'rv', 'Rückseite'))
THUMBNAIL_VARIANTS = (('av-vorschau', 'thumbnail_av'), ('rv-vorschau', 'thumbnail_rv'))


def source_images(row, request):
    """Current absolute image URLs per stable variant.

    Reuses MTOA's existing live-path/fallback resolver, no alternative guesses.
    The reverse is omitted when it resolves to the same file as the obverse.
    """
    urls = row.get_bild_urls or {}
    result = {}
    for variant, key in (*((v, k) for v, k, _ in IMAGE_VARIANTS), *THUMBNAIL_VARIANTS):
        if urls.get(key):
            uri = quote(absolute_uri(request, urls[key]), safe=":/?#[]@!$&'()*+,;=%")
            if valid_uri(uri) and uri not in result.values():
                result[variant] = uri
    return result


def public_image_uri(request, row, variant, source):
    """Stable Eligius redirect URI when a channel is configured, otherwise the file itself."""
    return image_redirect_uri(request, row.obj_id, variant) or source


def images(row, request):
    sources = source_images(row, request)
    return [(public_image_uri(request, row, variant, sources[variant]), label)
            for variant, _, label in IMAGE_VARIANTS if variant in sources]


def thumbnail(row, request):
    sources = source_images(row, request)
    for variant, _ in THUMBNAIL_VARIANTS:
        if variant in sources:
            return public_image_uri(request, row, variant, sources[variant])
    return None


def typology_entries(obj, row=None):
    """(URI, citation label) for every published typology link, first label wins."""
    values = []
    if obj.Typ:
        values.append((obj.Typ.link, obj.Typ.muenztyptitel or (row.typ if row else '')))
        # Konkordanz conveys related types, never asserted semantic identity.
        values += [(typ.link, typ.muenztyptitel) for typ in obj.Typ.Konkordanz.all()]
    for ref in obj.obj_ref_set.all():
        values.append((ref.link, ' '.join(clean_text(part) for part in (ref.idfk_Ref.abk, ref.nummer)
                                          if clean_text(part))))
    entries = {}
    for value, label in values:
        uri = valid_uri(value)
        if uri and uri not in entries:
            entries[uri] = clean_text(label)
    return list(entries.items())


def typology_uris(obj):
    return [uri for uri, _ in typology_entries(obj)]


def serialize_edm(row, obj, request):
    root = ET.Element(qname('rdf', 'RDF'))
    cho_uri = object_uri(request, row.obj_id) + '#providedCHO'
    aggregation_uri = object_uri(request, row.obj_id) + '#aggregation'
    cho = element(root, 'edm', 'ProvidedCHO', **{qname('rdf', 'about'): cho_uri})
    literal(cho, 'dc', 'title', record_title(row), 'de')
    literal(cho, 'dc', 'identifier', row.invnr)
    resource(cho, 'dcterms', 'isPartOf', absolute_uri(request, obj.Slg.get_absolute_url()))
    # Contextual classes: URI -> (class, {language or None: prefLabel}).
    contexts = {}
    def context(uri, kind, de=None, en=None, neutral=None):
        labels = {lang: clean_text(text) for lang, text in (('de', de), ('en', en), (None, neutral))
                  if clean_text(text)}
        if labels:
            contexts[uri] = (kind, labels)

    collection_authority = valid_uri(obj.Slg.nomisma_collection_uri)
    if collection_authority:
        resource(cho, 'dcterms', 'isPartOf', collection_authority)
        context(collection_authority, 'Concept', de=obj.Slg.name)
    literal(cho, 'dcterms', 'isPartOf', obj.Slg.name, 'de')
    literal(cho, 'dcterms', 'temporal', date_label(row), 'de')

    def controlled(prefix, name, text, model, kind='Concept'):
        literal(cho, prefix, name, text, 'de')
        uri = authority_uri(model.name_nom_id) if model else None
        if uri:
            resource(cho, prefix, name, uri)
            context(uri, kind, de=text or model.name, en=getattr(model, 'name_en', ''))

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
                context(uri, 'Place', de=row.mzstaette or mint.name, en=mint.name_en)

    literal(cho, 'dc', 'subject', row.typ, 'de')
    for uri, label in typology_entries(obj, row):
        resource(cho, 'dc', 'subject', uri)
        # Catalogue citations such as "RIC II.1 Domitian 78A" are language-neutral.
        context(uri, 'Concept', neutral=label)
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
            context(uri, 'Agent', de=person.name)
    element(cho, 'edm', 'type', 'IMAGE')

    views = images(row, request)
    image_rights = image_rights_uri(obj.Slg)
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
        preview = thumbnail(row, request)
        if preview:
            resource(aggregation, 'edm', 'object', preview)
    element(aggregation, 'edm', 'provider', 'Eligius')
    metadata_rights = metadata_rights_uri(obj.Slg)
    if metadata_rights:
        # Rights on the metadata aggregation, never on the physical coin or images.
        resource(aggregation, 'dc', 'rights', metadata_rights)
    if image_rights:
        resource(aggregation, 'edm', 'rights', image_rights)
    for uri, (kind, labels) in contexts.items():
        node = element(root, 'skos' if kind == 'Concept' else 'edm', kind, **{qname('rdf', 'about'): uri})
        for language, label in labels.items():
            literal(node, 'skos', 'prefLabel', label, language)
    return root
