"""Nomisma.org-Export (RDF/XML) pro Sammlung.

Aufbau nach https://nomisma.org/documentation/contribute:

* ``void:Dataset`` mit Titel, Beschreibung, Herausgeber, Lizenz, ``void:uriSpace``
  und ``void:dataDump`` (auch einzeln unter ``/slg/<id>/void.rdf``),
* je Münze ein ``nmo:NumismaticObject`` mit Titel, Inventarnummer, Sammlung,
  ``nmo:hasTypeSeriesItem`` (Pflicht), Maßen, Vorder-/Rückseitenbildern und
  ``void:inDataset``,
* Fundkontexte und Hortfunde aus freigegebenen Paketen als ``nmo:hasFindspot``
  bzw. ``nmo:Hoard``.

Wie beim Kulturpool-Export gilt: nur kontrollierte Objekte und Typen, stabile
URIs aus ``ELIGIUS_PUBLIC_BASE_URL``, Lizenz nur wenn eindeutig hinterlegt, Bilder
über den Weiterleitungsdienst wenn aktiviert. Anders als bei Kulturpool werden
nur Münzen exportiert, die einem Online-Typenkorpus zugeordnet werden können –
ohne Typ-URI kann Nomisma ein Objekt nicht verwenden.
"""
import os
import tempfile
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlsplit
from xml.sax.saxutils import escape, quoteattr

from django.conf import settings
from django.db.models import Prefetch, Q
from django.urls import reverse

from .models import MtoaPerson, Muenztyp, MuenztypObjektAnzeige, Obj, Obj_Ref, Paket
from .oai.edm import record_title, valid_uri
from .oai.identifiers import absolute_uri, image_redirect_uri
from .oai.rights import metadata_rights_uri
from .oai.xml import clean_text

CONTROLLED_WORKFLOW_NAME = 'kontrolliert'
CHUNK_SIZE = 1000
NUMISMATICS_HOST = 'numismatics.org'

NAMESPACES = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'dcterms': 'http://purl.org/dc/terms/',
    'void': 'http://rdfs.org/ns/void#',
    'nmo': 'http://nomisma.org/ontology#',
    'foaf': 'http://xmlns.com/foaf/0.1/',
    'crm': 'http://www.cidoc-crm.org/cidoc-crm/',
    'geo': 'http://www.w3.org/2003/01/geo/wgs84_pos#',
}
XSD = 'http://www.w3.org/2001/XMLSchema#'

# Online-Typenkorpora, zu denen Sammlungen ihre Münzen über Nomisma beitragen.
# RPC Online gehört bewusst nicht dazu: RPC sammelt Exemplare direkt bei den Sammlungen.
# (Host, Pfadpräfix) – ANS-Korpora verwenden /<Korpus>/id/<Typ-ID>.
TYPE_SERIES_PREFIXES = (
    ('numismatics.org', None),            # OCRE, CRRO, PELLA, SCO, PCO, HRC, AGCO, BIGR …
    ('iacb.arch.ox.ac.uk', '/id/'),       # Ancient British/Celtic Coins
    ('www.corpus-nummorum.eu', '/types/'),
    ('corpus-nummorum.eu', '/types/'),
)


# ---------------------------------------------------------------------------
# Auswahl

def is_type_series_uri(uri):
    uri = valid_uri(uri)
    if not uri:
        return False
    parsed = urlsplit(uri)
    host = (parsed.hostname or '').lower()
    for allowed_host, prefix in TYPE_SERIES_PREFIXES:
        if prefix is None and (host == allowed_host or host.endswith('.' + allowed_host)):
            segments = parsed.path.strip('/').split('/')
            return len(segments) == 3 and bool(segments[0]) and segments[1] == 'id' and bool(segments[2])
        if host == allowed_host and prefix and parsed.path.startswith(prefix):
            return bool(parsed.path[len(prefix):].strip('/'))
    return False


