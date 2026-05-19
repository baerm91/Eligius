from urllib.parse import urlparse

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, FOAF, RDF, XSD

from .models import Obj, Obj_Ref


NMO = Namespace("http://nomisma.org/ontology#")
VOID = Namespace("http://rdfs.org/ns/void#")
NUMISMATICS_DOMAIN = "numismatics.org"
CONTROLLED_WORKFLOW_NAME = "kontrolliert"


def get_nomisma_export_queryset(slg):
    return (
        Obj.objects.filter(
            Slg=slg,
            workflow__name__iexact=CONTROLLED_WORKFLOW_NAME,
            Typ__workflow__name__iexact=CONTROLLED_WORKFLOW_NAME,
        )
        .exclude(obj_ref_set__nach=True)
        .select_related("Slg", "SlgTeil", "Typ", "workflow", "Typ__workflow")
        .prefetch_related("obj_ref_set")
        .distinct()
        .order_by("invnr", "id")
    )


def serialize_collection_nomisma_rdf(slg, request):
    graph = Graph()
    graph.bind("rdf", RDF)
    graph.bind("dcterms", DCTERMS)
    graph.bind("void", VOID)
    graph.bind("nmo", NMO)
    graph.bind("foaf", FOAF)
    graph.bind("xsd", XSD)

    dataset_uri = URIRef(request.build_absolute_uri(slg.get_absolute_url()))

    for obj in get_nomisma_export_queryset(slg):
        _add_object(graph, obj, slg, request, dataset_uri)

    return graph.serialize(format="xml")


def _add_object(graph, obj, slg, request, dataset_uri):
    object_uri = URIRef(request.build_absolute_uri(obj.get_absolute_url()))
    obverse_uri = URIRef(f"{object_uri}#obverse")
    reverse_uri = URIRef(f"{object_uri}#reverse")

    graph.add((object_uri, RDF.type, NMO.NumismaticObject))

    title = _object_title(obj)
    if title:
        graph.add((object_uri, DCTERMS.title, Literal(title)))

    if obj.invnr:
        graph.add((object_uri, DCTERMS.identifier, Literal(obj.invnr)))

    if slg.nomisma_collection_uri:
        graph.add((object_uri, NMO.hasCollection, URIRef(slg.nomisma_collection_uri)))

    type_series_item = _type_series_item_uri(obj)
    if type_series_item:
        graph.add((object_uri, NMO.hasTypeSeriesItem, URIRef(type_series_item)))

    _add_typed_literal(graph, object_uri, NMO.hasAxis, obj.stempelstellung, XSD.integer)
    _add_typed_literal(graph, object_uri, NMO.hasDiameter, obj.durchmesser, XSD.decimal)
    _add_typed_literal(graph, object_uri, NMO.hasWeight, obj.gewicht, XSD.decimal)

    graph.add((object_uri, NMO.hasObverse, obverse_uri))
    graph.add((object_uri, NMO.hasReverse, reverse_uri))
    graph.add((object_uri, VOID.inDataset, dataset_uri))

    _add_image_resources(graph, obj, request, obverse_uri, reverse_uri)


def _object_title(obj):
    if obj.Typ and obj.Typ.titel:
        return obj.Typ.titel
    return obj.titel


def _type_series_item_uri(obj):
    if obj.Typ and _is_numismatics_uri(obj.Typ.link):
        return obj.Typ.link

    for obj_ref in _obj_refs(obj):
        if _is_numismatics_uri(obj_ref.link):
            return obj_ref.link

    return None


def _obj_refs(obj):
    if hasattr(obj, "_prefetched_objects_cache") and "obj_ref_set" in obj._prefetched_objects_cache:
        return obj._prefetched_objects_cache["obj_ref_set"]
    return Obj_Ref.objects.filter(idfk_Obj=obj)


def _is_numismatics_uri(uri):
    if not uri:
        return False
    parsed = urlparse(uri)
    return parsed.scheme in {"http", "https"} and NUMISMATICS_DOMAIN in parsed.netloc


def _add_typed_literal(graph, subject, predicate, value, datatype):
    if value is None:
        return
    graph.add((subject, predicate, Literal(value, datatype=datatype)))


def _add_image_resources(graph, obj, request, obverse_uri, reverse_uri):
    bild_urls = obj.get_bild_urls() or {}

    _add_image_resource(
        graph,
        request,
        obverse_uri,
        depiction=bild_urls.get("av"),
        thumbnail=bild_urls.get("thumbnail_av"),
    )
    _add_image_resource(
        graph,
        request,
        reverse_uri,
        depiction=bild_urls.get("rv"),
        thumbnail=bild_urls.get("thumbnail_rv"),
    )


def _add_image_resource(graph, request, image_uri, depiction=None, thumbnail=None):
    if depiction:
        graph.add((image_uri, FOAF.depiction, URIRef(_absolute_uri(request, depiction))))
    if thumbnail:
        graph.add((image_uri, FOAF.thumbnail, URIRef(_absolute_uri(request, thumbnail))))


def _absolute_uri(request, uri):
    parsed = urlparse(uri)
    if parsed.scheme and parsed.netloc:
        return uri
    return request.build_absolute_uri(uri)
