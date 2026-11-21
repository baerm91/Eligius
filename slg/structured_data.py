"""Strukturierte Daten (schema.org als JSON-LD) für Suchmaschinen.

Alle Bausteine liefern reine Python-Dicts; ``{% json_ld %}`` serialisiert sie
sicher in ein ``<script type="application/ld+json">``. Die Angaben sind
unsichtbar und ersetzen keine sichtbaren Elemente (z. B. keine sichtbaren
Breadcrumbs). Lizenzen und Normdaten-URIs kommen aus denselben Funktionen wie
der Kulturpool-/EDM-Export, damit beide Kanäle dasselbe behaupten.
"""
from decimal import Decimal

from django.urls import reverse
from django.utils.translation import gettext as _

from .oai.edm import PERSON_AUTHORITY_FIELDS, authority_uri, typology_entries, valid_uri
from .oai.rights import image_rights_uri, metadata_rights_uri
from .seo import absolute_url, clean_text, public_base_url

CONTEXT = 'https://schema.org'
SITE_NAME = 'Eligius'
RULER_ROLES = (1, 6, 7)      # Prägeherr / Münzherr (wie EDM-Export und MTOA)
DEPICTED_ROLE = 2            # dargestellte Person
UNIVERSITY = {
    '@type': 'CollegeOrUniversity',
    'name': 'Universität für Weiterbildung Krems',
    'url': 'https://www.donau-uni.ac.at/',
}


def _compact(value):
    """Leere Werte rekursiv entfernen, damit kein ``"name": ""`` ausgegeben wird."""
    if isinstance(value, dict):
        result = {k: _compact(v) for k, v in value.items()}
        return {k: v for k, v in result.items() if v not in (None, '', [], {})}
    if isinstance(value, (list, tuple)):
        result = [_compact(v) for v in value]
        return [v for v in result if v not in (None, '', [], {})]
    return value


def _unique(values):
    return list(dict.fromkeys(v for v in values if v))


def graph(*nodes):
    return _compact({'@context': CONTEXT, '@graph': [n for n in nodes if n]})


def _url(request, path):
    return public_base_url(request) + path


def organization_id(request):
    return _url(request, '/#organization')


def website_id(request):
    return _url(request, '/#website')


# ---------------------------------------------------------------------------
# Startseite

def organization(request):
    return {
        '@type': 'Organization',
        '@id': organization_id(request),
        'name': SITE_NAME,
        'alternateName': 'Numotheca Austriaca Eligius',
        'url': _url(request, '/'),
        'description': _('Digitales Münzkabinett für klösterliche und öffentliche Sammlungen in Österreich.'),
        'parentOrganization': UNIVERSITY,
    }


def website(request):
    return {
        '@type': 'WebSite',
        '@id': website_id(request),
        'name': SITE_NAME,
        'url': _url(request, '/'),
        'inLanguage': ['de', 'en'],
        'publisher': {'@id': organization_id(request)},
        'potentialAction': {
            '@type': 'SearchAction',
            'target': {
                '@type': 'EntryPoint',
                'urlTemplate': _url(request, reverse('Objektliste')) + '?q={search_term_string}',
            },
            'query-input': 'required name=search_term_string',
        },
    }


def home_graph(request):
    return graph(organization(request), website(request))


# ---------------------------------------------------------------------------
# Breadcrumbs (nur als Markup, nicht sichtbar)

def breadcrumbs(request, *items):
    """``items``: (Name, Pfad) ab der Startseite; der letzte Eintrag ist die aktuelle Seite."""
    trail = [(_('Startseite'), '/'), *items]
    return {
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': pos, 'name': clean_text(name, limit=0), 'item': _url(request, path)}
            for pos, (name, path) in enumerate(trail, start=1)
        ],
    }


# ---------------------------------------------------------------------------
# Normdaten

def _defined_term(name, model):
    if not model:
        return None
    return {
        '@type': 'DefinedTerm',
        'name': name or str(model),
        'sameAs': _unique([authority_uri(getattr(model, 'name_nom_id', None))]),
    }


def _mint_place(mint, name):
    if not mint:
        return None
    geonames = (mint.geonames or '').strip()
    return {
        '@type': 'Place',
        'name': name,
        'sameAs': _unique([
            authority_uri(mint.name_nom_id),
            f'https://www.geonames.org/{geonames}' if geonames.isdigit() else valid_uri(geonames),
            valid_uri(mint.ndpikmk),
        ]),
    }