def _objects_with_type_links(slg):
    concordances = Muenztyp.objects.filter(
        workflow__name__iexact=CONTROLLED_WORKFLOW_NAME, link__icontains=NUMISMATICS_HOST,
    ).exclude(nach=True).only('pk', 'link').order_by('pk')
    return (
        Obj.objects.filter(Slg=slg, workflow__name__iexact=CONTROLLED_WORKFLOW_NAME, faelschung__isnull=True)
        .filter(Q(Typ__isnull=True) | Q(Typ__workflow__name__iexact=CONTROLLED_WORKFLOW_NAME))
        .exclude(Typ_unsicher=True)
        # „nach“/Variante: das Objekt entspricht dem zitierten Typ nicht genau.
        .exclude(obj_ref__nach=True)
        .select_related('Typ')
        .prefetch_related(
            Prefetch('obj_ref_set', queryset=Obj_Ref.objects.only('id', 'idfk_Obj_id', 'link', 'nach').order_by('id')),
            Prefetch('Typ__Konkordanz', queryset=concordances, to_attr='nomisma_concordances'),
        )
        .order_by('id')
    )


def get_nomisma_export_queryset(slg):
    """Kontrollierte, als echt geltende Objekte mit ihren möglichen Typ-Links."""
    return (
        _objects_with_type_links(slg)
        .select_related('Slg', 'SlgTeil', 'SlgTeil__idfk_Slg_SlgTeil')
        .prefetch_related(
            Prefetch('pakete', queryset=Paket.objects.filter(online_freigegeben=True).exclude(slug__isnull=True)
                     .exclude(slug='').filter(kontexttyp__in=(Paket.KONTEXTTYP_HORTFUND, Paket.KONTEXTTYP_FUNDKONTEXT))),
        )
    )


def type_series_item_uri(obj):
    """Direkter Typ-Link, exaktes Objektzitat oder eindeutige numismatics.org-Konkordanz."""
    typ = obj.Typ
    if typ and not typ.nach and is_type_series_uri(typ.link):
        return typ.link
    for ref in obj.obj_ref_set.all():
        if not ref.nach and is_type_series_uri(ref.link):
            return ref.link
    if not typ or typ.nach:
        return None
    concordance_types = {}
    for concordance in typ.nomisma_concordances:
        if is_type_series_uri(concordance.link):
            parsed = urlsplit(concordance.link)
            host = (parsed.hostname or '').lower()
            if host == NUMISMATICS_HOST or host.endswith('.' + NUMISMATICS_HOST):
                canonical_host = host[4:] if host.startswith('www.') else host
                concordance_types.setdefault((canonical_host, parsed.path.rstrip('/')), concordance.link)
    if len(concordance_types) == 1:
        return next(iter(concordance_types.values()))
    return None


def count_exportable(slg):
    """Anzahl der Münzen mit demselben Typ-Link-Kriterium wie im Dump."""
    objects = _objects_with_type_links(slg).only('pk', 'Typ_id', 'Typ__link', 'Typ__nach')
    return sum(bool(type_series_item_uri(obj)) for obj in objects.iterator(chunk_size=CHUNK_SIZE))


def nomisma_readiness(slg, *, exportable_count=None):
    issues = []
    if not valid_uri(slg.nomisma_collection_uri):
        issues.append('Nomisma-Collection-URI fehlt (bei Nomisma beantragen, z. B. http://nomisma.org/id/…)')
    if not metadata_rights_uri(slg):
        issues.append('Metadatenrechte-URI fehlt – Nomisma verlangt eine Lizenz (üblich: CC0)')
    if exportable_count is None:
        exportable_count = count_exportable(slg)
    if not exportable_count:
        issues.append('Keine exportierbaren Münzen (kontrolliert, mit Link auf OCRE/CRRO-Typ o. Ä.)')
    return issues


# ---------------------------------------------------------------------------
# URIs

def dataset_uri(request, slg):
    return absolute_uri(request, slg.get_absolute_url())


def dump_uri(request, slg):
    return absolute_uri(request, reverse('collection_nomisma_rdf', kwargs={'id': slg.id}))


