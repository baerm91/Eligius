from pickle import NONE
from urllib.request import Request
from django.core.checks import messages
from django.db import IntegrityError, transaction, models
from django.contrib import admin, messages
from django.contrib.admin.models import LogEntry, DELETION
from django.contrib.admin.utils import quote
from django.db.models.query import Prefetch, Q
from django.http import HttpResponse
from django.http.response import HttpResponseRedirect
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.utils.http import urlencode
from django.shortcuts import redirect
# Register your models here.
from .models import *
# from .models import Slg, Obj, SlgTeil, Person, PersonFunktion, Herstellung, Ref, Nominal, Mzstaette, Obj_Person, Obj_Ref, Muenzstand, Variantenbeschr, AvBildtyp, RvBildtyp, AvBeizeichen, RvBeizeichen, AvBildrand, RvBildrand, Workflow, Obj_interne_Anmerkung, interneAnmerkung, Schlagwort, AvBildtyp_Schlagwort, RvBildtyp_Schlagwort, Muenztyp, Mztyp_Person, Faelschung
from import_export.admin import ImportExportModelAdmin, ExportActionMixin, ImportExportActionModelAdmin
from import_export import resources, fields, widgets
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget
from django.db.models import Count
import urllib.request, json
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout, HTTPError
from django import forms
from django.forms import Textarea
import time
import urllib3
from django.conf import settings
# Disable SSL warnings when using verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from django_admin_listfilter_dropdown.filters import DropdownFilter, RelatedDropdownFilter, ChoiceDropdownFilter
from model_clone import CloneModelAdmin
import nested_admin
import adminactions.actions as actions
from django.contrib.admin import site
from urllib.parse import urlencode, urlparse, urlunparse, urljoin
import traceback
from rdflib import Graph, Namespace, URIRef, XSD, Literal
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from datetime import date
import textwrap

from rdflib.namespace import RDF, RDFS, SKOS

from bs4 import BeautifulSoup


#from core.models import Person

from import_export.results import Result, RowResult


def _is_admin_autocomplete_request(request):
    """Erkennt Requests vom Django-Admin-Autocomplete-Endpoint."""
    if request.path.endswith('/autocomplete/'):
        return True
    resolver_match = getattr(request, 'resolver_match', None)
    return bool(resolver_match and getattr(resolver_match, 'url_name', None) == 'autocomplete')


def _get_admin_autocomplete_cache_version(model):
    version_key = f"admin-autocomplete-version:{model._meta.label_lower}"
    version = cache.get(version_key)
    if version is None:
        version = 1
        cache.set(version_key, version, None)
    return version


def _bump_admin_autocomplete_cache_version(model):
    version_key = f"admin-autocomplete-version:{model._meta.label_lower}"
    version = cache.get(version_key)
    if version is None:
        cache.set(version_key, 2, None)
        return
    cache.set(version_key, version + 1, None)


class CachedAutocompleteAdminMixin:
    autocomplete_cache_timeout = 3600
    autocomplete_only_fields = ('id',)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if _is_admin_autocomplete_request(request):
            return queryset.only(*self.autocomplete_only_fields)
        return queryset

    def get_search_results(self, request, queryset, search_term):
        if not _is_admin_autocomplete_request(request):
            return super().get_search_results(request, queryset, search_term)

        normalized_term = ' '.join((search_term or '').split()).casefold()
        cache_key = (
            f"admin-autocomplete:{self.model._meta.label_lower}:"
            f"{_get_admin_autocomplete_cache_version(self.model)}:{normalized_term}"
        )
        cached_ids = cache.get(cache_key)
        if cached_ids is not None:
            return queryset.filter(pk__in=cached_ids), False

        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        cache.set(cache_key, list(queryset.values_list('pk', flat=True)), self.autocomplete_cache_timeout)
        return queryset, use_distinct

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _bump_admin_autocomplete_cache_version(self.model)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        _bump_admin_autocomplete_cache_version(self.model)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        _bump_admin_autocomplete_cache_version(self.model)


class ReichskreisView(ImportExportModelAdmin):
    search_fields = ('name',)
    list_display = ('id','name',)
    ordering = ['name']
    pass

class ObjekttypenView(ImportExportModelAdmin):
    search_fields = ('name',)
    list_display = ('id','name','name_nom_id')
    ordering = ['name']
    pass

class Sek_MerkmaleView(ImportExportModelAdmin):
    search_fields = ('name','name_nom_id')
    list_display = ('id','name','name_nom_id',)
    ordering = ['name']
    
    pass

class HerstellungsmerkmaleView(ImportExportModelAdmin):
    search_fields = ('name','name_nom_id')
    list_display = ('id','name','name_nom_id',)
    ordering = ['name']
    pass

class RefView(ImportExportModelAdmin):
    search_fields = ('abk','zitat')
    list_display = ('id', 'abk','zitat','name_nom_id',)
    actions = [actions.merge, actions.export_as_xls]
    pass

class NominalView(ImportExportModelAdmin):
    search_fields = ('name','name_nom_id')
    list_display = ('id','name','name_nom_id',)
    pass

class MuenzstandView(ImportExportModelAdmin):
    search_fields = ('name',)
    list_display = ('id','name',)
    pass

class RandView(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('id','name',)
    pass

class MzstaetteView(ImportExportModelAdmin):
    search_fields = ('name','name_nom_id')
    list_display = ('id','name','name_nom_id', 'ndpikmk', 'geonames', 'lat', 'long')
    list_editable = ('ndpikmk', 'geonames','lat', 'long',)
    actions = [actions.merge, actions.export_as_xls]
    pass

class Obj_PersonInline(admin.TabularInline):
    model = Obj_Person
    #ordering = ("Person.name",)
    extra = 0
    raw_id_fields = ('idfk_Person', 'idfk_PersonFunktion')
    show_change_link = True
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Use select_related for foreign key relationships
        return queryset.select_related('idfk_Person', 'idfk_PersonFunktion')

class Mztyp_PersonInline(admin.TabularInline):
    model = Mztyp_Person
    #ordering = ("Person.name",)
    extra = 1
    autocomplete_fields = ['idfk_Person']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('idfk_Person', 'idfk_PersonFunktion')
    
class KatalogPersonInline(admin.TabularInline):
    model = KatalogPerson
    #ordering = ("Person.name",)
    extra = 1
    autocomplete_fields = ['person','personfunktion']

class Obj_RefInline(admin.TabularInline):
    model = Obj_Ref
    #ordering = ("Person.name",)
    extra = 0
    raw_id_fields = ('idfk_Ref', 'variante') # Use raw_id_fields for the reference field
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('idfk_Ref', 'idfk_Obj')

class Typ_RefInline(admin.TabularInline):
    model = Typ_Ref
    extra = 1
    classes = ['collapse']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('Ref')

class Person_RefInline(admin.TabularInline):
    model = Person_Ref
    extra = 1

class SlgInformation_RefInline(nested_admin.NestedTabularInline):
    model = SlgInformation_Ref
    extra = 0
    max_num = 10  # Begrenze auf 10 Ref-Inlines pro SlgInformation
    classes = ['collapse']
    raw_id_fields = ('Ref',)  # KRITISCH: Verwendet raw_id_fields statt Dropdown für bessere Performance
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('Ref', 'Slginfo')

class SlgInformationInline(nested_admin.NestedTabularInline):
    model = SlgInformation
    autocomplete_fields = ['person','objekte',]
    
    extra = 0
    max_num = 20  # REDUZIERT: Begrenzt die Anzahl der SlgInformation-Inlines für deutlich bessere Performance
    inlines = [SlgInformation_RefInline]
    classes = ['collapse']  # Standardmäßig eingeklappt für bessere Performance
    
    # Vereinfachte Felder zur Performance-Optimierung
    fields = ('dat_verb', 'dat_von', 'dat_bis', 'information', 'person')
    
    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'rows':2, 'cols':40})},  # Kleinere Widgets
    }
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related(
            'Slg'
        ).prefetch_related(
            'person',
            'objekte__Slg',
            'objekte__SlgTeil', 
            'objekte__Typ',
            'schlagworte',
            'slginformation_ref_set__Ref'
        ).order_by('-dat_von', 'dat_bis')  # Sortierung für konsistente Anzeige

# Füge diesen Filter vor der SlgInformationAdmin Klasse hinzu
class RawPersonenFilter(admin.SimpleListFilter):
    title = 'Raw Personen'
    parameter_name = 'has_raw_personen'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Mit Personen'),
            ('no', 'Ohne Personen'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(raw_personen__isnull=True).exclude(raw_personen='')
        if self.value() == 'no':
            return queryset.filter(Q(raw_personen__isnull=True) | Q(raw_personen=''))

import re

def match_personen_exact(modeladmin, request, queryset):
    for ereignis in queryset:
        # Vorherige Zuordnungen löschen
        ereignis.person.clear()

        raw = ereignis.raw_personen or ""
        # Kommaseparierte Liste in Einzelnamen aufsplitten
        names = [n.strip() for n in raw.split(",") if n.strip()]

        for name in names:
            try:
                # Use regex lookup instead of iexact to avoid collation issues
                person = Person.objects.filter(name__iregex=r'^' + re.escape(name) + r'$').first()
                if person:
                    # Treffer hinzufügen
                    ereignis.person.add(person)
            except Exception as e:
                # Log the error but continue processing
                continue

        ereignis.save()

# Füge die Beschreibung als Attribut hinzu
match_personen_exact.short_description = "Personen matchen (Exact Only)"

class SlgInformation_SchlagwortInline(admin.TabularInline):
    model = SlgInformationSchlagwort
    extra = 1
    autocomplete_fields = ['ereignisschlagwort']

class SlgInformationAdmin(ImportExportModelAdmin,):
    search_fields = ('name', 'information', 'person__name', 'raw_personen')
    list_editable = ('name','information','dat_verb')
    list_display = ('id', 'name', 'information', 'dat_verb', 'dat_von', 'dat_bis', 'Slg', 'display_schlagworte', 'display_persons')
    list_filter = (
        ('Slg', RelatedDropdownFilter),  # Besserer Filter für Sammlungen
        RawPersonenFilter,
    )
    list_select_related = ('Slg',)  # Für bessere Performance in der Liste
    actions = [match_personen_exact]
    
    # PERFORMANCE-OPTIMIERUNG: raw_id_fields statt autocomplete_fields für bessere Performance  
    raw_id_fields = ['person']  # Nur person, objekte wird erstmal nicht benötigt
    
    inlines = [SlgInformation_RefInline, SlgInformation_SchlagwortInline]  # Inline hinzugefügt
    fieldsets = (
        (None, {
            'fields': (
                'Slg',  # Sammlung hinzugefügt für bessere Navigation
                ('dat_verb', 'dat_von', 'dat_bis',),
                ('name', 'information'),
                'person',  # Getrennt für bessere Übersichtlichkeit
                # 'objekte',  # ENTFERNT: Wie vom User gewünscht, erstmal nicht nötig
                # 'schlagworte',  # <-- ENTFERNT! Wird über Inline verwaltet
                'raw_schlagworte',
                'raw_personen',  # Für Bulk-Import von Personen
            ),
        }),
    )
    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'rows':3, 'cols':45})},
    }
    
    def get_queryset(self, request):
        """Optimiertes QuerySet für bessere Performance"""
        queryset = super().get_queryset(request)
        return queryset.select_related('Slg').prefetch_related(
            'person',
            'objekte',
            'schlagworte',
            'slginformation_ref_set__Ref'
        )

    def display_persons(self, obj):
        """Displays names of related persons."""
        # Nutze prefetch_related Daten falls verfügbar
        if hasattr(obj, '_prefetched_objects_cache') and 'person' in obj._prefetched_objects_cache:
            return ", ".join([p.name for p in obj._prefetched_objects_cache['person']])
        return ", ".join([p.name for p in obj.person.all()])
    display_persons.short_description = 'Personen'

    def display_schlagworte(self, obj):
        """Displays names of related schlagworte."""
        # Nutze prefetch_related Daten falls verfügbar
        if hasattr(obj, '_prefetched_objects_cache') and 'schlagworte' in obj._prefetched_objects_cache:
            return ", ".join([s.name for s in obj._prefetched_objects_cache['schlagworte']])
        return ", ".join([s.name for s in obj.schlagworte.all()])
    display_schlagworte.short_description = 'Schlagworte'

