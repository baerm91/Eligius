"""RDF and other machine-readable catalogue representations."""

from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import DCTERMS, URIRef

from ..models import Obj, Slg
from ..nomisma_rdf import (
   cached_dump as nomisma_cached_dump,
)
from ..nomisma_rdf import (
   serialize_collection_nomisma_rdf,
   serialize_collection_void,
)
from ..serializers import ObjSerializer


def jsonresp(request, id):
   # obj = Obj.objects.select_related('idfk_Muenzstand', 'idfk_Herstellung', 'idfk_SlgTeil', 'idfk_Nominal', 'idfk_Mzstaette').prefetch_related('Ppl').get(id=id)
   obj = get_object_or_404(Obj, pk=id)
   serializer = ObjSerializer(obj)
   return JsonResponse(serializer.data)
   #data = serializers.serialize(obj, many=True).data
   # data = serializers.serialize('json', Obj.objects.filter(pk=id))
   # obj = serializers.serialize('json', obj)
   #return HttpResponse(obj, content_type="application/json")

def rdfliboutput(request, id):

   from rdflib.namespace import XSD

   from ..models import stempelstellung_parts
   from ..oai.identifiers import object_uri

   obj = get_object_or_404(Obj.objects.select_related('SlgTeil'), pk=id)
   # Objekt-URI aus der öffentlichen Basis-URL bzw. dem Request, nicht mehr
   # hartcodiert auf http://127.0.0.1:8000/slg/150 für jedes Objekt.
   base = object_uri(request, obj.pk)
   uri = URIRef(base)
   uriobv = URIRef(base + '#obverse')
   urirev = URIRef(base + '#reverse')
   nmo = Namespace("http://nomisma.org/ontology#")
   dcterms = Namespace(DCTERMS)

   g = Graph()
   g.bind('nmo',nmo)
   g.bind('dcterms', dcterms)
   if obj.titel:
      g.add( (uri, dcterms.title, Literal(obj.titel)) )
   if obj.invnr:
      g.add( (uri, dcterms.identifier, Literal(obj.invnr)) )
   if obj.SlgTeil_id:
      g.add( (uri, nmo.hasCollection, Literal(str(obj.SlgTeil))) )
   axis, _axis_text = stempelstellung_parts(obj.stempelstellung)
   if axis is not None:
      g.add( (uri, nmo.hasAxis, Literal(axis, datatype=XSD.integer)) )
   if obj.durchmesser is not None:
      g.add( (uri, nmo.hasDiameter, Literal(obj.durchmesser, datatype=XSD.decimal)) )
   if obj.gewicht is not None:
      g.add( (uri, nmo.hasWeight, Literal(obj.gewicht, datatype=XSD.decimal)) )
   g.add( (uri, nmo.hasObverse, uriobv) )
   g.add( (uri, nmo.hasReverse, urirev) )
   # g.add( (uriobv, foaf.depiction, uriobv) )
   # g.add( (urirev, nmo.hasReverse, urirev) )

   # dcterms:identifier "2017.11.16";
	# nmo:hasCollection <http://nomisma.org/id/ans>;
	# nmo:hasAxis "12"^^<xsd:integer>;
	# nmo:hasWeight "25.59"^^xsd:decimal;
	# nmo:hasDiameter "32"^^xsd:decimal;
	# nmo:hasObverse <http://numismatics.org/collection/2017.11.16#obverse>;
	# nmo:hasReverse <http://numismatics.org/collection/2017.11.16#reverse>;
	# void:inDataset <http://numismatics.org/search/>.
   turt = g.serialize(format='turtle')
   return HttpResponse(content_type="text/turtle; charset=utf-8", content=turt)

def collection_nomisma_rdf(request, id):
   """Nomisma-Datendump einer Sammlung (nur mit gesetztem Nomisma-Häkchen)."""
   slg = get_object_or_404(Slg, pk=id, nomisma_export_erlaubt=True)
   content_type = "application/rdf+xml; charset=utf-8"
   path = nomisma_cached_dump(slg, request)
   if path is not None:
      response = FileResponse(open(path, 'rb'), content_type=content_type)
   else:
      response = HttpResponse(serialize_collection_nomisma_rdf(slg, request), content_type=content_type)
   response['Content-Disposition'] = f'inline; filename="eligius-collection-{slg.id}-nomisma.rdf"'
   return response


def collection_nomisma_void(request, id):
   """VoID-Beschreibung des Datensatzes – diese URL wird bei Nomisma registriert."""
   slg = get_object_or_404(Slg, pk=id, nomisma_export_erlaubt=True)
   return HttpResponse(serialize_collection_void(slg, request), content_type="application/rdf+xml; charset=utf-8")