def void_uri(request, slg):
    return absolute_uri(request, reverse('collection_nomisma_void', kwargs={'id': slg.id}))


def _paket_uri(request, paket):
    return absolute_uri(request, reverse('paket_detail', kwargs={'slug': paket.slug}))


# ---------------------------------------------------------------------------
# RDF/XML-Schreiber (gestreamt, damit auch große Sammlungen wenig Speicher brauchen)

def _text(value):
    return escape(clean_text(value))


def _literal(prop, value, lang=None, datatype=None):
    text = clean_text(value)
    if not text:
        return ''
    attrs = (f' xml:lang={quoteattr(lang)}' if lang else '') + (f' rdf:datatype={quoteattr(XSD + datatype)}' if datatype else '')
    return f'<{prop}{attrs}>{escape(text)}</{prop}>'


def _resource(prop, uri):
    return f'<{prop} rdf:resource={quoteattr(uri)}/>' if uri else ''


def _node(kind, uri, *properties):
    body = ''.join(p for p in properties if p)
    return f'<{kind} rdf:about={quoteattr(uri)}>{body}</{kind}>\n'


def _header():
    declarations = ' '.join(f'xmlns:{prefix}={quoteattr(uri)}' for prefix, uri in NAMESPACES.items())
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<rdf:RDF {declarations}>\n'


FOOTER = '</rdf:RDF>\n'


def collection_title(slg):
    return f'Eligius – {slg.name}'


def collection_description(slg):
    text = clean_text(slg.beschreibung)
    if len(text) > 2000:
        text = text[:1999].rsplit(' ', 1)[0] + '…'
    return text or f'Münzen der Sammlung {slg.name}, digital erschlossen in Eligius.'


def void_dataset(request, slg, entities=None):
    licence = metadata_rights_uri(slg)
    return _node(
        'void:Dataset', dataset_uri(request, slg),
        _literal('dcterms:title', collection_title(slg), 'de'),
        _literal('dcterms:description', collection_description(slg), 'de'),
        _literal('dcterms:publisher', slg.name),
        _resource('dcterms:license', licence),
        _resource('foaf:homepage', dataset_uri(request, slg)),
        _literal('void:uriSpace', absolute_uri(request, '/objekt/')),
        _resource('void:dataDump', dump_uri(request, slg)),
        _literal('dcterms:modified', date.today().isoformat(), datatype='date'),
        _literal('void:entities', entities, datatype='integer') if entities is not None else '',
    )


def serialize_collection_void(slg, request):
    return _header() + void_dataset(request, slg) + FOOTER


# Stabile Ansicht der Bild-Weiterleitung -> Schlüssel aus Obj.get_bild_urls().
IMAGE_KEYS = {'av': 'av', 'rv': 'rv', 'av-vorschau': 'thumbnail_av', 'rv-vorschau': 'thumbnail_rv'}
# Wie slg.oai.edm.source_images: Leerzeichen etc. in Inventarnummern kodieren,
# bereits kodierte Zeichen (%) unverändert lassen.
URI_SAFE = ":/?#[]@!$&'()*+,;=%"


def _file_uri(request, source):
    if not source:
        return None
    return valid_uri(quote(absolute_uri(request, source), safe=URI_SAFE))


def _image_uri(obj, request, variant, source):
    file_uri = _file_uri(request, source)
    if not file_uri:
        return None
    return image_redirect_uri(request, obj.id, variant) or file_uri


def nomisma_image_target(obj_id, variant, request):
    """Bilddatei für /bild/<id>/<ansicht>/, sofern das Objekt im Nomisma-Export steht.

    Die Bild-Weiterleitung prüft sonst nur die Kulturpool-Freigabe; Sammlungen
    mit Nomisma- aber ohne Kulturpool-Freigabe hätten dann nur 404-Bildlinks.
    Gleiche Kriterien wie iter_collection_rdf, Rückseite ohne Deduplizierung.
    """
    key = IMAGE_KEYS.get(variant)
    if not key:
        return None
    slg_id = Obj.objects.filter(pk=obj_id, Slg__nomisma_export_erlaubt=True).values_list('Slg_id', flat=True).first()
    if slg_id is None:
        return None
    obj = get_nomisma_export_queryset(slg_id).filter(pk=obj_id).first()
    if obj is None or not type_series_item_uri(obj):
        return None
    return _file_uri(request, (obj.get_bild_urls() or {}).get(key))


