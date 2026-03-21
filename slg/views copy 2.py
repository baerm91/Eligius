from django.db import connection
from django.shortcuts import render , get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import UpdateView
from .models import Slg, Obj, Obj_Person, PersonFunktion, Person, Mzstaette, Metall, AvBildtyp, RvBildtyp
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Prefetch, Q, Count
from rest_framework import viewsets
from .serializers import MzstaettenSerializer, ObjSerializer
from .forms import SearchForm, DetailUpdateForm, PersonenUpdateForm
from django.core import serializers
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.forms import inlineformset_factory

from rdflib import Graph, Namespace, Literal
from rdflib.namespace import RDF, FOAF, DCTERMS, URIRef
from django.contrib import messages 


def MzUpdate(request, id):
   obj = Obj.objects.get(id=id)
   PersonFormSet = inlineformset_factory(Obj, Obj_Person, fields='__all__')
   formset = PersonFormSet(instance=obj)
   print(formset)
   form = DetailUpdateForm(instance=obj)
   if request.method == 'POST':
      print("erstes IF")
      print(request.POST)
      form = DetailUpdateForm(request.POST, instance=obj)
      if form.is_valid():
         print("zweites IF")
         form.save()
         return HttpResponseRedirect(request.path_info)
      else:
         print(form.errors)
   avtype = AvBildtyp.objects.all().order_by('name')
   rvtype = RvBildtyp.objects.all().order_by('name')
   
   
   context = {
      'form': form,
      'formset': formset,
      'test': obj,
      'Avtypes': avtype,
      'Rvtypes': rvtype,
   }

   
      # if form.is_valid():
      #    form.save()
         #return redirect('/')
   # def form_valid(self, form):
   #    print(form.cleaned_data)
   #    return super().form_valid(form)

   # def get_object(self):
   #    id_ = self.kwargs.get("id")
   #    return get_object_or_404(Obj, id=id_)

   return render(request, 'slg/obj_form.html', context)

def index(request):
   
   queryset = Obj.objects.defer('anmerkung', 'avleg', 'rvleg', 'avbeschr', 'rvbeschr', 'idfk_Muenzstand', 'idfk_Herstellung', 'SlgTeil', 'idfk_Nominal', 'idfk_Mzstaette').order_by('?')[:24]
   context = {
      'Objekte': queryset
   }

   return render(request, 'slg/index.html', context)

def dynamic_lookup_view(request, id):
   obj = Obj.objects.select_related('idfk_Muenzstand', 'idfk_Herstellung', 'Slg', 'idfk_Nominal', 'idfk_Mzstaette', 'Metall',).prefetch_related('Ppl').get(id=id)
   context = {
      'test': obj,
   }
   
   return render(request, 'slg/details.html', context)

def is_valid_qparam(param):
   return param != '' and param is not None