def _person(person, name):
    fields = (*PERSON_AUTHORITY_FIELDS, 'WikiDe', 'WikiEn')
    return {
        '@type': 'Person',
        'name': name,
        'sameAs': _unique([authority_uri(person.name_nom_id), *(valid_uri(getattr(person, f, None)) for f in fields)]),
    }


# ---------------------------------------------------------------------------
# Sammlung

def collection_id(request, slg):
    return _url(request, slg.get_absolute_url()) + '#collection'


def collection_reference(request, slg, name):
    return {
        '@type': 'Collection',
        '@id': collection_id(request, slg),
        'name': name,
        'url': _url(request, slg.get_absolute_url()),
        'sameAs': _unique([valid_uri(slg.nomisma_collection_uri)]),
    }


def collection_graph(request, slg, name, description, object_count, image=''):
    """Sammlung als ``Dataset`` (Google Dataset Search) und ``Collection``."""
    url = _url(request, slg.get_absolute_url())
    distributions = []
    if slg.nomisma_export_erlaubt:
        distributions.append({
            '@type': 'DataDownload',
            'name': 'Nomisma RDF',
            'encodingFormat': 'application/rdf+xml',
            'contentUrl': _url(request, reverse('collection_nomisma_rdf', kwargs={'id': slg.id})),
        })
    if slg.kulturpool_export_erlaubt:
        distributions.append({
            '@type': 'DataDownload',
            'name': 'OAI-PMH (EDM)',
            'encodingFormat': 'application/xml',
            'contentUrl': (_url(request, reverse('oai_endpoint'))
                           + f'?verb=ListRecords&metadataPrefix=edm&set=eligius:collection-{slg.id}'),
        })
    dataset = {
        '@type': ['Dataset', 'Collection'],
        '@id': collection_id(request, slg),
        'name': name,
        'description': clean_text(description, limit=5000),
        'url': url,
        'sameAs': _unique([valid_uri(slg.nomisma_collection_uri)]),
        'image': absolute_url(image, request),
        'keywords': [_('Numismatik'), _('Münzen'), name],
        'isAccessibleForFree': True,
        'inLanguage': 'de',
        'collectionSize': object_count,
        'license': metadata_rights_uri(slg),
        'creator': {'@type': 'Organization', 'name': name},
        'publisher': {'@id': organization_id(request)},
        'provider': {'@id': organization_id(request)},
        'includedInDataCatalog': {'@type': 'DataCatalog', 'name': SITE_NAME, 'url': _url(request, '/')},
        'distribution': distributions,
    }
    trail = breadcrumbs(request, (_('Sammlungen'), reverse('sammlungen_uebersicht')),
                        (name, slg.get_absolute_url()))
    return graph(dataset, trail, organization(request))


# ---------------------------------------------------------------------------
# Objekt

def _image(request, url, thumbnail, label, licence, credit, description=''):
    url = absolute_url(url, request)
    if not url:
        return None
    return {
        '@type': 'ImageObject',
        'contentUrl': url,
        'thumbnailUrl': absolute_url(thumbnail, request),
        'name': label,
        'description': description,
        'license': licence,
        'creditText': credit,
        'copyrightNotice': credit,
    }


def _quantity(name, value, unit_code, unit_text):
    if value in (None, ''):
        return None
    if isinstance(value, Decimal):
        value = float(value) if value % 1 else int(value)
    return {'@type': 'PropertyValue', 'name': name, 'value': value, 'unitCode': unit_code, 'unitText': unit_text}