def _side(obj, request, uri, urls, side):
    depiction = _image_uri(obj, request, side, urls.get(side))
    thumbnail = _image_uri(obj, request, f'{side}-vorschau', urls.get(f'thumbnail_{side}'))
    if not (depiction or thumbnail):
        return None, ''
    return uri, _node('rdf:Description', uri, _resource('foaf:thumbnail', thumbnail),
                      _resource('foaf:depiction', depiction))


def _findspot(request, paket):
    """nmo:Find mit Ort (Paket-Titel, optional Koordinaten) – ein Knoten je Paket."""
    base = _paket_uri(request, paket)
    label = paket.titel_oeffentlich or paket.name
    place = ''
    if paket.fund_lat is not None and paket.fund_lng is not None:
        lat, lng = f'{paket.fund_lat:f}', f'{paket.fund_lng:f}'
        place = (
            f'<geo:location><geo:SpatialThing>{_literal("geo:lat", lat, datatype="decimal")}'
            f'{_literal("geo:long", lng, datatype="decimal")}</geo:SpatialThing></geo:location>'
        )
    return _node(
        'nmo:Find', base + '#find',
        _literal('rdfs:label', label, 'de'),
        f'<crm:P7_took_place_at><crm:E53_Place rdf:about={quoteattr(base + "#place")}>'
        f'{_literal("rdfs:label", label, "de")}{place}</crm:E53_Place></crm:P7_took_place_at>',
    )


def _hoard(request, paket, dataset):
    base = _paket_uri(request, paket)
    return _node(
        'nmo:Hoard', base + '#hoard',
        _literal('dcterms:title', paket.titel_oeffentlich or paket.name, 'de'),
        _literal('dcterms:identifier', paket.slug),
        _resource('nmo:hasFindspot', base + '#find'),
        _resource('void:inDataset', dataset),
    )


def _titles(objects):
    """Titel wie im Kulturpool-Export (MTOA-Projektion), seitenweise geladen."""
    rows = (MuenztypObjektAnzeige.objects.filter(obj_id__in=[o.id for o in objects])
            .select_related('nominal_fk', 'objekttyp_fk')
            .prefetch_related(Prefetch('mtoaperson_set', queryset=MtoaPerson.objects.select_related('person')))
            .order_by('obj_id', '-pk'))
    titles = {}
    for row in rows:
        titles.setdefault(row.obj_id, record_title(row))
    return titles