class SlgView(nested_admin.NestedModelAdmin):
    # PERFORMANCE-OPTIMIERUNG: Nested-Inlines deaktiviert für deutlich bessere Performance
    inlines = []  # SlgInformation wird separat über den eigenen Admin verwaltet
    exclude = ['created_at']
    list_display = ('name', 'kategorie', 'beschreibung', 'ereignis_count', 'ereignisse_link')
    list_filter = ('kategorie',)
    search_fields = ('name',)
    show_full_result_count = False  # Reduziert COUNT-Queries für bessere Performance
    readonly_fields = ('ereignisse_link',)
    
    fieldsets = (
        (None, {
            'fields': ('name', 'kategorie', 'beschreibung', 'bildrechte_lizenz', 'cover')
        }),
        ('Bildeinstellungen', {
            'classes': ('collapse',),
            'fields': ('bildurl', 'bild_endung_av', 'bild_endung_rv', 'entferne_zeichen')
        }),
        ('Ereignisse', {
            'fields': ('ereignisse_link',),
            'description': 'Ereignisse werden für bessere Performance separat verwaltet.'
        }),
    )
    
    def get_queryset(self, request):
        """Optimiertes QuerySet ohne teure Nested-Inlines"""
        from django.db.models import Count
        
        queryset = super().get_queryset(request)
        if _is_admin_autocomplete_request(request):
            return queryset.only('id', 'name')
        return queryset.select_related('kategorie').annotate(
            _ereignis_count=Count('slginformation', distinct=True)
        )
    
    def ereignis_count(self, obj):
        """Zeigt die Anzahl der Ereignisse für diese Sammlung"""
        return obj._ereignis_count
    ereignis_count.short_description = 'Anzahl Ereignisse'
    ereignis_count.admin_order_field = '_ereignis_count'
    
    def ereignisse_link(self, obj):
        """Erstellt einen Link zur Verwaltung der Ereignisse"""
        from django.urls import reverse
        from django.utils.html import format_html
        
        if obj.pk:
            url = reverse('admin:slg_slginformation_changelist')
            return format_html(
                '<a href="{}?Slg__id__exact={}" class="button">Ereignisse verwalten ({})</a>',
                url, obj.pk, obj._ereignis_count
            )
        return "-"
    ereignisse_link.short_description = 'Ereignisse'
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Fügt Kontext-Info für Performance-optimierte Anzeige hinzu"""
        extra_context = extra_context or {}
        
        if object_id:
            # Füge Hinweise zur separaten Ereignis-Verwaltung hinzu
            from django.urls import reverse
            ereignisse_url = reverse('admin:slg_slginformation_changelist') + f'?Slg__id__exact={object_id}'
            extra_context['ereignisse_admin_url'] = ereignisse_url
            extra_context['performance_info'] = (
                "Ereignisse werden für bessere Performance separat verwaltet. "
                "Nutzen Sie den 'Ereignisse verwalten' Button in der Liste oder "
                f"<a href='{ereignisse_url}' target='_blank'>hier klicken</a>."
            )
        
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    # ... bestehende Konfiguration ...

@admin.register(Fundort)
class FundortAdmin(admin.ModelAdmin):
    list_display = ('name',)

class FundView(admin.ModelAdmin):
    search_fields = ('objekt','maßnahmennr', 'fundnummer')
    list_display = ('objekt','maßnahmennr', 'fundnummer','parzelle','quadrant','quadrantzusatz','anmerkung','vn','vno','vo', 'vso', 'vs', 'vsw', 'vw', 'vnw','lm_von', 'lm_bis','niveautiefe_in_m_von', 'niveautiefe_in_m_bis', 'niveau')
    raw_id_fields = ('objekt',)
    list_editable = ('parzelle','quadrant','quadrantzusatz','anmerkung','vn','vno','vo', 'vso', 'vs', 'vsw', 'vw', 'vnw','lm_von', 'lm_bis','niveautiefe_in_m_von', 'niveautiefe_in_m_bis', 'niveau')
    autocomplete_fields = ['zusammen_gefundene_muenzen',]
    save_on_top = True
    save_as = True

    fieldsets = (
        (None, {
            'fields': (
                ('objekt', 'zusammen_gefundene_muenzen', 'andere_materialien',),
                'maßnahmennr',
                ('fundnummer', 'fundnummerzusatz','kistennr',),
                ('fundort', 'parzelle', 'fundstelle', 'fundposition',),
                ('lm_von', 'lm_bis','niveautiefe_in_m_von', 'niveautiefe_in_m_bis', 'niveau'),
                ('vn','vno','vo', 'vso', 'vs', 'vsw', 'vw', 'vnw',),
                ('schnitt', 'bereichsbezeichnung',),
                ('sondage','quadrant','quadrantzusatz','flaeche', 'se', 'stratum',),
                'fundkontext',
                'anmerkung',
                ('fundjahr', 'funddatum', 'bearbeiter',),
            ),
        }),
    )

    list_filter = (
        'maßnahmennr',
        'fundstelle',
    )

class FundInline(admin.TabularInline):  # TabularInline ist effizienter als StackedInline
    model = Fund
    extra = 0
    classes = ['collapse']
    
    # Verwende raw_id_fields für die teuersten Queries
    fields = ('maßnahmennr', 'fundnummer', 'fundort', 'parzelle', 'fundjahr', 'anmerkung')
    raw_id_fields = ('fundort',)  # Das war eine der teuersten Queries (80.07ms)
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('fundort', 'objekt')
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.max_num = 1
        return formset

class PersonView(ImportExportModelAdmin,):
    search_fields = ('name','name_nom_id', 'beschreibung', 'zeichen')
    list_display = ('id','name','name_nom_id', 'dat_verb', 'dat_geboren', 'dat_gestorben', 'beschreibung', 'DNB')
    list_editable = ('dat_verb', 'dat_geboren', 'dat_gestorben',)
    ordering = ['-id']
    inlines = (Person_RefInline,)

    fieldsets = (
        (None, {
            'fields': (
                'name',
                'name_nom_id',
                'beschreibung',
                'zeichen',
                ('dat_geboren', 'dat_gestorben','dat_verb', ),
                ('WikiDe','WikiEn',),
                ('BiographiePortal','VIAF',),
                ('DeutscheDigitaleBib','DNB','Link'),
                ('DB', 'OeBL',),
                ('Zisterzienserlexikon','Benediktinerlexikon',),
                'mmlo',
            ),
        }),
    )
    readonly_fields = ('Link',)

    def get_form(self, request, obj=None, **kwargs):
        form = super(PersonView, self).get_form(request, obj, **kwargs)
        form.base_fields['name'].widget.attrs['style'] = 'width: 60em;'
        form.base_fields['beschreibung'].widget.attrs['style'] = 'width: 60em;'
        return form

    def Link(self, obj):
        url = '<a href="https://portal.dnb.de/opac.htm?query={}&method=simpleSearch&categoryId=persons" target="_blank">GND</a>'.format(obj.name)
        return mark_safe(url)

    def response_change(self, request, obj, post_url_continue=None):
        # lädt die Daten OCRE und Co. über eine SPARQL-Abfrage als CSV herunter und fügt sie zum Datensatz hinzu
        if "_download_infos" in request.POST:
            
            if obj.DNB:
                link = obj.DNB
                linkid = link.replace('http://d-nb.info/gnd/', '').replace('https://d-nb.info/gnd/', '')
                url2 = "http://beacon.findbuch.de/seealso/pnd-aks?format=seealso&id="+linkid
                
                
                with requests.Session() as s:
                    download = s.get(url2)

                    #decoded_content = download.content.decode('utf-8')

                    # cr = csv.reader(decoded_content.splitlines(), delimiter=',')
                    # data = json.load(download.read())
                    data = download.json()
                    print("JSON string = ", data[3]) 
                    for d in data[3]:
                        print(d)
                        if "https://tools.wmflabs.org/persondata/redirect/gnd/de/" in d:
                            if not obj.WikiDe:
                                r = requests.get(d) 
                                obj.WikiDe = r.url
                                print("abgespeichert")
                        if "http://www.zisterzienserlexikon.de/" in d:
                            if not obj.Zisterzienserlexikon:
                                #r = requests.get(d) 
                                obj.Zisterzienserlexikon = d
                                print("abgespeichert")
                        if "http://www.biographien.ac.at" in d:
                            if not obj.OeBL:
                                #r = requests.get(d) 
                                obj.OeBL = d
                                print("abgespeichert")
                        if "http://www.deutsche-biographie.de/" in d:
                            if not obj.DB:
                                #r = requests.get(d) 
                                obj.DB = d
                                print("abgespeichert")
                        if "https://www.deutsche-digitale-bibliothek.de/" in d:
                            if not obj.DeutscheDigitaleBib:
                                #r = requests.get(d) 
                                obj.DeutscheDigitaleBib = d
                                print("abgespeichert")
                        
                            # r.url
                    # obj.Ppl.add(Person.objects.get(name_nom_id=praegeherr))
                    # obj.mztyp_person_set.add(PersonFunktion.objects.get(id=1))
                    
                    #print(obj.Mzstaette)
                    obj.save()

                    opts = obj._meta
                    obj_url = reverse(
                        'admin:%s_%s_change' % (opts.app_label, opts.model_name),
                        args=(quote(obj.pk),),
                        current_app=self.admin_site.name,
                    )
                    self.message_user(request, "Daten vom Online-Typenkatalog heruntergeladen")
                    if post_url_continue is None:
                        post_url_continue = obj_url
                        return HttpResponseRedirect(post_url_continue)
                    #save_as=True
                ##############################################
                # json_string = urllib.request.urlopen(url)
                # cr = json_string.reader()

                # for row in cr:
                #     print(row)

                #data = json.loads(json_string)
                # decoded_reponse = json_string.read().decode('utf-8')
                # json_response = json.loads(decoded_reponse)

                # print(json_response)
                # for key, value in json_response.items():
                #     print(key, ":", value)
                # print("Project name: ", json_response["projectinfo"][0]["name"])
                
                #return HttpResponseRedirect(".")
        
        return super().response_change(request, obj)

class WappenAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']

class RegionAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']
    
class SchlagwortAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']
    # autocomplete_fields=['name']

class KatSchlagwortAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name', 'synonyme']
    # autocomplete=('name')

class FaelschungAdmin(admin.ModelAdmin):
    search_fields = ['name']

class AvBildtyp_SchlagwortInline(admin.TabularInline):
    model = AvBildtyp_Schlagwort
    extra = 1

class RvBildtyp_SchlagwortInline(admin.TabularInline):
    model = RvBildtyp_Schlagwort
    extra = 1

class Katalog_SchlagwortInline(admin.TabularInline):
    model = KatalogSchlagwort
    extra = 1
    # autocomplete=('katalog', 'katschlagwort')
    
class Mztyp_SchlagwortInline(admin.TabularInline):
    model = Mztyp_Schlagwort
    extra = 1
    classes = ['collapse']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('schlagwort')
    
class Mztyp_WappenInline(admin.TabularInline):
    model = Mztyp_Wappen
    extra = 1
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wappen')
    
class Obj_interneAnmerkungInline(admin.TabularInline):
    model = Obj_interne_Anmerkung
    #ordering = ("Person.name",)
    extra = 0
    # Verwende raw_id_fields für bessere Performance
    raw_id_fields = ('interne_Anmerkung',)  # Das war eine der teuersten Queries (69.59ms)
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related('interne_Anmerkung', 'idfk_Obj')

class Mztyp_interne_AnmerkungInline(admin.TabularInline):
    model = Mztyp_interne_Anmerkung
    #ordering = ("Person.name",)
    extra = 1
    classes = ['collapse']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('interne_Anmerkung')

class AvBildtypAdminForm(forms.ModelForm):
    class Meta:
        model = AvBildtyp
        fields = '__all__'        
        widgets = {
            'name': forms.Textarea(attrs={'cols': 80, 'rows': 20}),
        }

class AvBildtypAdmin(ImportExportActionModelAdmin, admin.ModelAdmin):
    #list_editable = ('name',)
    #list_editable = ('name',)
    form = AvBildtypAdminForm
    #list_select_related = ('object_count', '_mztyp_count',)
    # actions = [actions.export_as_xls]
        # return obj.schlagworte.all()
    ordering = ['name',]
    #list_select_related = ('object_count', '_mztyp_count',)
    # actions = [actions.export_as_xls]
        # return obj.schlagworte.all()
    search_fields = ['name', 'abk',]
    list_display = ('id', 'name', 'Schlagworte','object_count', 'mztyp_count')
    inlines = (AvBildtyp_SchlagwortInline,)
        #return super(AvBildtypAdmin,self).get_queryset(request).prefetch_related('obj_set', 'muenztyp_set')

    def Schlagworte(self, obj):
        return ", ".join([p.name for p in obj.schlagworte.all()])

        #return super(AvBildtypAdmin,self).get_queryset(request).prefetch_related('obj_set', 'muenztyp_set')
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Admin-Autocomplete wird bei jedem Tastendruck aufgerufen; hier bewusst
        # keine teuren Aggregationen/Prefetches aus der Listenansicht ausfuehren.
        if _is_admin_autocomplete_request(request):
            return queryset.only('id', 'name', 'abk')
        return queryset.prefetch_related('schlagworte').annotate(
            _object_count=Count("obj", distinct=True),
            _mztyp_count=Count("avmztypen", distinct=True),
        )

    def object_count(self, obj):
        return obj._object_count

    def mztyp_count(self, obj):
        return obj._mztyp_count

    object_count.short_description = "Anzahl der Objekte"
    object_count.admin_order_field = "_object_count"
    mztyp_count.short_description = "Anzahl der Münztypen"
    mztyp_count.admin_order_field = "_mztyp_count"
    
class RvBildtypAdminForm(forms.ModelForm):
    class Meta:
        model = RvBildtyp
        fields = '__all__'
        widgets = {
            'name': forms.Textarea(attrs={'cols': 80, 'rows': 20}),
    # actions = [actions.merge, actions.export_as_xls]
        }

        # return obj.schlagworte.all()
class RvBildtypAdmin(ImportExportActionModelAdmin, admin.ModelAdmin):
    form = RvBildtypAdminForm
    ordering = ['name']
    # actions = [actions.merge, actions.export_as_xls]
    search_fields = ['name', 'abk',]
    list_display = ('id', 'name', 'Schlagworte','object_count', 'mztyp_count')
        # return obj.schlagworte.all()
        #return super(RvBildtypAdmin,self).get_queryset(request).prefetch_related('obj_set', 'muenztyp_set')
    inlines = (RvBildtyp_SchlagwortInline,)

    def Schlagworte(self, obj):
        return ", ".join([p.name for p in obj.schlagworte.all()])

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Admin-Autocomplete wird bei jedem Tastendruck aufgerufen; hier bewusst
        # keine teuren Aggregationen/Prefetches aus der Listenansicht ausfuehren.
        if _is_admin_autocomplete_request(request):
            return queryset.only('id', 'name', 'abk')
        #return super(RvBildtypAdmin,self).get_queryset(request).prefetch_related('obj_set', 'muenztyp_set')
        queryset = queryset.prefetch_related('schlagworte').annotate(
            _object_count=Count("obj", distinct=True),
            _mztyp_count=Count("rvmztypen", distinct=True),
        )
        return queryset

    def object_count(self, obj):
        return obj._object_count

    def mztyp_count(self, obj):
        return obj._mztyp_count

    object_count.short_description = "Anzahl der Objekte"
    object_count.admin_order_field = "_object_count"
    mztyp_count.short_description = "Anzahl der Münztypen"
    mztyp_count.admin_order_field = "_mztyp_count"
    
    # def get_form(self, request, obj=None, **kwargs):
    #     form = super(RvBildtypAdmin, self).get_form(request, obj, **kwargs)
    #     form.base_fields['name'].widget.attrs['style'] = 'width: 80em;'
    #     return form
    
class AvBeizeichenAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ['name']
    search_fields = ['name']
    actions = [actions.merge, actions.export_as_xls]

class RvBeizeichenAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'object_count', 'mztyp_count')
    ordering = ['name']
    search_fields = ['name']
    actions = [actions.merge, actions.export_as_xls]
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if _is_admin_autocomplete_request(request):
            return queryset.only('id', 'name')
        queryset = queryset.annotate(
            _object_count=Count("obj", distinct=True),
            _mztyp_count=Count("rvbeizeichen", distinct=True),
        )
        return queryset
        #return super(RvBildtypAdmin,self).get_queryset(request).prefetch_related('obj_set', 'muenztyp_set')

    def object_count(self, obj):
        return obj._object_count

    def mztyp_count(self, obj):
        return obj._mztyp_count

    object_count.short_description = "Anzahl der Objekte"
    object_count.admin_order_field = "_object_count"
    mztyp_count.short_description = "Anzahl der Münztypen"
    mztyp_count.admin_order_field = "_mztyp_count"

class AvOffizinAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ['name']
    search_fields = ['name']
    actions = [actions.merge, actions.export_as_xls]

class RvOffizinAdmin(CachedAutocompleteAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ['name']
    search_fields = ['name']
    actions = [actions.merge, actions.export_as_xls]
    autocomplete_only_fields = ('id', 'name')

class AvBildrandAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ['name']
    search_fields = ['name']

class RvBildrandAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ['name']
    search_fields = ['name']

class Obj_SlgTeil(admin.TabularInline):
    model = Obj
    exclude = ['avleg','avbeschr', 'rvleg', 'rvbeschr','av_img', 'rv_img']
    #exclude = ['idfk_Mzstaette', 'avleg','avbeschr', 'rvleg', 'rvbeschr','av_img', 'rv_img']
    #ordering = ("Mzstaette.name",)
    extra = 0

class ObjInline(admin.TabularInline):
    model = Obj
    fk_name = 'Typ'
    fields = ('Slg', 'invnr', 'durchmesser', 'gewicht', 'stempelstellung', 'rv_beizeichen', 'rv_offizin')
    exclude = ['avleg','avbeschr', 'rvleg', 'rvbeschr','av_img', 'rv_img']
    #exclude = ['idfk_Mzstaette', 'avleg','avbeschr', 'rvleg', 'rvbeschr','av_img', 'rv_img']
    #ordering = ("Mzstaette.name",)
    extra = 2
    show_change_link = True

    def has_delete_permission(self, request, obj=None):
        return False
    # def get_absolute_url(self):
    #     def view_on_site(self, obj):
    #         return reverse("Objekt", kwargs={"id": self.id})



class SlgTeilAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('name',)
    # inlines = (Obj_SlgTeil,)  # Entfernt - Objekte sollen nicht mehr angezeigt werden

class MuenztypImport(resources.ModelResource):
    Objekttyp = fields.Field(
        column_name='Objekttyp',
        attribute='Objekttyp',
        widget=ForeignKeyWidget(Objekttyp, field='name'))  # Bitte anpassen.
    
    Herstellung = fields.Field(
        column_name='Herstellung',
        attribute='Herstellung',
        widget=ForeignKeyWidget(Herstellung, field='name'))  # Bitte anpassen.
    
    Reichskreis = fields.Field(
        column_name='Reichskreis',
        attribute='Reichskreis',
        widget=ForeignKeyWidget(Reichskreis, field='name'))
    
    Muenzstand = fields.Field(
        column_name='Münzstand',
        attribute='Muenzstand',
        widget=ForeignKeyWidget(Muenzstand, field='name'))
    
    Nominal = fields.Field(
        column_name='Nominal',
        attribute='Nominal',
        widget=ForeignKeyWidget(Nominal, field='name'))
    
    Metall = fields.Field(
        column_name='Material',
        attribute='Metall',
        widget=ForeignKeyWidget(Metall, field='name'))
    
    Mzstaette = fields.Field(
        column_name='Münzstätte',
        attribute='Mzstaette',
        widget=ForeignKeyWidget(Mzstaette, field='name'))
    
    region = fields.Field(
        column_name='Region',
        attribute='region',
        widget=ForeignKeyWidget(Region, field='name'))
    
    av_bildtyp = fields.Field(
        column_name='AvBildtyp',
        attribute='av_bildtyp',
        widget=ForeignKeyWidget(AvBildtyp, field='name'))
    
    av_beizeichen = fields.Field(
        column_name='AvBeizeichen',
        attribute='av_beizeichen',
        widget=ForeignKeyWidget(AvBeizeichen, field='name'))
    
    av_bildrand = fields.Field(
        column_name='AvBildrand',
        attribute='av_bildrand',
        widget=ForeignKeyWidget(AvBildrand, field='name'))
    
    rv_bildtyp = fields.Field(
        column_name='RvBildtyp',
        attribute='rv_bildtyp',
        widget=ForeignKeyWidget(RvBildtyp, field='name'))
    
    rv_beizeichen = fields.Field(
        column_name='RvBeizeichen',
        attribute='rv_beizeichen',
        widget=ForeignKeyWidget(RvBeizeichen, field='name'))
    
    rv_bildrand = fields.Field(
        column_name='RvBildrand',
        attribute='rv_bildrand',
        widget=ForeignKeyWidget(RvBildrand, field='name'))
    
    rand = fields.Field(
        column_name='Rand',
        attribute='rand',
        widget=ForeignKeyWidget(Rand, field='name'))
    
    workflow = fields.Field(
        column_name='Workflow',
        attribute='workflow',
        widget=ForeignKeyWidget(Workflow, field='name'))
    
    Ref = fields.Field(
        column_name='Zitat',
        attribute='Ref',
        widget=ForeignKeyWidget(Ref, field='abk'))
    
    variante = fields.Field(
        column_name='Variante',
        attribute='variante',
        widget=ForeignKeyWidget(Variantenbeschr, field='name'))
    
    class Meta:
        model = Muenztyp
        fields = ('id', 'muenztyptitel', 'titel', 'Objekttyp', 'Herstellung', 'Reichskreis', 'Muenzstand',
                  'Nominal', 'Metall', 'Mzstaette', 'region', 'avleg', 'av_bildtyp', 'av_beizeichen', 'av_bildrand',
                  'rvleg', 'rv_bildtyp', 'rv_beizeichen', 'rv_bildrand', 'rand', 'workflow', 'Ref', 'variante', 'link', 'dat_von', 'dat_bis', 'dat_verb')
        export_order = fields
        name = "Export der Muenztypen"
        skip_unchanged = True
        report_skipped = True
    
    def get_import_id_fields(self):
        return ['id']
    
    def dehydrate_Objekttyp(self, muenztyp):
        return muenztyp.Objekttyp.name if muenztyp.Objekttyp else None

    def dehydrate_Herstellung(self, muenztyp):
        return muenztyp.Herstellung.name if muenztyp.Herstellung else None

    def dehydrate_Reichskreis(self, muenztyp):
        return muenztyp.Reichskreis.name if muenztyp.Reichskreis else None

    def dehydrate_Muenzstand(self, muenztyp):
        return muenztyp.Muenzstand.name if muenztyp.Muenzstand else None

    def dehydrate_Nominal(self, muenztyp):
        return muenztyp.Nominal.name if muenztyp.Nominal else None

    def dehydrate_Metall(self, muenztyp):
        return muenztyp.Metall.name if muenztyp.Metall else None

    def dehydrate_Mzstaette(self, muenztyp):
        return muenztyp.Mzstaette.name if muenztyp.Mzstaette else None

    def dehydrate_region(self, muenztyp):
        return muenztyp.region.name if muenztyp.region else None

    def dehydrate_av_bildtyp(self, muenztyp):
        return muenztyp.av_bildtyp.name if muenztyp.av_bildtyp else None

    def dehydrate_av_beizeichen(self, muenztyp):
        return muenztyp.av_beizeichen.name if muenztyp.av_beizeichen else None

    def dehydrate_av_bildrand(self, muenztyp):
        return muenztyp.av_bildrand.name if muenztyp.av_bildrand else None

    def dehydrate_rv_bildtyp(self, muenztyp):
        return muenztyp.rv_bildtyp.name if muenztyp.rv_bildtyp else None

    def dehydrate_rv_beizeichen(self, muenztyp):
        return muenztyp.rv_beizeichen.name if muenztyp.rv_beizeichen else None

    def dehydrate_rv_bildrand(self, muenztyp):
        return muenztyp.rv_bildrand.name if muenztyp.rv_bildrand else None

    def dehydrate_rand(self, muenztyp):
        return muenztyp.rand.name if muenztyp.rand else None

    def dehydrate_workflow(self, muenztyp):
        return muenztyp.workflow.name if muenztyp.workflow else None

    def dehydrate_Ref(self, muenztyp):
        return muenztyp.Ref.abk if muenztyp.Ref else None

    def dehydrate_variante(self, muenztyp):
        return muenztyp.variante.name if muenztyp.variante else None

def extract_year(literal):
    if isinstance(literal, Literal):
        if literal.datatype == XSD.gYear:
            if literal.startswith('-'):  # Überprüfen auf negatives Jahr
                return str(literal)  # Direkte Verwendung des String-Werts
            elif isinstance(literal.value, date):
                return str(literal.value.year)  # Extrahieren des Jahres aus dem Datum
            else:
                return str(literal.value)  # Verwendung des Wertes, wenn kein Datum
    return None



def process_download_infos(obj):
    # Stellen Sie sicher, dass das Objekt einen Link enthält
    if not obj.link:
        return False, "Fehlermeldung"  # Beenden, falls kein Link vorhanden ist

    # Code zur Verarbeitung des Links und der Daten
    try:
        # Beispiel: Setzen von Feldern basierend auf geparsten Daten
        if 'numismatics.org/' in obj.link:
            # Normalize link - SPARQL database typically uses HTTP URIs
            if obj.link.startswith("https://"):
                http_link = "http://" + obj.link[8:]
            elif obj.link.startswith("http://"):
                http_link = obj.link
            else:
                http_link = "http://" + obj.link

            sparql_endpoint = 'https://nomisma.org/query'

            def run_sparql(query):
                normalized_query = textwrap.dedent(query).strip()
                params = {'query': normalized_query, 'output': 'json'}
                encoded_params = urlencode(params)
                sparql_query_url = f"{sparql_endpoint}?{encoded_params}"

                try:
                    response = requests.get(sparql_query_url, timeout=30)
                    response.raise_for_status()
                except RequestException as exc:
                    raise RuntimeError(
                        f"SPARQL-Request fehlgeschlagen: {exc}"
                    ) from exc

                try:
                    return response.json()
                except ValueError as exc:
                    raise RuntimeError(
                        "SPARQL-Antwort konnte nicht als JSON gelesen werden"
                    ) from exc

            # Query 1: Main type information
            # Try with HTTP URI first, then HTTPS if no results
            query_main = f"""
            SELECT * WHERE {{
              <{http_link}> ?p ?o
            }}
            """
            try:
                data_main = run_sparql(query_main)
            except RuntimeError as exc:
                return False, str(exc)
            
            # If no results with HTTP, try HTTPS URI
            if not data_main.get('results', {}).get('bindings', []):
                https_link = "https://" + http_link[7:] if http_link.startswith("http://") else obj.link
                query_main_https = f"""
                SELECT * WHERE {{
                  <{https_link}> ?p ?o
                }}
                """
                try:
                    data_main_https = run_sparql(query_main_https)
                    if data_main_https.get('results', {}).get('bindings', []):
                        data_main = data_main_https
                        http_link = https_link  # Use HTTPS link for subsequent queries
                except RuntimeError:
                    pass  # Keep original data_main
            
            # Define your namespaces
            nmo = "http://nomisma.org/ontology#"
            
            # Extract data from main query
            praegeherr_list = []
            dat_von = ""
            dat_bis = ""
            nom = ""
            mint = ""
            obverse_uri = None
            reverse_uri = None
            
            for binding in data_main.get('results', {}).get('bindings', []):
                p = binding.get('p', {}).get('value', '')
                o = binding.get('o', {})
                o_value = o.get('value', '')
                
                if p == nmo + 'hasAuthority':
                    praegeherr_list.append(o_value)
                elif p == nmo + 'hasStartDate':
                    # Extract year from gYear datatype
                    dat_von = o_value.lstrip('0') if o_value else ""
                elif p == nmo + 'hasEndDate':
                    dat_bis = o_value.lstrip('0') if o_value else ""
                elif p == nmo + 'hasDenomination':
                    nom = o_value
                elif p == nmo + 'hasMint':
                    mint = o_value
                elif p == nmo + 'hasObverse':
                    obverse_uri = o_value
                elif p == nmo + 'hasReverse':
                    reverse_uri = o_value
            
            # Query 2: Obverse information
            avleg = ""
            avpor_list = []
            if obverse_uri:
                query_obverse = f"""
                SELECT * WHERE {{
                  <{obverse_uri}> ?p ?o
                }}
                """
                try:
                    data_obverse = run_sparql(query_obverse)
                except RuntimeError as exc:
                    return False, str(exc)

                for binding in data_obverse.get('results', {}).get('bindings', []):
                    p = binding.get('p', {}).get('value', '')
                    o_value = binding.get('o', {}).get('value', '')
                    
                    if p == nmo + 'hasLegend':
                        avleg = o_value
                    elif p == nmo + 'hasPortrait':
                        avpor_list.append(o_value)
            
            # Query 3: Reverse information
            rvleg = ""
            rvpor_list = []
            if reverse_uri:
                query_reverse = f"""
                SELECT * WHERE {{
                  <{reverse_uri}> ?p ?o
                }}
                """
                try:
                    data_reverse = run_sparql(query_reverse)
                except RuntimeError as exc:
                    return False, str(exc)

                for binding in data_reverse.get('results', {}).get('bindings', []):
                    p = binding.get('p', {}).get('value', '')
                    o_value = binding.get('o', {}).get('value', '')
                    
                    if p == nmo + 'hasLegend':
                        rvleg = o_value
                    elif p == nmo + 'hasPortrait':
                        rvpor_list.append(o_value)
        
        elif 'rpc.ashmus.ox.ac.uk/' in obj.link:
            # Fetch HTML content and parse to find the RDF link
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36'}
            response = requests.get(obj.link, headers=headers)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                rdf_link = soup.find('a', string='rdf')
                
                if rdf_link:
                    rdf_url = urljoin(obj.link, rdf_link.get('href'))
                else:
                    # Wenn kein RDF-Link gefunden wurde, aus der if-Abfrage aussteigen
                    # messages.warning(request, f"Kein RDF-Link für {obj.link} gefunden.")
                    return False, "Kein RDF-Link gefunden"

                # Fetch and parse the RDF/XML data
                g = Graph()
                g.parse(rdf_url, format='xml')

                # Define your namespaces
                nmo = Namespace("http://nomisma.org/ontology#")
                
                # Use rdflib's functions to find the information you want
                praegeherr_list = []
                for s, p, o in g.triples((None, nmo.hasAuthority, None)):
                    praegeherr_list.append(str(o))

                dat_von = ""
                for s, p, o in g.triples((None, nmo.hasStartDate, None)):
                    dat_von = extract_year(o)

                dat_bis = ""
                for s, p, o in g.triples((None, nmo.hasEndDate, None)):
                    dat_bis = extract_year(o)

                nom = ""
                for s, p, o in g.triples((None, nmo.hasDenomination, None)):
                    nom = str(o)

                mint = ""
                for s, p, o in g.triples((None, nmo.hasMint, None)):
                    mint = str(o)

                # Find the obverse for that TypeSeriesItem
                type_series_item_uri = URIRef(obj.link)
                for s, p, o in g.triples((type_series_item_uri, nmo.hasObverse, None)):
                    obverse_uri = o

                # Now find the legend for that obverse
                avleg = ""
                for s, p, o in g.triples((obverse_uri, nmo.hasLegend, None)):
                    avleg = str(o)

                avpor_list = []
                for s, p, o in g.triples((obverse_uri, nmo.hasPortrait, None)):
                    avpor_list.append(str(o))

                # Find the reverse for that TypeSeriesItem
                for s, p, o in g.triples((type_series_item_uri, nmo.hasReverse, None)):
                    reverse_uri = o

                # Now find the legend for that reverse
                rvleg = ""
                for s, p, o in g.triples((reverse_uri, nmo.hasLegend, None)):
                    rvleg = str(o)

                rvpor_list = []
                for s, p, o in g.triples((reverse_uri, nmo.hasPortrait, None)):
                    rvpor_list.append(str(o))
            else:
                return False, "RDF-Link nicht gefunden"

        try:
            if dat_von:
                obj.dat_von = int(dat_von)
            if dat_bis:
                obj.dat_bis = int(dat_bis)
        except ValueError:
            print("Invalid value for dat_von or dat_bis:", dat_von, dat_bis)

        if not obj.avleg:
            obj.avleg = avleg
        if not obj.rvleg:
            obj.rvleg = rvleg
        if obj.Nominal is None:
            try:
                nom_get = Nominal.objects.get(name_nom_id=nom)
                obj.Nominal = nom_get
            except ObjectDoesNotExist:
                pass

        if not obj.Mzstaette:
            try:
                mint_get = Mzstaette.objects.get(name_nom_id=mint)
                obj.Mzstaette = mint_get
            except ObjectDoesNotExist:
                pass

        if "numismatics.org" in obj.link:
            obj.Muenzstand = Muenzstand.objects.get(id=424)

        for praegeherr in praegeherr_list:
            if praegeherr:
                try:
                    with transaction.atomic():
                        p1person = Person.objects.filter(name_nom_id=praegeherr).first()
                        p1 = Mztyp_Person(Mztyp=obj, idfk_Person=p1person, idfk_PersonFunktion=PersonFunktion.objects.get(id=1), appears_on_rev=0)
                        p1.save()
                except IntegrityError:
                    pass
        
        for avpor in avpor_list:
            if avpor:
                try:
                    with transaction.atomic():
                        p3person = Person.objects.filter(name_nom_id=avpor).first()
                        p3 = Mztyp_Person(Mztyp=obj, idfk_Person=p3person, idfk_PersonFunktion=PersonFunktion.objects.get(id=2), appears_on_rev=0)
                        p3.save()
                except IntegrityError:
                    pass
        
        for rvpor in rvpor_list:
            if rvpor:
                try:
                    with transaction.atomic():
                        p3person = Person.objects.filter(name_nom_id=rvpor).first()
                        p3 = Mztyp_Person(Mztyp=obj, idfk_Person=p3person, idfk_PersonFunktion=PersonFunktion.objects.get(id=2), appears_on_rev=1)
                        p3.save()
                except IntegrityError:
                    pass

        # Save object
        try:
            obj.save()
            return True, "Daten erfolgreich verarbeitet"
        except Exception as e:
            traceback_message = traceback.format_exc()
            message_user(request, f"Error saving object: {e}\nTraceback:\n{traceback_message}")
            return False, f"Fehler bei der Verarbeitung: {e}"

    except Exception as e:
        print(f"Fehler bei der Verarbeitung: {e}")
        return False, f"Fehler bei der Verarbeitung: {e}"

class MuenztypAdmin(ImportExportModelAdmin, CloneModelAdmin,):

    resource_class = MuenztypImport

    include_duplicate_object_link = True
    search_fields = ('muenztyptitel','titel','Mzstaette__name')
    list_display = ('id', 'muenztyptitel', 'titel', 'dat_verb', 'dat_von', 'dat_bis', 'Nominal', 'Metall', 'Mzstaette', 'Muenzstand',)
    list_select_related = False  # Wird vollständig durch get_queryset() gesteuert
    ordering=['-id']
    # LÖSUNG 1: Mzstaette aus list_editable entfernen da es in raw_id_fields ist
    list_editable = ('muenztyptitel', 'titel', 'dat_verb', 'dat_von', 'dat_bis')
    # LÖSUNG 2: Mzstaette in raw_id_fields belassen für bessere Performance
    raw_id_fields = ['Mzstaette']
    
    # PERFORMANCE: Kein teures COUNT(*) über die gesamte Tabelle
    show_full_result_count = False
    list_per_page = 50

    actions_on_top = True
    actions_on_bottom = True
    actions = ['material_vom_nominal', 'verkupfern', 'nummisieren', 'vermessingere', 'transpadana']
    save_as = False
    save_on_top = True
    inlines = (Mztyp_PersonInline, Typ_RefInline, Mztyp_SchlagwortInline, Mztyp_WappenInline, Mztyp_interne_AnmerkungInline)
    autocomplete_fields = ['av_bildtyp','rv_bildtyp', 'av_beizeichen', 'rv_beizeichen', 'Konkordanz', 'rand', 'auflage']
    radio_fields = {'workflow': admin.HORIZONTAL}

    fieldsets = (
        (None, {
            'fields': (
                ('id','workflow'),
                ('muenztyptitel','titel'),
                ('Ref', 'nummer', 'nach', 'variante',),
                'link',
                'Konkordanz',
                'Objekttyp',
                ('Muenzstand', 'Reichskreis',),
                ('Mzstaette', 'region'),
                ('Nominal', 'Metall', 'Herstellung',),
                #'Obj_PersonInline',
                ('dat_verb', 'dat_von', 'dat_bis'),
                ('auflage', 'ausgabedatum', 'beschlussdatum'),
            ),
        }),
        ('Anmerkung', {
            'classes': ('collapse',),
            'fields': (
                'anmerkung',
            ),
        }),
        ('Vorderseite', {
            'classes': ('wide',),
            'fields': (
                'avleg', 'av_bildtyp',
                ('av_beizeichen','av_bildrand'),
            ),
        }),
        ('Rückseite', {
            'classes': ('wide',),
            'fields': (
                'rvleg', 'rv_bildtyp',
                ('rv_beizeichen','rv_bildrand'),
            ),
        }),
        ('Rand', {
            'classes': ('wide',),
            'fields': (
                'rand',
            ),
        }),
    )
    

    readonly_fields = ('id',)
    
    def ObjBezeichen(self, obj):
        # Entfernt da es zusätzliche Queries verursacht und nicht verwendet wird
        return ""
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def verkupfern(self, request, queryset):
        queryset.update(Metall="9")
    verkupfern.short_description = "zu Kupfer machen"
    
    def nummisieren(self, request, queryset):
        queryset.update(Nominal="492")
    nummisieren.short_description = "zu Nummus machen"

    def vermessingere(self, request, queryset):
        queryset.update(Metall="5")
    vermessingere.short_description = "zu Messing machen"
    
    def material_vom_nominal(self, request, queryset):
        betroffene = queryset.filter(
            Metall__isnull=True,
            Nominal__isnull=False,
            Nominal__material__isnull=False,
        ).select_related('Nominal__material')

        zu_aktualisieren = []
        for mt in betroffene:
            mt.Metall = mt.Nominal.material
            zu_aktualisieren.append(mt)

        if zu_aktualisieren:
            Muenztyp.objects.bulk_update(zu_aktualisieren, ['Metall'], batch_size=500)

        anzahl = len(zu_aktualisieren)
        if anzahl:
            modeladmin_msg = f"{anzahl} Münztyp(en) aktualisiert: Material wurde vom Nominal übernommen."
            self.message_user(request, modeladmin_msg)
        else:
            self.message_user(
                request,
                "Keine passenden Münztypen gefunden (ohne Material, mit Nominal das Material hat).",
                level=messages.WARNING,
            )
    material_vom_nominal.short_description = "Material vom Nominal übernehmen (nur ohne Material)"

    def transpadana(self, request, queryset):
        queryset.update(region="210")
    transpadana.short_description = "nach Transpadana"

    
    
    def download_infos(self, request, obj, post_url_continue=None):
        success, message = process_download_infos(obj)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message) 

        # Weiterleitung
        opts = obj._meta
        obj_url = reverse(
            'admin:%s_%s_change' % (opts.app_label, opts.model_name),
            args=(quote(obj.pk),),
            current_app=self.admin_site.name,
        )

        if post_url_continue is None:
            post_url_continue = obj_url
        else:
            post_url_continue = "default_url"  # Ihre Standard-URL

        return HttpResponseRedirect(post_url_continue)
    

    def response_change(self, request, obj):
        if "_download_infos" in request.POST:
            return self.download_infos(request, obj)
        return super().response_change(request, obj)    

    list_filter = (
        ('workflow', RelatedDropdownFilter),
        ('Reichskreis', RelatedDropdownFilter),
        ('Nominal', RelatedDropdownFilter),
        ('Metall', RelatedDropdownFilter),
        ('Ref', RelatedDropdownFilter),
        )
    def get_person(self, obj):
        return obj.Ppl.name
    get_person.short_description = 'Person'

    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super(MuenztypAdmin, self).formfield_for_dbfield(db_field, **kwargs)
        return formfield

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if _is_admin_autocomplete_request(request):
            return qs.only('id', 'muenztyptitel', 'titel', 'Mzstaette_id')
        
        # PERFORMANCE: Unterschiedliche Querysets für Liste vs. Detail
        if request.resolver_match and request.resolver_match.url_name and request.resolver_match.url_name.endswith('_changelist'):
            return qs.select_related(
                'Nominal', 'Metall', 'Mzstaette', 'Muenzstand',
                'Ref', 'workflow',
            )
        else:
            # Detailansicht: Alle FKs laden
            return qs.select_related(
                'Nominal', 'Metall', 'Mzstaette', 'Muenzstand', 'Reichskreis',
                'Ref', 'workflow', 'rv_beizeichen', 'av_bildtyp', 'av_beizeichen',
                'av_bildrand', 'rv_bildtyp', 'rv_bildrand', 'rand',
                'Objekttyp', 'Herstellung', 'region', 'variante', 'auflage',
            )

    def get_form(self, request, obj=None, **kwargs):
        form = super(MuenztypAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['muenztyptitel'].widget.attrs['style'] = 'width: 60em;'
        form.base_fields['Konkordanz'].widget.attrs['style'] = 'width: 80em;'
        konkordanz_initial = self._get_konkordanz_initial_from_request(request, obj)
        if konkordanz_initial:
            form.base_fields['Konkordanz'].initial = konkordanz_initial
        form.base_fields['titel'].widget.attrs['style'] = 'width: 60em;'
        form.base_fields['av_bildtyp'].widget.attrs['style'] = 'width: 80em;'
        form.base_fields['rv_bildtyp'].widget.attrs['style'] = 'width: 80em;'
        
        
        return form

    def _get_konkordanz_initial_from_request(self, request, obj=None):
        raw_values = []
        for param_name in ('Konkordanz', 'konkordanz', 'konkordanz_id'):
            raw_values.extend(request.GET.getlist(param_name))

        konkordanz_ids = []
        seen_ids = set()
        current_id = getattr(obj, 'pk', None)

        for raw_value in raw_values:
            parts = [part.strip() for part in str(raw_value or '').replace(';', ',').split(',')]
            for value in parts:
                if not value:
                    continue
                match = None
                if value.isdigit():
                    match = Muenztyp.objects.filter(pk=int(value)).only('id').first()
                if match is None:
                    match = Muenztyp.objects.filter(
                        Q(muenztyptitel__iexact=value) | Q(titel__iexact=value)
                    ).only('id').first()
                if match is None:
                    match = Muenztyp.objects.filter(
                        Q(muenztyptitel__icontains=value) | Q(titel__icontains=value)
                    ).only('id').first()

                match_id = getattr(match, 'pk', None)
                if match_id and match_id != current_id and match_id not in seen_ids:
                    seen_ids.add(match_id)
                    konkordanz_ids.append(match_id)

        return konkordanz_ids

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

class AuflageAdmin(admin.ModelAdmin):
    search_fields = ['name']
    ordering = ['name']
   
class ObjResource(resources.ModelResource):
    Slg__name = Field(attribute='Slg__name', column_name='Sammlung')
    SlgTeil__name = Field(attribute='SlgTeil__name', column_name='Sammlungsteil')
    durchmesser = Field(attribute='durchmesser', column_name='Durchmesser in mm')
    gewicht = Field(attribute='gewicht', column_name='Gewicht in g')
    stempelstellung = Field(attribute='stempelstellung', column_name='Stempelstellung in h')
    abnutzung = Field(attribute='abnutzung', column_name='Abnutzung')
    faelschung = Field(attribute='faelschung', column_name='Fälschung?')
    Typ_unsicher = Field(attribute='Typ_unsicher', column_name='Typ_unsicher?')
    #Typ__muenztyptitel = Field(attribute='Typ__muenztyptitel', column_name='Zitat')
    Typ__titel = Field(attribute='Typ__titel', column_name='Titel des Objektes')
    Typ__Herstellung__name = Field(attribute='Typ__Herstellung__name', column_name='Herstellung')
    Typ__Reichskreis__name = Field(attribute='Typ__Reichskreis__name', column_name='Reichskreis')
    Typ__Muenzstand__name = Field(attribute='Typ__Muenzstand__name', column_name='Münzstand')
    Typ__Nominal__name = Field(attribute='Typ__Nominal__name', column_name='Nominal')
    Typ__Metall__name = Field(attribute='Typ__Metall__name', column_name='Metall')
    Typ__Mzstaette__name = Field(attribute='Typ__Mzstaette__name', column_name='Münzstätte')
    Typ__region__name = Field(attribute='Typ__region__name', column_name='Region')
    Typ__dat_von = Field(attribute='Typ__dat_von', column_name='Datierung von')
    Typ__dat_bis = Field(attribute='Typ__dat_bis', column_name='Datierung bis')
    Typ__dat_verb = Field(attribute='Typ__dat_verb', column_name='Datierung')
    Typ__avleg = Field(attribute='Typ__avleg', column_name='Av.-Leg.')
    Typ__av_bildtyp__name = Field(attribute='Typ__av_bildtyp__name', column_name='Av.-Beschreibung')
    Typ__av_beizeichen__name = Field(attribute='Typ__av_beizeichen__name', column_name='Av.-Beizeichen')
    #Typ__av_offizin__name = Field(attribute='Typ__av_offizin__name', column_name='Av.-Offizin')
    Typ__rvleg = Field(attribute='Typ__rvleg', column_name='Rv.-Leg.')
    Typ__rv_bildtyp__name = Field(attribute='Typ__rv_bildtyp__name', column_name='Rv.-Beschreibung')
    Typ__rv_beizeichen__name = Field(attribute='Typ__rv_beizeichen__name', column_name='Rv.-Beizeichen')
    #Typ__rv_offizin__name = Field(attribute='Typ__rv_offizin__name', column_name='Rv.-Offizin')
    #Konkordanzen = Field(column_name='Konkordanzen', attribute=None)  # Attribut ist None, da dies ein benutzerdefiniertes Feld ist
    Zitate = Field(column_name='Zitat', attribute=None)  # Attribut ist None, da dies ein benutzerdefiniertes Feld ist
    
    class Meta:
        model = Obj
        # fields = ('id', 'invnr', 'Slg__name','SlgTeil__name', 'Objekttyp__name', 'Metall__name', 'Typ__muenztyptitel', 'Typ__titel')
        fields = ('id', 'invnr', 'Slg__name','SlgTeil__name', 'durchmesser','gewicht','stempelstellung', 'abnutzung', 'faelschung', 'Typ_unsicher', 'Zitate', 'Typ__titel', 'Typ__Herstellung__name', 'Typ__Reichskreis__name', 'Typ__Muenzstand__name', 'Typ__Nominal__name', 'Typ__Metall__name', 'Typ__Mzstaette__name', 'Typ__region__name', 'Typ__dat_von', 'Typ__dat_bis', 'Typ__dat_verb', 'Typ__avleg', 'Typ__av_bildtyp__name', 'Typ__av_beizeichen__name','Typ__rvleg', 'Typ__rv_bildtyp__name', 'Typ__rv_beizeichen__name', 'rv_offizin__name')
        export_order = ('id', 'invnr', 'Slg__name','SlgTeil__name', 'durchmesser','gewicht','stempelstellung', 'abnutzung', 'faelschung', 'Typ_unsicher', 'Zitate', 'Typ__titel', 'Typ__Herstellung__name', 'Typ__Reichskreis__name', 'Typ__Muenzstand__name', 'Typ__Nominal__name', 'Typ__Metall__name', 'Typ__Mzstaette__name', 'Typ__region__name', 'Typ__dat_von', 'Typ__dat_bis', 'Typ__dat_verb', 'Typ__avleg', 'Typ__av_bildtyp__name', 'Typ__av_beizeichen__name', 'Typ__rvleg', 'Typ__rv_bildtyp__name', 'Typ__rv_beizeichen__name', 'rv_offizin__name')
        name = "Export der Objekte"

    def dehydrate_Zitate(self, obj):
        if obj.Typ:
            konkordanz_list = [str(konkordanz) for konkordanz in obj.Typ.Konkordanz.all()]
            muenztyptitel = obj.Typ.muenztyptitel if obj.Typ.muenztyptitel else ''

            if konkordanz_list:
                konkordanz_str = '; '.join(konkordanz_list)
                return f"{muenztyptitel}; {konkordanz_str}"
            else:
                return muenztyptitel
        return ''

class SafeField(Field):
    def get_value(self, obj):
        try:
            return super().get_value(obj)
        except Fund.DoesNotExist:
            return None

class CachedForeignKeyWidget(ForeignKeyWidget):
    """
    Ein ForeignKeyWidget, das die Datenbankabfragen zwischenspeichert,
    um die Import-Geschwindigkeit drastisch zu verbessern.
    """
    def __init__(self, model, field='pk', *args, **kwargs):
        super().__init__(model, field=field, *args, **kwargs)
        self._cache = {}

    def clean(self, value, row=None, *args, **kwargs):
        # In older django-import-export versions, empty_values checking is done by the Field.
        # We can just do a basic check here.
        if value is None or value == '':
            return None

        if value not in self._cache:
            # Query the database only once per unique value
            self._cache[value] = super().clean(value, row, *args, **kwargs)
            
        return self._cache[value]
   
class ObjImport(resources.ModelResource):
    Slg = fields.Field(
        column_name='Sammlung',
        attribute='Slg',
        widget=CachedForeignKeyWidget(Slg, field='name'))
    
    SlgTeil = fields.Field(
        column_name='Sammlungsteil',
        attribute='SlgTeil',
        widget=CachedForeignKeyWidget(SlgTeil, field='name'))
    
    Typ = fields.Field(
        column_name='Münztyp',
        attribute='Typ',
        widget=CachedForeignKeyWidget(Muenztyp, field='muenztyptitel'))

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        from slg.signals import disable_mtoa_sync
        disable_mtoa_sync()

        self._instance_cache = None
        self._import_invnr_values = set()
        self._import_slg_names = set()

        try:
            invnr_col = self.fields['invnr'].column_name
            slg_col = self.fields['Slg'].column_name

            for row_dict in dataset.dict:
                inv = row_dict.get(invnr_col, '')
                slg = row_dict.get(slg_col, '')
                if inv:
                    self._import_invnr_values.add(str(inv).strip())
                if slg:
                    self._import_slg_names.add(str(slg).strip())

            if self._import_slg_names and self._import_invnr_values:
                slg_map = {s.name: s for s in Slg.objects.filter(name__in=self._import_slg_names)}
                slg_ids = [s.id for s in slg_map.values()]

                if slg_ids:
                    self._instance_cache = {}
                    qs = Obj.objects.filter(
                        Slg_id__in=slg_ids,
                        invnr__in=self._import_invnr_values
                    ).select_related('Slg', 'SlgTeil', 'Typ')
                    for obj in qs:
                        key = (str(obj.invnr).strip(), obj.Slg_id)
                        self._instance_cache.setdefault(key, []).append(obj)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Pre-Cache konnte nicht erstellt werden, verwende Standard-Lookup",
                exc_info=True
            )
            self._instance_cache = None

        super().before_import(dataset, using_transactions, dry_run, **kwargs)

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        from slg.signals import enable_mtoa_sync
        enable_mtoa_sync()

        if not dry_run and self._import_slg_names and self._import_invnr_values:
            try:
                slg_ids = list(
                    Slg.objects.filter(name__in=self._import_slg_names)
                    .values_list('id', flat=True)
                )
                if slg_ids:
                    imported_pks = list(
                        Obj.objects.filter(
                            Slg_id__in=slg_ids,
                            invnr__in=self._import_invnr_values
                        ).values_list('pk', flat=True)
                    )
                    if imported_pks:
                        from .mtoa_sync import sync_objs_to_mtoa
                        for i in range(0, len(imported_pks), 500):
                            sync_objs_to_mtoa(imported_pks[i:i + 500])
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "MTOA Batch-Sync nach Import fehlgeschlagen"
                )

        super().after_import(dataset, result, using_transactions, dry_run, **kwargs)

    class Meta:
        model = Obj
        fields = ('id', 'invnr', 'Slg', 'SlgTeil', 'Typ', 'TempTyp', 'durchmesser', 'gewicht', 'stempelstellung', 'abnutzung',)
        export_order = fields
        name = "Export der Objekte"
        skip_unchanged = True
        report_skipped = True
        use_bulk = True
        batch_size = 500
    
    def get_import_id_fields(self):
        return ['invnr', 'Slg']
    
    def before_import_row(self, row, **kwargs):
        sammlung_name = row.get('Sammlung', '')
        if sammlung_name == 'Fundmünzprojekt':
            self._current_id_fields = ['invnr', 'Slg', 'SlgTeil']
        else:
            self._current_id_fields = ['invnr', 'Slg']
    
    def get_or_init_instance(self, instance_loader, row):
        if self._instance_cache is not None:
            try:
                invnr_val = self.fields['invnr'].clean(row)
                if invnr_val:
                    invnr_val = str(invnr_val).strip()
            except Exception:
                invnr_val = None

            try:
                slg_obj = self.fields['Slg'].clean(row)
            except Exception:
                slg_obj = None

            if slg_obj and invnr_val:
                key = (invnr_val, slg_obj.id)
                candidates = self._instance_cache.get(key, [])

                if candidates:
                    if hasattr(self, '_current_id_fields') and 'SlgTeil' in self._current_id_fields:
                        try:
                            slgteil_obj = self.fields['SlgTeil'].clean(row)
                        except Exception:
                            slgteil_obj = None
                        slgteil_id = slgteil_obj.id if slgteil_obj else None
                        for obj in candidates:
                            if obj.SlgTeil_id == slgteil_id:
                                return obj, False
                    else:
                        return candidates[0], False

            return self.Meta.model(), True

        # Fallback ohne Cache
        if hasattr(self, '_current_id_fields'):
            original_id_fields = self.get_import_id_fields()
            self.Meta.import_id_fields = self._current_id_fields
            try:
                return super().get_or_init_instance(instance_loader, row)
            finally:
                self.Meta.import_id_fields = original_id_fields
        
        return super().get_or_init_instance(instance_loader, row)

class UserActionListFilter(admin.SimpleListFilter):
    title = 'Benutzer'
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        # Holen Sie sich den ContentType für das Obj-Modell
        obj_content_type = ContentType.objects.get_for_model(Obj)
        
        # Filtern Sie die LogEntry-Einträge für das Obj-Modell und extrahieren Sie die Benutzer
        users = User.objects.filter(pk__in=LogEntry.objects.filter(content_type=obj_content_type).values_list('user', flat=True).distinct())
        return [(user.pk, user.username) for user in users]

    def queryset(self, request, queryset):
        if self.value():
            obj_content_type = ContentType.objects.get_for_model(Obj)
            # Holen Sie sich die IDs der Obj-Objekte, die vom gewählten Benutzer geändert wurden
            obj_ids = LogEntry.objects.filter(content_type=obj_content_type, user__id=self.value()).values_list('object_id', flat=True)
            return queryset.filter(pk__in=obj_ids)
        return queryset
    
class SlgFilter(admin.SimpleListFilter):
    title = 'Sammlung'
    parameter_name = 'slg'

    def lookups(self, request, model_admin):
        return Slg.objects.values_list('id', 'name')

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(Slg__id=self.value())
class MetallVorhandenFilter(admin.SimpleListFilter):
    title = 'Material vorhanden'
    parameter_name = 'metall_vorhanden'

    def lookups(self, request, model_admin):
        return (
            ('ja', 'Ja – Material gesetzt'),
            ('nein', 'Nein – Material leer'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'ja':
            return queryset.filter(Metall__isnull=False)
        if self.value() == 'nein':
            return queryset.filter(Metall__isnull=True)


def material_von_nominal_uebernehmen(modeladmin, request, queryset):
    """
    Admin-Action: Übernimmt das Material/Metall vom Nominal-Eintrag
    für Objekte, die:
    - keinen Typ haben (Typ ist leer)
    - ein Nominal haben (idfk_Nominal ist gesetzt)
    - kein Metall/Material haben (Metall ist leer)
    - deren Nominal ein Material hinterlegt hat
    """
    # Filtere nur die Objekte, die die Kriterien erfüllen
    betroffene = queryset.filter(
        Typ__isnull=True,
        idfk_Nominal__isnull=False,
        Metall__isnull=True,
        idfk_Nominal__material__isnull=False,
    ).select_related('idfk_Nominal', 'idfk_Nominal__material')
    
    # PERFORMANCE: bulk_update statt einzelner save() pro Objekt
    zu_aktualisieren = []
    for obj in betroffene:
        obj.Metall = obj.idfk_Nominal.material
        zu_aktualisieren.append(obj)
    
    if zu_aktualisieren:
        Obj.objects.bulk_update(zu_aktualisieren, ['Metall'], batch_size=500)
    anzahl = len(zu_aktualisieren)
    
    if anzahl:
        modeladmin.message_user(
            request,
            f"{anzahl} Objekt(e) aktualisiert: Material wurde vom Nominal übernommen."
        )
    else:
        modeladmin.message_user(
            request,
            "Keine passenden Objekte gefunden (ohne Typ, mit Nominal, ohne Material, Nominal hat Material).",
            level=messages.WARNING
        )

material_von_nominal_uebernehmen.short_description = "Material vom Nominal übernehmen (nur ohne Typ, ohne Material)"


def material_von_muenztyp_uebernehmen(modeladmin, request, queryset):
    """
    Admin-Action: Übernimmt das Material/Metall vom zugewiesenen Münztyp
    für Objekte, die einen Typ haben aber kein eigenes Material.
    """
    betroffene = queryset.filter(
        Typ__isnull=False,
        Metall__isnull=True,
        Typ__Metall__isnull=False,
    ).select_related('Typ__Metall')

    zu_aktualisieren = []
    for obj in betroffene:
        obj.Metall = obj.Typ.Metall
        zu_aktualisieren.append(obj)

    if zu_aktualisieren:
        Obj.objects.bulk_update(zu_aktualisieren, ['Metall'], batch_size=500)
    anzahl = len(zu_aktualisieren)

    if anzahl:
        modeladmin.message_user(
            request,
            f"{anzahl} Objekt(e) aktualisiert: Material wurde vom Münztyp übernommen."
        )
    else:
        modeladmin.message_user(
            request,
            "Keine passenden Objekte gefunden (mit Typ, ohne Material, Typ hat Material).",
            level=messages.WARNING
        )

material_von_muenztyp_uebernehmen.short_description = "Material vom Münztyp übernehmen (nur mit Typ, ohne Material)"


class ObjAdmin(ImportExportModelAdmin):
    #form = ObjForm
    # resource_class = ObjResource
    resource_class = ObjImport
    # change_list_template = 'admin/slg/obj/change_list.html'

    search_fields = ('titel','invnr','idfk_Mzstaette__name', 'Typ__muenztyptitel', 'Typ__titel')
    list_select_related = ('Slg', 'SlgTeil', 'Typ', 'idfk_Nominal','Metall',)
    list_display = ('id', 'invnr', 'SlgTeil', 'Münztitel','Typ','durchmesser', 'gewicht', 'stempelstellung', 'abnutzung', 'idfk_Nominal','Metall',)
    ordering=['-id']
    list_editable = ('invnr', 'durchmesser', 'gewicht', 'stempelstellung','abnutzung')
    
    # Reduziert doppelte COUNT-Abfragen
    show_full_result_count = False
    list_per_page = 50
    
    actions_on_top = True
    actions_on_bottom = True
    save_as = True
    save_on_top = True
    inlines = (Obj_PersonInline, Obj_RefInline, FundInline, Obj_interneAnmerkungInline,)
    
    # BENUTZERFREUNDLICHERE LÖSUNG: Mehr autocomplete_fields statt raw_id_fields
    autocomplete_fields = [
        'Typ',
        'sekundaere_Merkmale', 
        'Herstellungsmerkmale',
        'Untertyp',
        'av_beizeichen', 
        'rv_beizeichen',
        'av_bildtyp',
        'rv_bildtyp', 
        'idfk_Muenzstand', 
        'idfk_Nominal', 
        'rand',
        'av_offizin',           
        'rv_offizin',           
        'av_offizin_symbol',    
        'rv_offizin_symbol',    
        'Objekttyp',            
        'idfk_Mzstaette',       
        'region',               
        'av_bildrand',          
        'rv_bildrand',          
        'faelschung',
        'idfk_Herstellung',     
        'Metall',               
        'Slg',                  
        'SlgTeil',              
        'workflow',             # NEU: Von raw_id_fields verschoben!
        'pakete',               # NEU: Paket-Autocomplete
    ]
    
    # Jetzt ist raw_id_fields leer oder kann ganz entfernt werden
    # raw_id_fields = ()
    
    actions = ['export_coins', 'create_coin_labels', 'create_catalog', material_von_nominal_uebernehmen, material_von_muenztyp_uebernehmen, 'sync_mtoa_selected']
    
    fieldsets = (
        (None, {
            'fields': (
                ('invnr','workflow'),
                ('Slg', 'SlgTeil'),
                'pakete',
                ('Typ', 'Typ_unsicher', 'TempTyp',),
                ('Untertyp', 'Untertyp_unsicher'),
                ('faelschung', 'Metall', 'idfk_Herstellung', ),
                ('Herstellungsmerkmale','sekundaere_Merkmale',),
                ('gewicht', 'durchmesser', 'stempelstellung'),
                'abnutzung',
                ('av_beizeichen', 'av_offizin', 'av_offizin_symbol'),
                ('rv_beizeichen', 'rv_offizin', 'rv_offizin_symbol'),
            ),
        }),
        ('Beschreibung, falls das Objekt eine Fälschung oder keinem Typ zugewiesen werden kann.', {
            'classes': ('collapse',),
            'fields': (
                'titel',
                'Objekttyp',
                'idfk_Muenzstand',
                ('idfk_Mzstaette', 'region'),
                'idfk_Nominal',
                ('dat_verb', 'dat_von', 'dat_bis'),
                'avleg', 'av_bildtyp',
                ('av_bildrand'),
                'rvleg', 'rv_bildtyp',
                ('rv_bildrand'),
                'rand',
                'anmerkung',
            ),
        }),
    )
    


    def get_queryset(self, request):
        if _is_admin_autocomplete_request(request):
            return super().get_queryset(request).only('id', 'invnr', 'titel', 'Typ_id')

        resolver_match = getattr(request, 'resolver_match', None)
        url_name = getattr(resolver_match, 'url_name', '') or ''
        # OPTIMIERT: Unterschiedliche Querysets für Liste vs. Detail
        if url_name.endswith('_changelist'):
            # Für die Listenansicht: Nur die Felder laden, die wirklich benötigt werden
            queryset = super().get_queryset(request).select_related(
                'Slg',
                'SlgTeil', 
                'Typ',
                'idfk_Nominal',
                'Metall',
            )
            return queryset
        else:
            # Für Detailansicht (Formulare): Alle Felder laden
            queryset = super().get_queryset(request).select_related(
                'Slg',
                'SlgTeil',
                'Typ',
                'idfk_Muenzstand',
                'idfk_Herstellung',
                'idfk_Nominal',
                'Metall',
                'faelschung',
                'idfk_Mzstaette',
                'region',
                'Untertyp',
                'av_bildtyp',
                'av_beizeichen',
                'av_offizin',
                'av_bildrand',
                'rv_bildtyp',
                'rv_beizeichen',
                'rv_offizin',
                'rv_bildrand',
                'rand',
                'workflow',
                'av_offizin_symbol',
                'rv_offizin_symbol'
            ).prefetch_related(
                'Herstellungsmerkmale',
                'sekundaere_Merkmale',
                'pakete',
            )
            return queryset

    # ... rest of existing code ...

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if object_id and '_download_legenden' in request.POST:
            obj = self.get_object(request, object_id)
            if obj and obj.Typ:
                obj.avleg = obj.Typ.avleg
                obj.rvleg = obj.Typ.rvleg
                obj.save()
                self.message_user(request, "Die Legenden vom Münztyp wurden übernommen.")
                redirect_url = reverse('admin:slg_obj_change', args=(object_id,))
                
                # Speichern des Filters aus der aktuellen URL
                if '_changelist_filters' in request.GET:
                    redirect_url += '?' + request.GET.urlencode()

                return redirect(redirect_url)

        return super().changeform_view(request, object_id, form_url, extra_context)
        # return super().response_change(request, obj, post_url_continue=post_url_continue)
        # return super().response_change(request, obj)
        #return HttpResponseRedirect("../%s" % obj.id)
        # return HttpResponseRedirect(post_url_continue)

    # def abbildungen(self, obj):
    #     #https://www.univie.ac.at/stiftheiligenkreuz/Hauptsammlung/thumbails/02463a00.webp
    #     #return mark_safe('<img src="{}/thumbnails/{}a00.webp"/>'.format(obj.Slgteil, obj.img))
    #     if obj.Slg.id == 2:
    #         url = '<img src="'+obj.Slg.bildurl+'/thumbnails/'+obj.invnr+'a00.webp" width="300"/><img src="'+obj.Slg.bildurl+'/thumbnails/'+obj.invnr+'r00.webp" width="300"/>'
    #     else:
    #         url = '<img src="https://www.univie.ac.at/stiftheiligenkreuz/Hauptsammlung/thumbnails/{}a00.webp" width="300"/><img src="https://www.univie.ac.at/stiftheiligenkreuz/Hauptsammlung/thumbnails/{}r00.webp" width="300"/>'.format(obj.img, obj.img)
    #     return mark_safe(url)

    #entfernt den Löschenbutton
    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_form(self, request, obj=None, **kwargs):
        form = super(ObjAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['Typ'].widget.attrs['style'] = 'width: 45em;'
        form.base_fields['av_bildtyp'].widget.attrs['style'] = 'width: 80em;'
        form.base_fields['rv_bildtyp'].widget.attrs['style'] = 'width: 80em;'
        return form

    def formfield_for_dbfield(self, db_field, **kwargs):
        request = kwargs['request']
        formfield = super(ObjAdmin, self).formfield_for_dbfield(db_field, **kwargs)
        if db_field.name in self.list_editable:
            cache_attr_name = 'choices_cache_%s' % db_field.name
            choices_cache = getattr(request, cache_attr_name, None)
            if choices_cache is not None:
                formfield.choices = choices_cache
            else:
                if hasattr(formfield, 'choices'):
                    setattr(request, cache_attr_name, formfield.choices)
        return formfield
        
    list_filter = (
        SlgFilter,
        ('SlgTeil', RelatedDropdownFilter),
        ('pakete', RelatedDropdownFilter),
        ('Typ', admin.BooleanFieldListFilter),
        MetallVorhandenFilter,
        ('workflow', RelatedDropdownFilter),
        )
    def get_person(self, obj):
        return obj.Ppl.name
    get_person.short_description = 'Person'

    def Münztitel(self, obj):
        return obj.Typ.titel if obj.Typ else obj.titel
    Münztitel.short_description = 'Münztitel'
    Münztitel.admin_order_field = 'Typ__titel'
    
    def export_coins(self, request, queryset):
        from .views import prepare_coin_data_export  # Importieren der Funktion
        # Dedupliziere das queryset mit values('pk').distinct()
        distinct_pks = queryset.values('pk').distinct().values_list('pk', flat=True)
        # Erstelle ein neues queryset nur mit den eindeutigen PKs
        deduplicated_queryset = Obj.objects.filter(pk__in=distinct_pks)
        # Füge alle notwendigen select_related und prefetch_related hinzu
        deduplicated_queryset = deduplicated_queryset.select_related(
            'Slg',
            'SlgTeil',
            'Typ',
            'idfk_Nominal',
            'Metall',
            'idfk_Mzstaette',
            'region',
            'av_bildtyp',
            'rv_bildtyp',
            'av_beizeichen',
            'rv_beizeichen',
            'av_offizin',
            'rv_offizin'
        ).prefetch_related(
            'Herstellungsmerkmale',
            'sekundaere_Merkmale',
            'Ppl',
            'idfk_Ref'
        )
        response = prepare_coin_data_export(deduplicated_queryset)  # Aufruf der Funktion mit den ausgewählten Datensätzen
        return response  # Rückgabe der HttpResponse für den Datei-Download
    
    export_coins.short_description = "Münzliste exportieren"  # Beschreibung der Aktion

    def sync_mtoa_selected(self, request, queryset):
        """Admin-Aktion: Ausgewählte Objekte in MuenztypObjektAnzeige synchronisieren."""
        from .mtoa_sync import sync_objs_to_mtoa

        obj_ids = list(queryset.values_list('pk', flat=True))
        created, updated = sync_objs_to_mtoa(obj_ids)

        self.message_user(
            request,
            f"{created + updated} Objekt(e) in MTOA synchronisiert "
            f"({created} neu, {updated} aktualisiert)."
        )
    sync_mtoa_selected.short_description = "MTOA aktualisieren (Anzeige-Tabelle)"

    def create_coin_labels(self, request, queryset):
        from .views import prepare_coin_labels_html
        # Dedupliziere das queryset
        distinct_pks = queryset.values('pk').distinct().values_list('pk', flat=True)
        deduplicated_queryset = Obj.objects.filter(pk__in=distinct_pks)
        
        response = prepare_coin_labels_html(deduplicated_queryset)
        return response

    create_coin_labels.short_description = "Unterlagszettel erstellen"

    def create_catalog(self, request, queryset):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        # Sammle alle Object-IDs
        distinct_pks = queryset.values('pk').distinct().values_list('pk', flat=True)
        obj_ids = ','.join(map(str, distinct_pks))
        
        # Weiterleitung zur Katalog-Sortierung
        url = reverse('catalog_sort_titles') + f'?obj_ids={obj_ids}'
        return HttpResponseRedirect(url)

    create_catalog.short_description = "Katalog erstellen"

    def save_model(self, request, obj, form, change):
        from .signals import disable_mtoa_sync, enable_mtoa_sync
        disable_mtoa_sync()
        try:
            super().save_model(request, obj, form, change)
        except Exception:
            enable_mtoa_sync()
            raise

    def save_related(self, request, form, formsets, change):
        from .signals import enable_mtoa_sync
        from .mtoa_sync import sync_objs_to_mtoa
        try:
            super().save_related(request, form, formsets, change)
        finally:
            enable_mtoa_sync()
        sync_objs_to_mtoa([form.instance.pk])

    class Media:
        js = ('Djangoprojekt/js/admin.js',)

@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    date_hierarchy = 'action_time'

    list_filter = [
        'user',
        'content_type',
        'action_flag'
    ]

    search_fields = [
        'object_repr',
    ]

    list_display = [
        'action_time',
        'user',
        'content_type',
        'object_link',
        'action_flag',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def object_link(self, obj):
        if obj.action_flag == DELETION:
            link = escape(obj.object_repr)
        else:
            ct = obj.content_type
    #date_hierarchy = ['history__history_date']
            link = '<a href="%s">%s</a>' % (
    #list_display = ('invnr', 'titel','durchmesser', 'gewicht', 'stempelstellung','get_mzstaette','freigabe',)
                reverse('admin:%s_%s_change' % (ct.app_label, ct.model), args=[obj.object_id]),
                escape(obj.object_repr),
            )
        return mark_safe(link)
    object_link.admin_order_field = "object_repr"
    #inlines = (Obj_PersonInline,)
    # inlines = (Obj_PersonInline, Obj_RefInline,Obj_interneAnmerkungInline,)
    # #inlines = (Obj_PersonInline,MzstaetteInline,)
    # #readonly_fields = ('image_tag',)
    # autocomplete_fields = ['Typ__Ref', 'rv_beizeichen']
    # radio_fields = {'workflow': admin.HORIZONTAL}
    object_link.short_description = "object"

class MyObjectsAdmin(admin.ModelAdmin,):
    #date_hierarchy = ['history__history_date']
    search_fields = ('titel','invnr','Typ__Mzstaette__name')
    #list_display = ('invnr', 'titel','durchmesser', 'gewicht', 'stempelstellung','get_mzstaette','freigabe',)
    list_display = ('id', 'invnr', 'Slg', 'SlgTeil','rv_beizeichen', 'rv_offizin', 'Typ', 'TempTyp', 'durchmesser', 'gewicht', 'stempelstellung',)
    ordering=['-id']
    list_editable = ('invnr', 'Typ', 'Slg', 'SlgTeil','rv_beizeichen', 'rv_offizin', 'durchmesser', 'gewicht', 'stempelstellung',)
    raw_id_fields = ('Slg','SlgTeil', "Typ",'rv_beizeichen', 'rv_offizin')
    
    #inlines = (Obj_PersonInline,)
    # inlines = (Obj_PersonInline, Obj_RefInline,Obj_interneAnmerkungInline,)
    # #inlines = (Obj_PersonInline,MzstaetteInline,)
    # #readonly_fields = ('image_tag',)
    # autocomplete_fields = ['Typ__Ref', 'rv_beizeichen']
    # radio_fields = {'workflow': admin.HORIZONTAL}
    actions_on_top = True
    actions_on_bottom = True
    save_as = True
    save_on_top = True
    show_full_result_count = False
    list_per_page = 50

    list_filter_related = True
    list_filter = (
        ('Slg', RelatedDropdownFilter),
        ('SlgTeil', RelatedDropdownFilter),
        ('Typ__Ref', RelatedDropdownFilter),
        ('Typ__workflow', admin.RelatedOnlyFieldListFilter),
        ('workflow', RelatedDropdownFilter),
        )
    
    actions = [actions.export_as_xls, actions.graph_queryset]
    
    actions = ['SlgHlHaupt',]
    
    
    def get_queryset(self, request):
        return super(MyObjectsAdmin,self).get_queryset(request).select_related('Slg','SlgTeil','Typ','rv_beizeichen', 'rv_offizin' )
    
    #entfernt den Löschenbutton

    def SlgHlHaupt(self, request, queryset):
        queryset.update(Slg="1", SlgTeil="2")
    SlgHlHaupt.short_description = "Objekte zu Hl gesellen"

    class Media:
        js = ('Djangoprojekt/js/admin.js',)

class StaatAdmin(admin.ModelAdmin,):
    search_fields = ('name',)

class PersonFunktionAdmin(ImportExportModelAdmin,):
    search_fields = ('name',)

class KatalogartAdmin(admin.ModelAdmin,):
    search_fields = ('name',)

class OnlineressourceInline(admin.TabularInline,):
    model = Onlineressource
    fields = ('name',)
    extra = 1

#derweil deaktiviert, da sonst bei zuvielen Einträgen man keine Änderungen beim Firmennamen vornehmen kann
class KatalogFirmenInline(admin.TabularInline,):
    model = KatalogFirmen
    # raw_id_fields = ("katalog",)
    #inlineformset_factory(Katalog_Firma, Katalog.firmen.through)
    autocomplete_fields = ['katalog','firma']

    #fk_name = 
    # fields = ('katalog__titel', 'katalogart','nummer', 'tag_von', 'tag_bis', 'monat', 'jahr',)
    # fields = ('katalog',)
    #exclude = ['avleg','avbeschr', 'rvleg', 'rvbeschr','av_img', 'rv_img']
    #exclude = ['idfk_Mzstaette', 'avleg','avbeschr', 'rvleg', 'rvbeschr','av_img', 'rv_img']
    #ordering = ("Mzstaette.name",)
    extra = 1
    # show_change_link = True
    
    # def has_delete_permission(self, request, obj=None):
    #     return true
    # def get_absolute_url(self):
    #     def view_on_site(self, obj):
    #         return reverse("Objekt", kwargs={"id": self.id})
    def get_queryset(self, request):
        return super(KatalogFirmenInline,self).get_queryset(request).select_related('katalog', 'firma')

        

class FirmaAdmin(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('id','name',)
    inlines = [OnlineressourceInline]
    # inlines = [KatalogFirmenInline,OnlineressourceInline]
    #exclude = ('firmen',)
    # def get_queryset(self, request):
    #         return super(FirmaAdmin,self).get_queryset(request).select_related('katalogfirmen_set',)
    # def get_queryset(self, request):
    #     queryset = super().get_queryset(request)
    #     queryset = queryset.prefetch_related('katalog')
    #     return queryset
    def formfield_for_dbfield(self, db_field, **kwargs):
        request = kwargs['request']
        formfield = super(FirmaAdmin, self).formfield_for_dbfield(db_field, **kwargs)
        if db_field.name in self.list_editable:
            cache_attr_name = 'choices_cache_%s' % db_field.name
            choices_cache = getattr(request, cache_attr_name, None)
            if choices_cache is not None:
                formfield.choices = choices_cache
            else:
                if hasattr(formfield, 'choices'):
                    setattr(request, cache_attr_name, formfield.choices)
        return formfield

class MonatAdmin(admin.ModelAdmin):
    search_fields = ('name',)

        #('sammler__idfk_Person', RelatedDropdownFilter),
class MuenztypObjektAnzeigeAdmin(admin.ModelAdmin):
    search_fields = ('titel',)
    



class OnlineressourceView(ImportExportModelAdmin,):
    search_fields = ('name',)
    list_display = ('name','katalog', 'firma','temp')
    list_editable = ('katalog', 'firma',)
    autocomplete_fields = ['firma']
    raw_id_fields = ['katalog',]
    def get_queryset(self, request):
        return super(OnlineressourceView,self).get_queryset(request).select_related('katalog__katalogart','katalog__monat', 'firma',)

class KatalogAdmin(admin.ModelAdmin):
    search_fields = ('titel',)
        #('sammler__idfk_Person', RelatedDropdownFilter),
    autocomplete_fields = ['firmen','katalogart']
    list_editable = ('titel', 'nummer', 'tag_von','jahr','tafelteil','tafelanzahl','anzahl')
    list_filter = (
        ('firmen', RelatedDropdownFilter),
        ('katalogart', RelatedDropdownFilter),
        ('schlagworte', RelatedDropdownFilter),
        ('tafelteil', admin.BooleanFieldListFilter),
        ('workflow', RelatedDropdownFilter),
        )
    inlines = [KatalogFirmenInline,OnlineressourceInline, KatalogPersonInline, Katalog_SchlagwortInline]
    # list_filter = (
    #     ('firmen__name', RelatedDropdownFilter),
    #     #('jahr', admin.SimpleListFilter),
    #     ('tafelteil', admin.BooleanFieldListFilter),
    #     'workflow',
    #     )
    list_display = ('id', 'titel', 'Schlagworte','katalogart','nummer', 'tag_von', 'monat', 'jahr','tafelteil', 'tafelanzahl','anzahl',)
    fieldsets = (
        (None, {
            'fields': (
                'workflow',
                ('titel',),
                #'firmen',
                ('katalogart', 'nummer','katalogteil',),
        # return obj.schlagworte.all()
    # def Hyperlinks(self, obj):
    #     # return obj.schlagworte.all()
    #     return ", ".join([p.name for p in obj.hlinks.all()])
                ('tag_von','tag_bis','monat','jahr',),
                'anzahl',
                ('tafelteil','tafelanzahl'),
                'anmerkung',
            ),
        }),
    )
    radio_fields = {'workflow': admin.HORIZONTAL}
    
      
    # def Slg(self, obj):
    #     return ", ".join([p.name for p in obj.Ppl.filter(katalogperson__personfunktion=25)])
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.resolver_match.url_name.endswith('_changelist'):
            return qs.prefetch_related('schlagworte').select_related('katalogart', 'monat', 'workflow')
        return qs
        # return obj.schlagworte.all()
    # def Hyperlinks(self, obj):
    #     # return obj.schlagworte.all()
    #     return ", ".join([p.name for p in obj.hlinks.all()])

    def Schlagworte(self, obj):
        return ", ".join([p.name for p in obj.schlagworte.all()])

    def get_preserved_filters(self, request):
        """
        Returns the preserved filters querystring.
        """
        match = request.resolver_match
        if self.preserve_filters and match:
            opts = self.model._meta
            current_url = '%s:%s' % (match.app_name, match.url_name)
            changelist_url = 'admin:%s_%s_changelist' % (opts.app_label, opts.model_name)
            if current_url == changelist_url:
                preserved_filters = request.GET.urlencode()
            else:
                preserved_filters = request.GET.get('_changelist_filters')

            if preserved_filters:
                return urlencode({'_changelist_filters': preserved_filters})
        return ''
    
    def response_change(self, request, obj, post_url_continue=None):
        # Kontrolliert, ob in Anmerkungen Schlagworte stehen
        
        
        if "_verschlagwortung" in request.POST:
            anmerkung = obj.anmerkung
            anmerkung = anmerkung.lower()
            #woerter = anmerkung.split()
            # initializing test list
            test_list = list(KatSchlagwort.objects.values('name', 'id', 'synonyme'))
            
            #print("test_list:" + str(test_list))
            # test_list = str(test_list)
            # for split in woerter:
            woerter=[]
            for id_dict in test_list:
                if id_dict['name'].lower() in anmerkung:
                    wort = id_dict['name']
                    woerter.append(wort)
                    try:
                        with transaction.atomic():
                            # p1person = Person.objects.filter(name_nom_id=praegeherr).first()
                            # p1 = KatalogSchlagwort(katalog=obj, katschlagwort=p1person, idfk_PersonFunktion=PersonFunktion.objects.get(id=1), appears_on_rev=0)
                            p1 = KatalogSchlagwort(katalog=obj, katschlagwort=KatSchlagwort.objects.get(id=id_dict['id']))
                            p1.save()
                    except IntegrityError:
                        pass
                    #print("Kommt vor: " + id_dict['name'])
                #print("Kommt NICHT vor: " + id_dict['name'])
                if id_dict['synonyme'] is not None:
                    for syn in id_dict['synonyme'].splitlines():
                        if syn.lower() in anmerkung:
                            wort = syn
                            woerter.append(wort)
                            try:
                                with transaction.atomic():
                                    # p1person = Person.objects.filter(name_nom_id=praegeherr).first()
                                    # p1 = KatalogSchlagwort(katalog=obj, katschlagwort=p1person, idfk_PersonFunktion=PersonFunktion.objects.get(id=1), appears_on_rev=0)
                                    p1 = KatalogSchlagwort(katalog=obj, katschlagwort=KatSchlagwort.objects.get(id=id_dict['id']))
                                    p1.save()
                            except IntegrityError:
                                pass
            obj.save()

            opts = obj._meta
            obj_url = reverse(
                'admin:%s_%s_change' % (opts.app_label, opts.model_name),
                args=(quote(obj.pk),),
                current_app=self.admin_site.name,
            )
            preserved_filters = self.get_preserved_filters(request)

            obj_url = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts},
                obj_url
            )
            self.message_user(request, "Verschlagwortung: " + str(woerter))
            # if post_url_continue is None:
            post_url_continue = obj_url
            return HttpResponseRedirect(post_url_continue)
            
            # print("Ende")
            #     qs1_l = [element for element in test_list if str(element.name)==str(split)]
            # print("Die folgenden Wörter kommen in der Datenbank vor: " + str(qs1_l))
            #     for schlagwort in test_list:
            #         if schlagwort == split:
            #             print(split + " = " + schlagwort)
            #         else:
            #             print(split + " != " + schlagwort)
                
            
            # printing original string
            # print("The original string : " + test_string)
            
            # # printing original list
            # print("The original list : " + str(test_list))
            
            # # using list comprehension
            # # checking if string contains list element
            # res = [ele for ele in test_list if(ele in test_string)]
            
            # print result
            
            # print("Does string contain any list element : " + str(bool(res)))
                
        
        return super().response_change(request, obj)
    
    def get_form(self, request, obj=None, **kwargs):
        form = super(KatalogAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['titel'].widget.attrs['style'] = 'width: 60em;'
        #form.base_fields['firmen'].widget.attrs['style'] = 'width: 60em;'
        return form

    def get_queryset(self, request):
        return super(KatalogAdmin,self).get_queryset(request).select_related('katalogart', 'monat','workflow',).prefetch_related('schlagworte',)
        # return super(KatalogAdmin,self).get_queryset(request).select_related('katalogart', 'monat',).prefetch_related('schlagworte',Prefetch('Ppl', queryset=KatalogPerson.objects.select_related('idfk_Person__name', 'idfk_PersonFunktion')))

class HerstellungAdmin(admin.ModelAdmin):
    search_fields = ['name']
    list_display = ['name']

class MetallAdmin(admin.ModelAdmin):
    search_fields = ['name']
    list_display = ['name']

class WorkflowAdmin(CachedAutocompleteAdminMixin, admin.ModelAdmin):
    search_fields = ['name']
    list_display = ['reihenfolge', 'name']
    list_editable = ['name']
    ordering = ['reihenfolge']
    autocomplete_only_fields = ('id', 'name', 'reihenfolge')

@admin.register(SlgKategorie)
class SlgKategorieAdmin(admin.ModelAdmin):
    list_display = ('name', 'beschreibung')
    search_fields = ('name',)

@admin.register(Kontaktanfrage)
class KontaktanfrageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'betreff', 'erstellt_am', 'bearbeitet')
    list_filter = ('bearbeitet', 'erstellt_am')
    search_fields = ('name', 'email', 'betreff', 'nachricht')
    readonly_fields = ('name', 'email', 'betreff', 'nachricht', 'erstellt_am')
    
    def has_add_permission(self, request):
        return False  # Verhindert das manuelle Hinzufügen von Kontaktanfragen

@admin.register(ObjektAenderung)
class ObjektAenderungAdmin(admin.ModelAdmin):
    list_display = ('objekt_link', 'objekt_invnr', 'feld', 'name', 'email', 'erstellt_am', 'status')
    list_filter = ('status', 'erstellt_am', 'feld')
    search_fields = ('objekt__invnr', 'objekt__titel', 'name', 'email', 'feld', 'begruendung')
    readonly_fields = ('objekt', 'objekt_link', 'objekt_invnr', 'name', 'email', 'feld', 'alter_wert', 'neuer_wert', 'begruendung', 'erstellt_am')
    
    fieldsets = (
        ('Objektinformationen', {
            'fields': ('objekt', 'objekt_link', 'objekt_invnr')
        }),
        ('Änderungsdetails', {
            'fields': ('feld', 'alter_wert', 'neuer_wert', 'begruendung')
        }),
        ('Absender', {
            'fields': ('name', 'email', 'erstellt_am')
        }),
        ('Bearbeitung', {
            'fields': ('status', 'bearbeitet_von', 'bearbeitet_am')
        }),
    )
    
    def objekt_link(self, obj):
        """Erstellt einen Link zum Objekt in der Admin-Oberfläche"""
        if obj.objekt:
            url = reverse('admin:slg_obj_change', args=[obj.objekt.id])
            return format_html('<a href="{}" target="_blank">Objekt bearbeiten</a>', url)
        return "-"
    objekt_link.short_description = "Objekt-Link"
    
    def objekt_invnr(self, obj):
        """Zeigt die Inventarnummer des Objekts an"""
        if obj.objekt:
            url = reverse('Objekt', args=[obj.objekt.id])
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.objekt.invnr)
        return "-"
    objekt_invnr.short_description = "Inventarnummer"
    
    def save_model(self, request, obj, form, change):
        if 'status' in form.changed_data:
            obj.bearbeitet_von = request.user
            obj.bearbeitet_am = timezone.now()
        super().save_model(request, obj, form, change)

class OffizinSymbolAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'object_count')
    ordering = ['name']
    search_fields = ['name', 'beschreibung']
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if _is_admin_autocomplete_request(request):
            return queryset.only('id', 'name', 'beschreibung')
        queryset = queryset.annotate(
            _object_count=Count("av_objekte", distinct=True) + Count("rv_objekte", distinct=True),
        )
        return queryset

    def object_count(self, obj):
        return obj._object_count

    object_count.short_description = "Anzahl der Objekte"
    object_count.admin_order_field = "_object_count"

# Register the new model
admin.site.register(OffizinSymbol, OffizinSymbolAdmin)

class EreignisSchlagwortKategorieAdmin(admin.ModelAdmin):
    list_display = ['name', 'beschreibung']
    search_fields = ['name']
    ordering = ['name']

class EreignisSchlagwortAdmin(admin.ModelAdmin):
    list_display = ['name', 'kategorie', 'beschreibung']
    list_filter = ['kategorie']
    search_fields = ['name', 'synonyme', 'beschreibung']
    ordering = ['kategorie__name', 'name']
    autocomplete_fields = ['kategorie']

class SlgInformation_SchlagwortInline(admin.TabularInline):
    model = SlgInformationSchlagwort
    extra = 1
    autocomplete_fields = ['ereignisschlagwort']

# Erweitern Sie Ihre bestehende SlgInformationAdmin Klasse
class SlgInformationAdmin(admin.ModelAdmin):
    # ... existing configuration ...
    inlines = [SlgInformation_SchlagwortInline]  # Fügen Sie diese Zeile hinzu
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('schlagworte__kategorie')

admin.site.site_header = 'Verwaltung'



# Add before OffizinSymbol if it exists, or at appropriate location
class PaketAdmin(ImportExportModelAdmin):
    search_fields = ('name', 'beschreibung')
    list_display = ('name', 'ist_arbeitspaket', 'online_freigegeben', 'anzahl_objekte', 'erstellt_am', 'bearbeitet_am')
    list_display_links = ('name',)
    list_filter = ('ist_arbeitspaket', 'online_freigegeben', 'erstellt_am')
    list_editable = ('ist_arbeitspaket', 'online_freigegeben')
    ordering = ['name']
    
    def anzahl_objekte(self, obj):
        return obj.obj_set.count()
    anzahl_objekte.short_description = 'Anzahl Objekte'

# Import/Export Resource für Paket-Zuweisungen (KOMPLETT ÜBERSCHRIEBEN)
class ObjPaketZuweisungResource(resources.ModelResource):
    invnr = fields.Field(column_name='invnr', attribute='invnr')
    slg_name = fields.Field(column_name='Sammlung')
    slgteil_name = fields.Field(column_name='Sammlungsteil')
    paket_name = fields.Field(column_name='Paket')
    
    class Meta:
        model = Obj
        fields = ('invnr', 'slg_name', 'slgteil_name', 'paket_name')
        import_id_fields = ('invnr',)  # Vereinfacht
        skip_unchanged = True
        report_skipped = True
        use_transactions = True  # Wichtig für Konsistenz

    def _clean_string(self, value):
        """Robuste String-Bereinigung"""
        if not value:
            return None
        
        cleaned = str(value).strip()
        # Normalisiere nur mehrfache Leerzeichen zu einzelnen
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        return cleaned if cleaned else None

    def import_data(self, dataset, dry_run=False, raise_errors=False, use_transactions=None, collect_failed_rows=False, **kwargs):
        """KOMPLETT EIGENER IMPORT - umgeht django-import-export komplett"""
        
        if dry_run:
            return self._validate_dataset(dataset)
        
        # ECHTER IMPORT: Eine einzige Bulk-Operation
        return self._bulk_import(dataset)
    
    def _validate_dataset(self, dataset):
        """Schnelle Validierung für Dry-Run"""
        result = Result()
        
        for i, row in enumerate(dataset.dict):
            invnr = self._clean_string(row.get('invnr', ''))
            slg_name = self._clean_string(row.get('Sammlung', ''))
            paket_name = self._clean_string(row.get('Paket', ''))
            
            if not invnr:
                result.append_invalid_row(i + 1, {'invnr': 'Inventarnummer ist erforderlich'})
            if not slg_name:
                result.append_invalid_row(i + 1, {'Sammlung': 'Sammlung ist erforderlich'})
            if not paket_name:
                result.append_invalid_row(i + 1, {'Paket': 'Paket ist erforderlich'})
        
        # Simuliere Erfolg für gültige Zeilen
        valid_rows = len(dataset) - len(result.invalid_rows)
        result.totals[RowResult.IMPORT_TYPE_NEW] = valid_rows
        
        return result

    def _bulk_import(self, dataset):
        """OPTIMIERTER Bulk-Import mit Chunking für bessere Performance"""
        from django.db import transaction
        from slg.models import Paket, Slg, SlgTeil, Obj
        
        result = Result()
        CHUNK_SIZE = 1000  # Verarbeite in 1000er-Batches
        
        try:
            with transaction.atomic():
                # 1. SAMMLE UND VALIDIERE ALLE DATEN
                import_rows = []
                paket_namen = set()
                slg_namen = set()
                slgteil_namen = set()
                
                print("🔄 Verarbeite Import-Daten...")
                
                for i, row in enumerate(dataset.dict):
                    invnr = self._clean_string(row.get('invnr', ''))
                    slg_name = self._clean_string(row.get('Sammlung', ''))
                    slgteil_name = self._clean_string(row.get('Sammlungsteil', ''))
                    paket_name = self._clean_string(row.get('Paket', ''))
                    
                    if invnr and slg_name and paket_name:
                        paket_namen.add(paket_name)
                        slg_namen.add(slg_name)
                        if slgteil_name:
                            slgteil_namen.add(slgteil_name)
                        import_rows.append((invnr, slg_name, slgteil_name, paket_name))
                
                print(f"📊 {len(import_rows)} gültige Zeilen zum Verarbeiten")
                
                # 2. LADE/ERSTELLE PAKETE (einmalig)
                existing_pakete = {p.name: p for p in Paket.objects.filter(name__in=paket_namen)}
                missing_pakete = paket_namen - set(existing_pakete.keys())
                
                if missing_pakete:
                    print(f"📦 Erstelle {len(missing_pakete)} neue Pakete")
                    neue_pakete = [Paket(name=name) for name in missing_pakete]
                    Paket.objects.bulk_create(neue_pakete, batch_size=1000)
                    for paket in Paket.objects.filter(name__in=missing_pakete):
                        existing_pakete[paket.name] = paket

                # 3. LADE REFERENZ-DATEN (einmalig)
                slg_cache = {s.name: s for s in Slg.objects.filter(name__in=slg_namen)}
                slgteil_cache = {}
                if slgteil_namen:
                    slgteil_cache = {st.name: st for st in SlgTeil.objects.filter(name__in=slgteil_namen)}

                # 4. VERARBEITE IN CHUNKS für bessere Performance
                total_created = 0
                total_skipped = 0
                total_errors = 0
                alle_fehler = []
                
                ThroughModel = Obj.pakete.through
                
                for chunk_start in range(0, len(import_rows), CHUNK_SIZE):
                    chunk_end = min(chunk_start + CHUNK_SIZE, len(import_rows))
                    chunk = import_rows[chunk_start:chunk_end]
                    
                    print(f"🔄 Verarbeite Chunk {chunk_start//CHUNK_SIZE + 1}/{(len(import_rows)-1)//CHUNK_SIZE + 1} ({len(chunk)} Zeilen)")
                    
                    # SAMMLE OBJEKT-SUCHKRITERIEN FÜR DIESEN CHUNK
                    invnr_slg_mapping = {}  # invnr -> [(slg_id, slgteil_id_or_none)]
                    
                    for invnr, slg_name, slgteil_name, _ in chunk:
                        slg = slg_cache.get(slg_name)
                        slgteil = slgteil_cache.get(slgteil_name) if slgteil_name else None
                        
                        if slg:
                            if invnr not in invnr_slg_mapping:
                                invnr_slg_mapping[invnr] = []
                            invnr_slg_mapping[invnr].append((slg.id, slgteil.id if slgteil else None))
                    
                    # FINDE OBJEKTE FÜR DIESEN CHUNK (effizientere Query)
                    chunk_obj_cache = {}
                    
                    if invnr_slg_mapping:
                        # Alle Inventarnummern in diesem Chunk
                        invnr_list = list(invnr_slg_mapping.keys())
                        
                        # Lade alle Objekte mit diesen Inventarnummern
                        objekte_queryset = Obj.objects.filter(
                            invnr__in=invnr_list
                        ).select_related('Slg', 'SlgTeil')
                        
                        # Filtere die richtigen Objekte basierend auf Slg/SlgTeil
                        for obj in objekte_queryset:
                            obj_slg_id = obj.Slg.id if obj.Slg else None
                            obj_slgteil_id = obj.SlgTeil.id if obj.SlgTeil else None
                            
                            # Prüfe ob dieses Objekt zu unseren Suchkriterien passt
                            if obj.invnr in invnr_slg_mapping:
                                for slg_id, slgteil_id in invnr_slg_mapping[obj.invnr]:
                                    if obj_slg_id == slg_id and obj_slgteil_id == slgteil_id:
                                        key = (obj.invnr, obj.Slg.name, obj.SlgTeil.name if obj.SlgTeil else None)
                                        chunk_obj_cache[key] = obj
                                        break
                    
                    # PRÜFE BESTEHENDE ZUWEISUNGEN FÜR DIESEN CHUNK
                    chunk_obj_ids = [obj.id for obj in chunk_obj_cache.values()]
                    chunk_paket_ids = [paket.id for paket in existing_pakete.values()]
                    
                    existing_relations = set()
                    if chunk_obj_ids and chunk_paket_ids:
                        existing_relations = set(
                            ThroughModel.objects
                            .filter(obj_id__in=chunk_obj_ids, paket_id__in=chunk_paket_ids)
                            .values_list('obj_id', 'paket_id')
                        )
                    
                    # VERARBEITE CHUNK-ZEILEN
                    chunk_zuweisungen = []
                    chunk_errors = 0
                    chunk_skipped = 0
                    
                    for invnr, slg_name, slgteil_name, paket_name in chunk:
                        obj_key = (invnr, slg_name, slgteil_name)
                        obj = chunk_obj_cache.get(obj_key)
                        
                        if not obj:
                            alle_fehler.append(f"Objekt '{invnr}' in '{slg_name}'{f'/{slgteil_name}' if slgteil_name else ''} nicht gefunden")
                            chunk_errors += 1
                            continue
                        
                        paket = existing_pakete.get(paket_name)
                        if not paket:
                            alle_fehler.append(f"Paket '{paket_name}' nicht gefunden")
                            chunk_errors += 1
                            continue
                        
                        relation_key = (obj.id, paket.id)
                        if relation_key in existing_relations:
                            chunk_skipped += 1
                            continue
                        
                        chunk_zuweisungen.append(ThroughModel(obj_id=obj.id, paket_id=paket.id))
                    
                    # ERSTELLE ZUWEISUNGEN FÜR DIESEN CHUNK
                    chunk_created = 0
                    if chunk_zuweisungen:
                        try:
                            ThroughModel.objects.bulk_create(chunk_zuweisungen, batch_size=1000, ignore_conflicts=True)
                            chunk_created = len(chunk_zuweisungen)
                            print(f"  ✅ {chunk_created} neue Zuweisungen erstellt")
                        except Exception as e:
                            print(f"  ❌ Fehler beim Erstellen der Zuweisungen: {e}")
                            chunk_errors += len(chunk_zuweisungen)
                    
                    if chunk_skipped > 0:
                        print(f"  ⏭️ {chunk_skipped} Zuweisungen übersprungen (bereits vorhanden)")
                    
                    # SUMMIERE CHUNK-ERGEBNISSE
                    total_created += chunk_created
                    total_skipped += chunk_skipped
                    total_errors += chunk_errors
                
                print(f"🎯 GESAMT: {total_created} erstellt, {total_skipped} übersprungen, {total_errors} Fehler")
                
                # ERSTELLE FINAL RESULT
                result.totals[RowResult.IMPORT_TYPE_NEW] = total_created
                result.totals[RowResult.IMPORT_TYPE_SKIP] = total_skipped
                result.totals[RowResult.IMPORT_TYPE_ERROR] = total_errors
                
                # Zeige erste 10 Fehler
                for fehler_msg in alle_fehler[:10]:
                    result.append_base_error(fehler_msg)
                
                if len(alle_fehler) > 10:
                    result.append_base_error(f"... und {len(alle_fehler) - 10} weitere Fehler")
                
        except Exception as e:
            print(f"❌ Schwerwiegender Fehler beim Import: {e}")
            import traceback
            traceback.print_exc()
            result.append_base_error(f"Schwerwiegender Fehler: {str(e)}")
        
        return result

    # WICHTIG: Alle anderen Methoden deaktivieren, damit nur import_data verwendet wird
    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        return dataset
    
    def before_import_row(self, row, **kwargs):
        return
    
    def get_or_init_instance(self, instance_loader, row):
        # DUMMY - wird nicht verwendet da import_data überschrieben ist
        return Obj(), False
    
    def after_import_instance(self, instance, new, row_number=None, **kwargs):
        return
    
    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        return
    
    def import_obj(self, obj, data, dry_run):
        # DUMMY - wird nicht verwendet
        return
    
    def save_instance(self, instance, using_transactions=True, dry_run=False):
        # DUMMY - wird nicht verwendet  
        return
    
    def delete_instance(self, instance, using_transactions=True, dry_run=False):
        # DUMMY - wird nicht verwendet
        return

# Optimierte Admin-Klasse für bessere Performance
class ObjPaketZuweisungAdmin(ImportExportModelAdmin):
    resource_class = ObjPaketZuweisungResource
    list_display = ('invnr', 'slg_display', 'slgteil_display', 'pakete_display')
    search_fields = ('invnr',)
    list_filter = ('Slg', 'SlgTeil', 'pakete')
    
    def get_queryset(self, request):
        """Optimiertes QuerySet mit select_related und prefetch_related"""
        return super().get_queryset(request).select_related(
            'Slg', 'SlgTeil'
        ).prefetch_related('pakete')
    
    def slg_display(self, obj):
        return obj.Slg.name if obj.Slg else '-'
    slg_display.short_description = 'Sammlung'
    
    def slgteil_display(self, obj):
        return obj.SlgTeil.name if obj.SlgTeil else '-'
    slgteil_display.short_description = 'Sammlungsteil'
    
    def pakete_display(self, obj):
        # Nutze prefetch_related Daten
        return ', '.join([paket.name for paket in obj.pakete.all()])
    pakete_display.short_description = 'Pakete'

# Registrierung
admin.site.register(EreignisSchlagwortKategorie, EreignisSchlagwortKategorieAdmin)
admin.site.register(EreignisSchlagwort, EreignisSchlagwortAdmin)
admin.site.register(Onlineressource,OnlineressourceView)
admin.site.register(Firma, FirmaAdmin)
# admin.site.register(KatalogSchlagwort,KatalogSchlagwortAdmin)
admin.site.register(Katalogart,KatalogartAdmin)
admin.site.register(Katalog, KatalogAdmin)
admin.site.register(Slg, SlgView)
admin.site.register(Obj, ObjAdmin,)
admin.site.register(MyObjects, MyObjectsAdmin,)
admin.site.register(Muenztyp, MuenztypAdmin,)
admin.site.register(SlgTeil, SlgTeilAdmin)
admin.site.register(Person, PersonView,)
admin.site.register(PersonFunktion,PersonFunktionAdmin)
admin.site.register(Herstellung,HerstellungAdmin)
admin.site.register(Herstellungsmerkmale,HerstellungsmerkmaleView)
admin.site.register(Sek_Merkmale,Sek_MerkmaleView)
admin.site.register(Objekttyp,ObjekttypenView)
admin.site.register(Rand,RandView,)
admin.site.register(Ref, RefView,)
admin.site.register(Nominal, NominalView,)
admin.site.register(Reichskreis,ReichskreisView)
admin.site.register(Muenzstand,MuenzstandView)
#admin.site.register(Mzstaette,)
admin.site.register(Mzstaette, MzstaetteView,)
admin.site.register(AvBildtyp, AvBildtypAdmin,)
admin.site.register(AvBeizeichen, AvBeizeichenAdmin,)
admin.site.register(AvOffizin, AvOffizinAdmin,)
admin.site.register(AvBildrand, AvBildrandAdmin,)
admin.site.register(RvBildrand, RvBildrandAdmin,)
admin.site.register(RvBildtyp, RvBildtypAdmin,)
admin.site.register(RvBeizeichen, RvBeizeichenAdmin,)
admin.site.register(RvOffizin, RvOffizinAdmin,)
admin.site.register(Workflow,WorkflowAdmin)
admin.site.register(Variantenbeschr,)
admin.site.register(Region, RegionAdmin)
admin.site.register(Metall,MetallAdmin)
admin.site.register(interneAnmerkung,)
admin.site.register(Schlagwort, SchlagwortAdmin,)
admin.site.register(Wappen, WappenAdmin,)
admin.site.register(KatSchlagwort, KatSchlagwortAdmin,)
admin.site.register(Faelschung, FaelschungAdmin,)
admin.site.register(Fund, FundView,)
admin.site.register(SlgInformation,SlgInformationAdmin)
admin.site.register(MuenztypObjektAnzeige,MuenztypObjektAnzeigeAdmin)
admin.site.register(Auflage, AuflageAdmin)
admin.site.register(Paket, PaketAdmin)
admin.site.register(ObjPaketZuweisung, ObjPaketZuweisungAdmin)

class TitelAdmin(admin.ModelAdmin):
    list_display = ('name', 'sortierung', 'erstellt_am')
    list_editable = ('sortierung',)
    search_fields = ('name',)
    ordering = ('sortierung', 'name')

admin.site.register(Titel, TitelAdmin)