def objekt_list_view(request):
   # queryset = Obj.objects.all().order_by('?')[:18]
   print(request.GET)
   if request.GET:
      print(request.GET)
      qs = Obj.objects.all().select_related('SlgTeil', 'Slg').prefetch_related('Ppl', 'idfk_Ref',)
   else:
      qs = Obj.objects.all().select_related('SlgTeil', 'Slg').prefetch_related('Ppl', 'idfk_Ref',).order_by('?')

   
   # qs = Obj.objects.all().select_related('SlgTeil', 'Slg').prefetch_related('Ppl', 'idfk_Ref',).order_by('?').distinct()
   #qs = Obj.objects.all().order_by('dat_von','dat_bis').select_related('idfk_Mzstaette', 'idfk_Muenzstand',).prefetch_related('Ppl', 'idfk_Ref')
   #personen = Person.objects.all()
   #personen = qs.values('Person')
   #personen = [p.Ppl for p in qs]

   #anzahl = Obj.objects.all().order_by('dat_von','dat_bis').select_related('idfk_Mzstaette', 'idfk_Muenzstand',).prefetch_related('idfk_Person', ).count()
   # Obj_and_Persons = Obj_Person.objects.select_related('idfk_Person')
   # qs = Obj.objects.all().order_by('dat_von','dat_bis').select_related('idfk_Mzstaette', 'idfk_Muenzstand',).prefetch_related(Prefetch('Ppl', queryset=Obj_and_Persons))
   # personen = [p.idfk_Person.name for p in qs.idfk_Person]
      
   #personen = [p.idfk_Person.name for p in qs.Ppl.all()]
   #print(personen)
   #persons = qs.general_persons
   #personen = [info.idfk_Person.name for info in Obj.obj_person_set]
   #qs = Obj.objects.all()
   #print(personen)
   q = request.GET.getlist('q')
   num = request.GET.getlist('num')
   #print(num)
   # if q:
   #    q = q.split(", ")
   # else:
   #    q = []
   #print(q)
   #data = q.split("%2C+")
   #print(data)
   mstand = request.GET.get('mstand')
   mint = request.GET.getlist('mint')
   region = request.GET.getlist('region')
   slg = request.GET.getlist('slg')
   #print(mint)
   # mint = request.GET.get('mint')
   nom = request.GET.getlist('idfk_Nominal')
   material = request.GET.getlist('material')
   av_bildtyp = request.GET.getlist('av_bildtyp')
   av_beizeichen = request.GET.getlist('av_beizeichen')
   rv_bildtyp = request.GET.getlist('rv_bildtyp')
   rv_beizeichen = request.GET.getlist('rv_beizeichen')
   
   lit = request.GET.getlist('idfk_Ref')
   von = request.GET.get('dat_von')
   bis = request.GET.get('dat_bis')
   person = request.GET.getlist('Ppl')
   #print(person)
   excl_person = request.GET.getlist('excl_ppl')
   avbeschreibungen = request.GET.getlist('avbeschr')
   excl_avbeschreibungen = request.GET.getlist('excl_avbeschr')
   avleg = request.GET.getlist('avleg')
   excl_avleg = request.GET.getlist('excl_avleg')
   rvleg = request.GET.getlist('rvleg')
   excl_rvleg = request.GET.getlist('excl_rvleg')
   rvbeschreibungen = request.GET.getlist('rvbeschr')
   excl_rvbeschreibungen = request.GET.getlist('excl_rvbeschr')


   #form = SearchForm(initial=request.GET)
   if q != [] and not q != "":
      qs = qs.filter(Q(titel__in=q) | Q(invnr__in=q) )
   if is_valid_qparam(mstand):
      qs = qs.filter(idfk_Muenzstand__name__icontains=mstand)

   if num != []:
      qs = qs.filter(Q(idfk_Ref__obj_ref__nummer__in=num))
      #print (qs.query)
   # elif is_valid_qparam(mint):
   #anzahl = qs.count()
   
   #if not is_valid_qparam(mint):
   #Wenn die Suche aktiv, dann soll Queryset gefiltert werden
   # if person != []:
   #    qs = qs.filter(Ppl__name__in=person)
   for ppl in person:
      if is_valid_qparam(ppl):
         qs = qs.filter(Ppl__name__exact=ppl)
   for ppl in excl_person:
      if is_valid_qparam(ppl):
         qs = qs.exclude(Ppl__name__exact=ppl)
   
   #print(mint)

   if mint != []:
      qs = qs.filter(idfk_Mzstaette__name__in=mint)
   
   if region != []:
      qs = qs.filter(idfk_Mzstaette__region__in=region)
      #print(qs)
   if nom != []:
      qs = qs.filter(idfk_Nominal__name__in=nom)
   if material != []:
      qs = qs.filter(Metall__name__in=material)
   if is_valid_qparam(von):
      qs = qs.filter(dat_von__gte=von)
      #print(von)
      #von = int(von)
      #print(von)
      #form.fields["dat_von"].initial = int(von)
   if is_valid_qparam(bis):
      qs = qs.filter(dat_bis__lte=bis)
      #form.fields["dat_bis"].initial = bis

   for avleg in avleg:
      if is_valid_qparam(avleg):
         qs = qs.filter(avleg__icontains=avleg)
   for avleg in excl_avleg:
      if is_valid_qparam(avleg):
         qs = qs.exclude(avleg__icontains=avleg)
   for avbe in avbeschreibungen:
      if is_valid_qparam(avbe):
         qs = qs.filter(avbeschr__icontains=avbe)
   for avbe in excl_avbeschreibungen:
      if is_valid_qparam(avbe):
         qs = qs.exclude(avbeschr__icontains=avbe)

   for rvleg in rvleg:
      if is_valid_qparam(rvleg):
         qs = qs.filter(rvleg__icontains=rvleg)
   for rvleg in excl_rvleg:
      if is_valid_qparam(rvleg):
         qs = qs.exclude(rvleg__icontains=rvleg)
   for rvbe in rvbeschreibungen:
      if is_valid_qparam(rvbe):
         qs = qs.filter(rvbeschr__icontains=rvbe)
   for rvbe in excl_rvbeschreibungen:
      if is_valid_qparam(rvbe):
         qs = qs.exclude(rvbeschr__icontains=rvbe)

   if slg != []:
      qs = qs.filter(Slg_id__in=slg)
   if lit != []:
      qs = qs.filter(idfk_Ref__abk__in=lit)
   if av_bildtyp != []:
      qs = qs.filter(av_bildtyp_id__in=av_bildtyp)
   if rv_bildtyp != []:
      qs = qs.filter(rv_bildtyp_id__in=rv_bildtyp)
   if av_beizeichen != []:
      qs = qs.filter(av_beizeichen_id__in=av_beizeichen)
   if rv_beizeichen != []:
      qs = qs.filter(rv_beizeichen_id__in=rv_beizeichen)
      
   #personen = qs.Ppl.obj_person_set.all()
   # personen = qs.values('Ppl__name',).exclude(Ppl__name=None).annotate(cc=Count('Ppl'))
   personen = qs.values('Ppl__name', 'Ppl__obj_person__idfk_PersonFunktion__name').exclude(Ppl__name=None).annotate(cc=Count('Ppl')).order_by('Ppl__obj_person__idfk_PersonFunktion__name')
   #print([p.Obj_Person for p in qs])
   print(personen.values)
   qs = qs.distinct()
      #form.fields["idfk_Mzstaette"].queryset = Mzstaette.objects.filter(name__icontains=request.GET.get('idfk_Mzstaette'))
   # else:
   #    form.fields["idfk_Mzstaette"].queryset = qs.values_list('idfk_Mzstaette__name', flat=True).distinct().exclude(idfk_Mzstaette__name=None).order_by('idfk_Mzstaette__name')

   #Select2-Filter für das Dropdownfeld im Suchformular
   mints = qs.values('idfk_Mzstaette__name', 'idfk_Mzstaette__region__name').exclude(idfk_Mzstaette__name=None).annotate(cc=Count('idfk_Mzstaette__name')).order_by('idfk_Mzstaette__region__name', 'idfk_Mzstaette__name')
   regions = mints.values('idfk_Mzstaette__region__name').exclude(idfk_Mzstaette__region__name=None).annotate(cc=Count('idfk_Mzstaette__region__name')).order_by('idfk_Mzstaette__region__name')

   #objpers = qs.values_list('obj_person')#.annotate(cc=Count('Ppl__name'))
   prollen = personen.values('Ppl__obj_person__idfk_PersonFunktion__name').annotate(cc=Count('Ppl__obj_person__idfk_PersonFunktion__name')).order_by('Ppl__obj_person__idfk_PersonFunktion__name')
   # prollen = personen.values('Ppl__obj_person__idfk_PersonFunktion__name').annotate(cc=Count('Ppl__obj_person__idfk_PersonFunktion__name')).order_by('Ppl__obj_person__idfk_PersonFunktion__name')
   #print(personen)

   nominale = qs.values('idfk_Nominal__name').exclude(idfk_Nominal__name=None).annotate(cc=Count('idfk_Nominal__name')).order_by('idfk_Nominal__name')
   lit = qs.values('idfk_Ref__abk').exclude(idfk_Ref__abk=None).annotate(cc=Count('idfk_Ref__abk')).order_by('idfk_Ref__abk')
   slgen = qs.values('Slg__id', 'Slg__name').exclude(Slg=None).annotate(cc=Count('Slg')).order_by('Slg__name')
   avtype = qs.values('av_bildtyp__id', 'av_bildtyp__name').exclude(av_bildtyp=None).annotate(cc=Count('av_bildtyp')).order_by('av_bildtyp__name')
   rvtype = qs.values('rv_bildtyp__id', 'rv_bildtyp__name').exclude(rv_bildtyp=None).annotate(cc=Count('rv_bildtyp')).order_by('rv_bildtyp__name')
   #print(rvtype)
   # lit = qs.values_list('idfk_Ref__abk', flat=True).distinct().exclude(idfk_Ref__abk=None).order_by('idfk_Ref__abk')
   #form.fields["idfk_Ref"].required = False
   
   #form.fields["dat_von"].required = False
  
   #nominale = qs.values_list('idfk_Nominal__name', flat=True).distinct().exclude(idfk_Nominal__name=None).order_by('idfk_Nominal__name')
   #personen = qs.values_list('Ppl__name', flat=True).distinct().exclude(Ppl__name=None).order_by('Ppl__name')
   #lit = qs.values_list('idfk_Ref__abk', flat=True).distinct().order_by('idfk_Ref__abk')
   # lit = qs.values_list('idfk_Ref__abk', flat=True).distinct().exclude(idfk_Ref__abk=None).order_by('idfk_Ref__abk')
   #mints = qs.values_list('idfk_Mzstaette__name', flat=True).distinct().exclude(idfk_Mzstaette__name=None).order_by('idfk_Mzstaette__name')
   #anzahl = qs.count()
   #print(anzahl)
   #personen = qs.prefetch_related('Ppl').distinct()
   #for i in qs:
   #   personen = qs.distinct()
   #personen = Obj.ppl_set.all()
   page = request.GET.get('page', 1)
   paginator = Paginator(qs, 12)
   anzahl = paginator.count
   variables = request.GET.copy()
   if 'page' in variables:
        del variables['page']
   #print(variables)
   try:
        qs = paginator.page(page)
   except PageNotAnInteger:
        qs = paginator.page(1)
   except EmptyPage:
        qs = paginator.page(paginator.num_pages)
   #print("Personen:{}".format(person))
   #print(numbers)
   # try:
   #       qs = paginator.page(page)
   # except PageNotAnInteger:
   #       qs = paginator.page(1)
   # except EmptyPage:
   #       qs = paginator.page(paginator.num_pages)

   
   
   #print(personen)
   #qs = paginator.get_page(page)
   
   context = {
      'Objekte': qs,
      'Personen': personen,
      'Personenrollen': prollen,
      'Nominale': nominale,
      'Mints': mints,
      'Regions': regions,
      'Literatur': lit,
      'Avtypes': avtype,
      'Rvtypes': rvtype,
      'Slgen': slgen,
      'Anzahl': anzahl,
      'getvars': '&{0}'.format(variables.urlencode()),
      #'Form': form,
      #'numbers': numbers,
   }

   return render(request, 'slg/Objektliste.html', context)