def object_graph(request, obj, coin_data, labels):
    """Münze/Objekt als ``VisualArtwork``.

    ``labels`` enthält bereits lokalisierte Anzeigenamen (title, collection,
    nominal, metal, mint, object_type, description), wie sie auch auf der
    Seite stehen.
    """
    url = _url(request, obj.get_absolute_url())
    slg = obj.Slg
    collection_name = labels.get('collection') or (slg.name if slg else '')
    licence = image_rights_uri(slg) if slg else None
    credit = clean_text(collection_name, limit=0)
    bild_urls = coin_data.get('bild_urls') or {}
    images = [
        _image(request, bild_urls.get('av'), bild_urls.get('thumbnail_av'), _('Vorderseite'), licence, credit,
               labels.get('alt', {}).get('av')),
        _image(request, bild_urls.get('rv'), bild_urls.get('thumbnail_rv'), _('Rückseite'), licence, credit,
               labels.get('alt', {}).get('rv')),
    ]

    creators, depicted = [], []
    for rel in coin_data.get('personen') or []:
        person = getattr(rel, 'idfk_Person', None)
        if not person or not person.name:
            continue
        node = _person(person, labels.get('persons', {}).get(person.pk, person.name))
        role = getattr(rel, 'idfk_PersonFunktion_id', None)
        if role in RULER_ROLES and node not in creators:
            creators.append(node)
        elif role == DEPICTED_ROLE and node not in depicted:
            depicted.append(node)

    typ = coin_data.get('Typ')
    example_of = None
    if typ:
        citation = clean_text(typ.muenztyptitel, limit=0)
        example_of = {
            '@type': 'CreativeWork',
            '@id': _url(request, typ.get_absolute_url()) + '#type',
            'name': citation if citation.lower() != 'unbestimmt' else None,
            'url': _url(request, typ.get_absolute_url()),
            # Nur der eigene Typ-Link ist identisch; Konkordanzen sind verwandt, nicht gleich.
            'sameAs': _unique([valid_uri(typ.link)]),
        }
    references = [{'@type': 'CreativeWork', 'name': label, 'url': uri} for uri, label in typology_entries(obj)]

    keywords = _unique(clean_text(str(entry.schlagwort), limit=0)
                       for key in ('av_schlagworte', 'rv_schlagworte')
                       for entry in (coin_data.get(key) or []) if getattr(entry, 'schlagwort', None))

    artwork = {
        '@type': 'VisualArtwork',
        '@id': url + '#object',
        'url': url,
        'name': labels.get('title'),
        'description': labels.get('description'),
        'identifier': {'@type': 'PropertyValue', 'propertyID': _('Inventarnummer'), 'value': obj.invnr},
        'artform': labels.get('object_type'),
        'artMedium': labels.get('metal'),
        'material': labels.get('metal'),
        'temporalCoverage': clean_text(coin_data.get('dat_verb'), limit=0),
        'locationCreated': _mint_place(coin_data.get('mzstaette'), labels.get('mint')),
        'creator': creators,
        'about': depicted,
        'exampleOfWork': example_of,
        'citation': references,
        'keywords': keywords,
        'image': images,
        'isPartOf': collection_reference(request, slg, collection_name) if slg else None,
        'provider': {'@id': organization_id(request)},
        'additionalProperty': [
            {'@type': 'PropertyValue', 'name': _('Nominal'), 'value': labels.get('nominal'),
             'valueReference': _defined_term(labels.get('nominal'), coin_data.get('nominal'))}
            if coin_data.get('nominal') else None,
            {'@type': 'PropertyValue', 'name': _('Material'), 'value': labels.get('metal'),
             'valueReference': _defined_term(labels.get('metal'), coin_data.get('metall'))}
            if coin_data.get('metall') else None,
            _quantity(_('Gewicht'), coin_data.get('gewicht'), 'GRM', 'g'),
            _quantity(_('Durchmesser'), coin_data.get('durchmesser'), 'MMT', 'mm'),
            _quantity(_('Stempelstellung'), coin_data.get('stempelstellung'), None, 'h'),
            {'@type': 'PropertyValue', 'name': _('Vs.'), 'value': clean_text(coin_data.get('avleg'), limit=0)}
            if coin_data.get('avleg') else None,
            {'@type': 'PropertyValue', 'name': _('Rs.'), 'value': clean_text(coin_data.get('rvleg'), limit=0)}
            if coin_data.get('rvleg') else None,
        ],
    }
    crumbs = [(collection_name, slg.get_absolute_url())] if slg else []
    title = labels.get('title')
    current = f'{obj.invnr} – {title}' if title and title != obj.invnr else obj.invnr
    trail = breadcrumbs(request, *crumbs, (current, obj.get_absolute_url()))
    return graph(artwork, trail, organization(request))


# ---------------------------------------------------------------------------
# Münztyp & Paket: nur Breadcrumbs

def typ_graph(request, typ, title):
    return graph(breadcrumbs(request, (_('Münzen & Objekte durchsuchen'), reverse('Objektliste')),
                             (title, typ.get_absolute_url())))


def paket_graph(request, paket, name):
    return graph(breadcrumbs(request, (_('Neuerschließungen'), reverse('neuerschliessungen')),
                             (name, reverse('paket_detail', kwargs={'slug': paket.slug}))))
