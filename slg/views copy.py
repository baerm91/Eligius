from django.shortcuts import render #, get_object_or_404
from .models import Slg, Obj, Obj_Person, PersonFunktion, Person, Mzstaette
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Prefetch, Q, Count
from rest_framework import viewsets
from .serializers import MzstaettenSerializer
from .forms import SearchForm

# Create your views here.
def index(request):
   
   queryset = Obj.objects.defer('anmerkung', 'avleg', 'rvleg', 'avbeschr', 'rvbeschr', 'idfk_Muenzstand', 'idfk_Herstellung', 'idfk_SlgTeil', 'idfk_Nominal', 'idfk_Mzstaette').order_by('?')[:24]
   context = {
      'Objekte': queryset
   }

   return render(request, 'slg/index.html', context)

def dynamic_lookup_view(request, id):
   obj = Obj.objects.select_related('idfk_Muenzstand', 'idfk_Herstellung', 'idfk_SlgTeil', 'idfk_Nominal', 'idfk_Mzstaette').prefetch_related('Ppl').get(id=id)
   context = {
      'test': obj,
   }
   
   return render(request, 'slg/details.html', context)
def is_valid_qparam(param):
   return param != '' and param is not None

def objekt_list_view(request):
   # queryset = Obj.objects.all().order_by('?')[:18]
   qs = Obj.objects.all().order_by('dat_von','dat_bis').select_related('idfk_Mzstaette', 'idfk_Muenzstand',).prefetch_related('Ppl', 'idfk_Ref')
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
   q = request.GET.get('q')
   mstand = request.GET.get('mstand')
   mint = request.GET.get('mint')
   nom = request.GET.get('nom')
   lit = request.GET.getlist('lit')
   von = request.GET.get('fromdate')
   bis = request.GET.get('todate')
   person = request.GET.getlist('person')

   print(request.GET)
   form = SearchForm(initial=request.GET)
   if is_valid_qparam(q):
      qs = qs.filter(titel__icontains=q)
   elif is_valid_qparam(mstand):
      qs = qs.filter(idfk_Muenzstand__name__icontains=mstand)
   # elif is_valid_qparam(mint):
   
   if is_valid_qparam(mint):
      qs = qs.filter(idfk_Mzstaette__name__icontains=mint)
      form.fields["idfk_Mzstaette"].queryset = Mzstaette.objects.filter(name__icontains=request.GET.get('mint'))
   # else:
   #    form.fields["idfk_Mzstaette"].queryset = qs.values_list('idfk_Mzstaette__name', flat=True).distinct().exclude(idfk_Mzstaette__name=None).order_by('idfk_Mzstaette__name')


   if is_valid_qparam(nom):
      qs = qs.filter(idfk_Nominal__name__icontains=nom)
   if is_valid_qparam(von):
      qs = qs.filter(dat_von__gte=von)
   if is_valid_qparam(bis):
      qs = qs.filter(dat_bis__lte=bis)
   if person != []:
      qs = qs.filter(Ppl__name__in=person).distinct()
   if lit != []:
      qs = qs.filter(idfk_Ref__abk__in=lit).distinct()
      #print(person)
   
   #form.fields["photos"].queryset = Photo.objects.filter(user=request.user)
   if not is_valid_qparam(mint):
      form.fields["idfk_Mzstaette"].queryset = qs.values_list('idfk_Mzstaette__name', flat=True).distinct().exclude(idfk_Mzstaette__name=None).order_by('idfk_Mzstaette__name')

   nominale = qs.values_list('idfk_Nominal__name', flat=True).distinct().exclude(idfk_Nominal__name=None).order_by('idfk_Nominal__name')
   personen = qs.values_list('Ppl__name', flat=True).distinct().exclude(Ppl__name=None).order_by('Ppl__name')
   lit = qs.values_list('idfk_Ref__abk', flat=True).distinct().order_by('idfk_Ref__abk')
   # lit = qs.values_list('idfk_Ref__abk', flat=True).distinct().exclude(idfk_Ref__abk=None).order_by('idfk_Ref__abk')
   mints = qs.values_list('idfk_Mzstaette__name', flat=True).distinct().exclude(idfk_Mzstaette__name=None).order_by('idfk_Mzstaette__name')
   anzahl = qs.count()
   print(anzahl)
   #personen = qs.prefetch_related('Ppl').distinct()
   #for i in qs:
   #   personen = qs.distinct()
   #personen = Obj.ppl_set.all()
   page = request.GET.get('page', 1)
   paginator = Paginator(qs, 6)
   variables = request.GET.copy()
   if 'page' in variables:
        del variables['page']
   print(variables)
   try:
        qs = paginator.page(page)
   except PageNotAnInteger:
        qs = paginator.page(1)
   except EmptyPage:
        qs = paginator.page(paginator.num_pages)
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
      'Nominale': nominale,
      'Mints': mints,
      'Literatur': lit,
      'Anzahl': anzahl,
      'getvars': '&{0}'.format(variables.urlencode()),
      'Form': form,
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