def iter_collection_rdf(slg, request):
    """RDF/XML als Folge von Textstücken; ``stats`` wird am Ende befüllt."""
    dataset = dataset_uri(request, slg)
    collection = valid_uri(slg.nomisma_collection_uri)
    yield _header()
    yield void_dataset(request, slg)
    seen_pakete = set()
    chunk = []

    def render(objects):
        titles = _titles(objects)
        parts = []
        for obj in objects:
            type_uri = type_series_item_uri(obj)
            if not type_uri:
                continue
            uri = absolute_uri(request, obj.get_absolute_url())
            urls = obj.get_bild_urls() or {}
            obverse, obverse_node = _side(obj, request, uri + '#obverse', urls, 'av')
            reverse_, reverse_node = _side(obj, request, uri + '#reverse', urls, 'rv')
            context = []
            for paket in obj.pakete.all():
                paket_base = _paket_uri(request, paket)
                if paket.kontexttyp == Paket.KONTEXTTYP_HORTFUND:
                    context.append(_resource('dcterms:isPartOf', paket_base + '#hoard'))
                else:
                    context.append(_resource('nmo:hasFindspot', paket_base + '#find'))
                if paket.pk not in seen_pakete:
                    seen_pakete.add(paket.pk)
                    parts.append(_findspot(request, paket))
                    if paket.kontexttyp == Paket.KONTEXTTYP_HORTFUND:
                        parts.append(_hoard(request, paket, dataset))
            axis = obj.stempelstellung if obj.stempelstellung in range(1, 13) else None
            parts.append(_node(
                'nmo:NumismaticObject', uri,
                _literal('dcterms:title', titles.get(obj.id) or obj.titel or (obj.Typ.titel if obj.Typ else '')
                         or f'{slg.name} {obj.invnr}', 'de'),
                _literal('dcterms:identifier', obj.invnr),
                _literal('dcterms:publisher', slg.name),
                _resource('nmo:hasCollection', collection),
                _resource('nmo:hasTypeSeriesItem', type_uri),
                _literal('nmo:hasAxis', axis, datatype='integer'),
                _literal('nmo:hasDiameter', obj.durchmesser, datatype='decimal'),
                _literal('nmo:hasWeight', obj.gewicht, datatype='decimal'),
                *context,
                _resource('nmo:hasObverse', obverse),
                _resource('nmo:hasReverse', reverse_),
                _resource('void:inDataset', dataset),
            ))
            parts.append(obverse_node)
            parts.append(reverse_node)
        return ''.join(parts)

    for obj in get_nomisma_export_queryset(slg).iterator(chunk_size=CHUNK_SIZE):
        chunk.append(obj)
        if len(chunk) >= CHUNK_SIZE:
            yield render(chunk)
            chunk = []
    if chunk:
        yield render(chunk)
    yield FOOTER


def serialize_collection_nomisma_rdf(slg, request):
    return ''.join(iter_collection_rdf(slg, request))


# ---------------------------------------------------------------------------
# Dateicache: Große Sammlungen nicht bei jedem Abruf neu erzeugen

def cache_path(slg):
    if not getattr(settings, 'ELIGIUS_PUBLIC_BASE_URL', ''):
        return None  # Ohne feste Basis-URL hinge der Inhalt vom Host des Requests ab.
    directory = Path(getattr(settings, 'ELIGIUS_NOMISMA_CACHE_DIR', Path(tempfile.gettempdir()) / 'eligius-nomisma'))
    return directory / f'collection-{slg.id}.rdf'


def _discard(tmp):
    try:
        os.unlink(tmp)
    except OSError:
        pass


def cached_dump(slg, request, max_age=None, force=False):
    """Pfad zu einer aktuellen Dump-Datei; erzeugt sie bei Bedarf atomar neu.

    Gibt ``None`` zurück, wenn kein Cache möglich ist (keine Basis-URL oder
    Verzeichnis nicht beschreibbar) – dann direkt ausliefern.
    """
    path = cache_path(slg)
    if path is None:
        return None
    max_age = getattr(settings, 'ELIGIUS_NOMISMA_CACHE_SECONDS', 6 * 3600) if max_age is None else max_age
    def fresh():
        return path.exists() and time.time() - path.stat().st_mtime < max_age

    try:
        if not force and fresh():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = open(path.with_name(path.name + '.lock'), 'a+')
    except OSError:
        return None
    with lock:
        # Ein Rebuild pro Datei: parallele Anfragen warten und nutzen danach das
        # frisch geschriebene Ergebnis statt selbst neu zu bauen.
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass  # Windows-Entwicklung: ohne Lock weiter
        try:
            if not force and fresh():
                return path
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix='.tmp')
        except OSError:
            return None
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                for part in iter_collection_rdf(slg, request):
                    handle.write(part)
            os.replace(tmp, path)
        except OSError:
            # Speicher voll, Dateisperre o. Ä.: direkt ausliefern statt HTTP 500.
            _discard(tmp)
            return None
        except BaseException:
            _discard(tmp)
            raise
    return path