class MzstaettenRView(viewsets.ModelViewSet):
# class MzstaettenRView(generics.RetrieveUpdateDestroyAPIView):
    
    queryset         = Mzstaette.objects.all()
    serializer_class = MzstaettenSerializer
    

   #  def get_queryset(self):
   #      return Mzstaette.objects.all()
    
    # def get_object(self):
    #     id = self.kwargs.get("id")
    #     return Mzstaette.objects.get(id=id)

def jsonresp(request, id):
   # obj = Obj.objects.select_related('idfk_Muenzstand', 'idfk_Herstellung', 'idfk_SlgTeil', 'idfk_Nominal', 'idfk_Mzstaette').prefetch_related('Ppl').get(id=id)
   obj = Obj.objects.get(pk=id)
   serializer = ObjSerializer(obj)
   return JsonResponse(serializer.data)
   #data = serializers.serialize(obj, many=True).data
   # data = serializers.serialize('json', Obj.objects.filter(pk=id))
   # obj = serializers.serialize('json', obj)
   #return HttpResponse(obj, content_type="application/json")

def rdfliboutput(request, id):
   
   obj = Obj.objects.get(pk=id)
   print(request.build_absolute_uri)
   uri = URIRef('http://127.0.0.1:8000/slg/150')
   uriobv = URIRef('http://127.0.0.1:8000/slg/150#obverse')
   urirev = URIRef('http://127.0.0.1:8000/slg/150#reverse')
   # uri = URIRef(obj.get_absolute_url)
   titel = Literal(obj.titel)
   invnr = Literal(obj.invnr)
   slgteil = Literal(obj.SlgTeil)
   stempelstellung = Literal(obj.stempelstellung)
   durchmesser = Literal(obj.durchmesser)
   nmo = Namespace("http://nomisma.org/ontology#")
   dcterms = Namespace(DCTERMS)
   
   g = Graph()
   g.bind('nmo',nmo)
   g.bind('dcterms', dcterms)
   g.add( (uri, dcterms.title, titel) )
   g.add( (uri, dcterms.identifier, invnr) )
   g.add( (uri, nmo.hasCollection, slgteil) )
   g.add( (uri, nmo.hasAxis, stempelstellung) )
   g.add( (uri, nmo.hasDiameter, durchmesser) )
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