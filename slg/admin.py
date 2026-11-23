from django.db import IntegrityError, transaction, models
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.options import csrf_protect_m
from django.core.exceptions import PermissionDenied
from django.contrib.admin.models import LogEntry, DELETION
from django.contrib.admin.utils import quote
from django.db.models.query import Q
from django.http import HttpResponse
from django.http.response import HttpResponseRedirect
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, reverse
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.shortcuts import redirect
# Register your models here.
from .models import *
from .translation_resources import (AvBildtypTranslationResource, RvBildtypTranslationResource, TranslationStatusFilter, TranslationAdminMixin,
    ObjekttypTranslationResource, HerstellungTranslationResource, PersonFunktionTranslationResource, SchlagwortTranslationResource,
    MetallTranslationResource, NominalTranslationResource, MzstaetteTranslationResource)
from .admin_imports import (
    CachedForeignKeyWidget as CachedForeignKeyWidget,
    MuenztypImport,
    ObjImport,
    ObjResource as ObjResource,
    SafeField as SafeField,
)
from .admin_packages import ObjPaketZuweisungAdmin, ObjPaketZuweisungResource as ObjPaketZuweisungResource, PaketAdmin
from .services.type_metadata import (
    _host_matches,
    _normalize_type_link as _normalize_type_link,
    _safe_get,
    _SAFE_IRI_RE as _SAFE_IRI_RE,
    _safe_sparql_iri as _safe_sparql_iri,
    extract_year as extract_year,
    process_download_infos,
    TYPE_LINK_HOSTS as TYPE_LINK_HOSTS,
    TYPE_LINK_MAX_BYTES as TYPE_LINK_MAX_BYTES,
    TYPE_LINK_MAX_REDIRECTS as TYPE_LINK_MAX_REDIRECTS,
    TYPE_LINK_TIMEOUT as TYPE_LINK_TIMEOUT,
)
from .services.schlagwort_merge import METADATA, lock_keyword_writes, merge_keywords, merge_preview
from import_export.resources import modelresource_factory
from import_export.admin import ImportExportModelAdmin, ImportExportActionModelAdmin
from .resources import FundResource
from django.db.models import Count, Exists, OuterRef
from django.db.models.functions import Trim
import json
import requests as requests
from requests.exceptions import RequestException
from django import forms
from django.forms import Textarea
from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter
from model_clone import CloneModelAdmin
import nested_admin
import adminactions.actions as actions
from urllib.parse import urlencode, urlparse
import logging
from django.core import signing
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache







def _set_widget_style(form, field_name, style):
    """Breite setzen, ohne für View-only-Nutzer (leere base_fields) zu crashen."""
    field = form.base_fields.get(field_name)
    if field is not None:
        field.widget.attrs['style'] = style


def _sync_objekte_mtoa(obj_ids):
    """MTOA nach .update()/.bulk_update() nachziehen (diese lösen keine Signals aus)."""
    from .signals import sync_queryset_to_mtoa
    sync_queryset_to_mtoa(Obj.objects.filter(pk__in=list(obj_ids)))


def _sync_typen_mtoa(typ_ids):
    """Wie _sync_objekte_mtoa, für alle Objekte (und Konkordanzen) der Münztypen."""
    from .signals import sync_queryset_to_mtoa
    typ_ids = list(typ_ids)
    sync_queryset_to_mtoa(Obj.objects.filter(Q(Typ_id__in=typ_ids) | Q(Typ__Konkordanz__in=typ_ids)))


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

class ObjekttypenView(TranslationAdminMixin, ImportExportModelAdmin):
    # Erste Ressource: reiner Übersetzungsaustausch; zweite: bisheriger Vollimport/-export.
    resource_classes = [ObjekttypTranslationResource, modelresource_factory(Objekttyp)]
    search_fields = ('name', 'name_en')
    list_display = ('id', 'name', 'name_en', 'name_nom_id')
    list_display_links = ('id', 'name')
    list_editable = ('name_en',)
    list_filter = (TranslationStatusFilter,)
    fields = (('name', 'name_en'), 'name_nom_id')
    ordering = ['name']

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

class NominalView(TranslationAdminMixin, ImportExportModelAdmin):
    # Erste Ressource: reiner Übersetzungsaustausch; zweite: bisheriger Vollimport/-export.
    resource_classes = [NominalTranslationResource, modelresource_factory(Nominal)]
    search_fields = ('name', 'name_en', 'name_nom_id')
    list_display = ('id', 'name', 'name_en', 'name_nom_id',)
    list_display_links = ('id', 'name')
    list_editable = ('name_en',)
    list_filter = (TranslationStatusFilter,)

class MuenzstandView(ImportExportModelAdmin):
    search_fields = ('name',)
    list_display = ('id','name',)
    pass

class RandView(admin.ModelAdmin):
    search_fields = ('name',)
    list_display = ('id','name',)
    pass

class MzstaetteView(TranslationAdminMixin, ImportExportModelAdmin):
    resource_classes = [MzstaetteTranslationResource, modelresource_factory(Mzstaette)]
    search_fields = ('name', 'name_en', 'name_nom_id')
    list_display = ('id', 'name', 'name_en', 'name_nom_id', 'ndpikmk', 'geonames', 'lat', 'long')
    list_display_links = ('id', 'name')
    list_editable = ('name_en', 'ndpikmk', 'geonames', 'lat', 'long',)
    list_filter = (TranslationStatusFilter,)
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

@admin.action(description="Personen matchen (Exact Only)", permissions=['change'])
def match_personen_exact(modeladmin, request, queryset):
    updated = skipped = 0
    for ereignis in queryset:
        raw = ereignis.raw_personen or ""
        # Kommaseparierte Liste in Einzelnamen aufsplitten
        names = [n.strip() for n in raw.split(",") if n.strip()]
        persons = []
        for name in names:
            # Regex statt iexact, um Collation-Probleme zu vermeiden
            person = Person.objects.filter(name__iregex=r'^' + re.escape(name) + r'$').first()
            if person and person not in persons:
                persons.append(person)
        if not persons:
            # Leeres raw_personen oder kein Treffer: bestehende Links nicht löschen.
            skipped += 1
            continue
        with transaction.atomic():
            ereignis.person.set(persons)
        updated += 1
    modeladmin.message_user(
        request, f'{updated} Ereignis(se) aktualisiert, {skipped} ohne Treffer unverändert gelassen.')

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
    list_display = ('name', 'kategorie', 'nomisma_export_erlaubt', 'kulturpool_export_erlaubt', 'kulturpool_readiness', 'beschreibung', 'ereignis_count', 'ereignisse_link')
    list_filter = ('kategorie', 'nomisma_export_erlaubt', 'kulturpool_export_erlaubt')
    search_fields = ('name',)
    show_full_result_count = False  # Reduziert COUNT-Queries für bessere Performance
    readonly_fields = ('ereignisse_link', 'kulturpool_readiness', 'nomisma_readiness')
    
    fieldsets = (
        (None, {
            'fields': ('name', 'kategorie', 'beschreibung', 'bildrechte_lizenz', 'cover')
        }),
        ('Datenweitergabe / Nomisma und Kulturpool', {
            'fields': ('nomisma_export_erlaubt', 'nomisma_collection_uri', 'nomisma_readiness',
                       'kulturpool_export_erlaubt', 'kulturpool_rights_uri',
                       'kulturpool_metadata_rights_uri', 'kulturpool_readiness'),
            'description': 'Kulturpool nutzt /oai/. Bildrechte: Ist „Copyrightlizenz der Bilder“ eine eindeutige Lizenz wie „CC BY-NC 4.0“, '
                           'wird die passende Creative-Commons-URI automatisch verwendet; sonst die Kulturpool-Rechte-URI eintragen. '
                           'Metadatenrechte (üblich: http://creativecommons.org/publicdomain/zero/1.0/) separat eintragen – sie gelten auch für Nomisma. '
                           'Nomisma nutzt /slg/<id>/nomisma.rdf; registriert wird /slg/<id>/void.rdf. '
                           'Vor der Freigabe validate_kulturpool_export --preflight --slg ID --strict ausführen.'
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

    @admin.display(description='Nomisma-Bereitschaft')
    def nomisma_readiness(self, obj):
        if not obj.pk or not obj.nomisma_export_erlaubt:
            return 'Export deaktiviert'
        from django.urls import reverse
        from .nomisma_rdf import count_exportable, nomisma_readiness
        issues = nomisma_readiness(obj)
        if issues:
            return '; '.join(issues)
        return (f'Bereit: ca. {count_exportable(obj)} Münzen mit Typ-Link. Bei Nomisma registrieren: '
                f'{reverse("collection_nomisma_void", kwargs={"id": obj.pk})}')

    @admin.display(description='Kulturpool-Bereitschaft')
    def kulturpool_readiness(self, obj):
        from .oai.readiness import collection_readiness
        if not obj.kulturpool_export_erlaubt:
            return 'Export deaktiviert'
        from .oai.rights import image_rights_uri, metadata_rights_uri
        issues = collection_readiness(obj)
        if issues:
            return '; '.join(issues)
        return (f'Bildrechte: {image_rights_uri(obj)}; Metadatenrechte: {metadata_rights_uri(obj)}. '
                'Objektqualität mit validate_kulturpool_export prüfen')
    
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

class FundView(ImportExportModelAdmin):
    resource_classes = [FundResource]
    search_fields = ('objekt__invnr','maßnahmennr', 'fundnummer')  # objekt ist OneToOne: über invnr suchen
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
        _set_widget_style(form, 'name', 'width: 60em;')
        _set_widget_style(form, 'beschreibung', 'width: 60em;')
        return form

    def Link(self, obj):
        query = urlencode({'query': obj.name or '', 'method': 'simpleSearch', 'categoryId': 'persons'})
        return format_html(
            '<a href="https://portal.dnb.de/opac.htm?{}" target="_blank" rel="noopener noreferrer">GND</a>',
            query,
        )

    PERSON_LINK_HOSTS = (
        ('Zisterzienserlexikon', ('zisterzienserlexikon.de',)),
        ('OeBL', ('biographien.ac.at',)),
        ('DB', ('deutsche-biographie.de',)),
        ('DeutscheDigitaleBib', ('deutsche-digitale-bibliothek.de',)),
    )
    PERSONDATA_HOSTS = ('tools.wmflabs.org', 'toolforge.org')
    GND_ID_RE = re.compile(r'[0-9][0-9Xx-]{0,15}')

    def response_change(self, request, obj, post_url_continue=None):
        # Ergänzt Personenlinks über den GND-SeeAlso-Beacon (beacon.findbuch.de).
        if "_download_infos" in request.POST:
            self._download_person_links(request, obj)
            opts = obj._meta
            return HttpResponseRedirect(reverse(
                'admin:%s_%s_change' % (opts.app_label, opts.model_name),
                args=(quote(obj.pk),),
                current_app=self.admin_site.name,
            ))
        return super().response_change(request, obj)

    def _download_person_links(self, request, obj):
        gnd = re.sub(r'^https?://d-nb\.info/gnd/', '', (obj.DNB or '').strip()).strip('/')
        if not self.GND_ID_RE.fullmatch(gnd):
            self.message_user(request, 'Keine gültige GND-ID im Feld DNB.', messages.ERROR)
            return
        url = 'http://beacon.findbuch.de/seealso/pnd-aks?' + urlencode({'format': 'seealso', 'id': gnd})
        try:
            data = _safe_get(url, ('beacon.findbuch.de',)).json()
        except (RequestException, RuntimeError, ValueError):
            logging.getLogger(__name__).warning('GND-Beacon für Person %s nicht abrufbar', obj.pk, exc_info=True)
            self.message_user(request, 'Personendaten konnten nicht abgerufen werden.', messages.ERROR)
            return
        links = data[3] if isinstance(data, list) and len(data) > 3 and isinstance(data[3], list) else []
        changed = []
        for link in links:
            if not isinstance(link, str) or len(link) > 255:
                continue
            try:
                parts = urlparse(link)
            except ValueError:
                continue
            if parts.scheme not in ('http', 'https'):
                continue
            if _host_matches(parts.hostname, self.PERSONDATA_HOSTS):
                if obj.WikiDe or not parts.path.startswith('/persondata/redirect/gnd/de/'):
                    continue
                try:
                    final = _safe_get(link, self.PERSONDATA_HOSTS + ('de.wikipedia.org',)).url
                except (RequestException, RuntimeError):
                    continue
                if _host_matches(urlparse(final).hostname, ('de.wikipedia.org',)) and len(final) <= 255:
                    obj.WikiDe = final
                    changed.append('WikiDe')
                continue
            for field, hosts in self.PERSON_LINK_HOSTS:
                if not getattr(obj, field) and _host_matches(parts.hostname, hosts):
                    setattr(obj, field, link)
                    changed.append(field)
        if changed:
            obj.save(update_fields=changed)
            self.message_user(request, 'Personenlinks ergänzt: ' + ', '.join(changed))
        else:
            self.message_user(request, 'Keine neuen Personenlinks gefunden.', messages.WARNING)

class WappenAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']

class RegionAdmin(admin.ModelAdmin):
    ordering = ['name']
    search_fields = ['name']
    
class DuplicateKeywordFilter(admin.SimpleListFilter):
    title = 'Namensgleiche Schlagworte'
    parameter_name = 'duplicates'

    def lookups(self, request, model_admin):
        return [('yes', 'Nur namensgleiche')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            duplicates = Schlagwort.objects.alias(trimmed_name=Trim('name')).filter(
                trimmed_name__iexact=OuterRef('trimmed_name'),
            ).exclude(pk=OuterRef('pk'))
            return queryset.alias(trimmed_name=Trim('name')).filter(Exists(duplicates))
        return queryset


class KeywordMergeForm(forms.Form):
    revision = forms.CharField(widget=forms.HiddenInput)
    target = forms.TypedChoiceField(label='Schlagwort, das erhalten bleibt', coerce=int)

    def __init__(self, keywords, metadata, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target'].choices = [
            ('', 'Bitte wählen'),
            *((keyword.pk, f'{keyword.name} (ID {keyword.pk})') for keyword in keywords),
        ]
        for field, values in metadata.items():
            if len(values) > 1:
                self.fields[field] = forms.ChoiceField(
                    label=METADATA[field], choices=[('', 'Bitte wählen'), *((value, value) for value in values)],
                )


class SchlagwortAdmin(TranslationAdminMixin, ImportExportActionModelAdmin, admin.ModelAdmin):
    resource_classes = [SchlagwortTranslationResource]
    actions = ['merge_selected_keywords']
    ordering = ['name']
    search_fields = ['name', 'name_en', 'name_nom_id']
    list_display = ('id', 'name', 'name_en', 'name_nom_id')
    list_display_links = ('id', 'name')
    list_editable = ('name_en',)
    list_filter = (DuplicateKeywordFilter, TranslationStatusFilter)
    list_per_page = 50
    fields = (('name', 'name_en'), 'name_nom_id')

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if request.method == 'POST':
            with transaction.atomic():
                lock_keyword_writes()
                return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def has_merge_permission(self, request):
        return self.has_change_permission(request) and self.has_delete_permission(request)

    @admin.action(permissions=['merge'], description='Ausgewählte Schlagworte zusammenführen')
    def merge_selected_keywords(self, request, queryset):
        ids = list(queryset.order_by('pk').values_list('pk', flat=True))
        try:
            keywords, counts, metadata, _, _, revision = merge_preview(ids)
        except ValueError as exc:
            self.message_user(request, str(exc), messages.WARNING)
            return

        signer = signing.Signer(salt='slg.schlagwort.merge')
        if 'confirm_merge' in request.POST:
            form = KeywordMergeForm(keywords, metadata, request.POST)
            if form.is_valid():
                try:
                    expected = signer.unsign(form.cleaned_data['revision'])
                    with transaction.atomic():
                        target, snapshot = merge_keywords(ids, form.cleaned_data['target'], form.cleaned_data, expected)
                        self.log_change(request, target, 'Schlagworte zusammengeführt. ' +
                                        json.dumps(snapshot, ensure_ascii=False))
                except signing.BadSignature:
                    form.add_error(None, 'Die Vorschau ist ungültig. Starten Sie die Aktion erneut.')
                except ValueError as exc:
                    form.add_error(None, str(exc))
                except IntegrityError:
                    form.add_error(None, 'Verknüpfungen wurden gleichzeitig geändert. Starten Sie die Aktion erneut.')
                else:
                    self.message_user(request, f'{len(ids)} Schlagworte zu „{target.name}“ '
                                               f'(ID {target.pk}) zusammengeführt.', messages.SUCCESS)
                    return
        else:
            form = KeywordMergeForm(keywords, metadata, initial={'revision': signer.sign(revision)})

        return TemplateResponse(request, 'admin/slg/schlagwort/merge.html', {
            **self.admin_site.each_context(request),
            'title': 'Schlagworte zusammenführen',
            'opts': self.model._meta,
            'rows': [(keyword, counts[keyword.pk]) for keyword in keywords],
            'form': form,
            'action_checkbox_name': ACTION_CHECKBOX_NAME,
            'return_url': request.get_full_path(),
        })


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
            'name': forms.Textarea(attrs={'cols': 60, 'rows': 4}),
            'name_en': forms.Textarea(attrs={'cols': 60, 'rows': 4}),
        }

class AvBildtypAdmin(TranslationAdminMixin, ImportExportActionModelAdmin, admin.ModelAdmin):
    #list_editable = ('name',)
    #list_editable = ('name',)
    resource_classes = [AvBildtypTranslationResource]
    list_editable = ('name_en',)
    list_display_links = ('id',)
    list_filter = (TranslationStatusFilter,)
    list_per_page = 25
    fields = (('name', 'name_en'), 'abk')
    form = AvBildtypAdminForm
    #list_select_related = ('object_count', '_mztyp_count',)
    # actions = [actions.export_as_xls]
        # return obj.schlagworte.all()
    ordering = ['name',]
    #list_select_related = ('object_count', '_mztyp_count',)
    # actions = [actions.export_as_xls]
        # return obj.schlagworte.all()
    search_fields = ['name', 'name_en', 'abk',]
    list_display = ('id', 'name', 'name_en', 'Schlagworte','object_count', 'mztyp_count')
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
            'name': forms.Textarea(attrs={'cols': 60, 'rows': 4}),
            'name_en': forms.Textarea(attrs={'cols': 60, 'rows': 4}),
    # actions = [actions.merge, actions.export_as_xls]
        }

        # return obj.schlagworte.all()
class RvBildtypAdmin(TranslationAdminMixin, ImportExportActionModelAdmin, admin.ModelAdmin):
    resource_classes = [RvBildtypTranslationResource]
    list_editable = ('name_en',)
    list_display_links = ('id',)
    list_filter = (TranslationStatusFilter,)
    list_per_page = 25
    fields = (('name', 'name_en'), 'abk')
    form = RvBildtypAdminForm
    ordering = ['name']
    # actions = [actions.merge, actions.export_as_xls]
    search_fields = ['name', 'name_en', 'abk',]
    list_display = ('id', 'name', 'name_en', 'Schlagworte','object_count', 'mztyp_count')
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

    def _bulk_update_typen(self, queryset, **values):
        # .update() löst keine Signals aus -> MTOA der betroffenen Objekte explizit nachziehen.
        ids = list(queryset.values_list('pk', flat=True))
        Muenztyp.objects.filter(pk__in=ids).update(**values)
        _sync_typen_mtoa(ids)

    def verkupfern(self, request, queryset):
        self._bulk_update_typen(queryset, Metall="9")
    verkupfern.short_description = "zu Kupfer machen"
    verkupfern.allowed_permissions = ('change',)
    
    def nummisieren(self, request, queryset):
        self._bulk_update_typen(queryset, Nominal="492")
    nummisieren.short_description = "zu Nummus machen"
    nummisieren.allowed_permissions = ('change',)

    def vermessingere(self, request, queryset):
        self._bulk_update_typen(queryset, Metall="5")
    vermessingere.short_description = "zu Messing machen"
    vermessingere.allowed_permissions = ('change',)
    
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
            _sync_typen_mtoa([mt.pk for mt in zu_aktualisieren])

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
    material_vom_nominal.allowed_permissions = ('change',)

    def transpadana(self, request, queryset):
        self._bulk_update_typen(queryset, region="210")
    transpadana.short_description = "nach Transpadana"
    transpadana.allowed_permissions = ('change',)

    
    
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
        _set_widget_style(form, 'muenztyptitel', 'width: 60em;')
        _set_widget_style(form, 'Konkordanz', 'width: 80em;')
        konkordanz_initial = self._get_konkordanz_initial_from_request(request, obj)
        if konkordanz_initial:
            if 'Konkordanz' in form.base_fields:
                form.base_fields['Konkordanz'].initial = konkordanz_initial
        _set_widget_style(form, 'titel', 'width: 60em;')
        _set_widget_style(form, 'av_bildtyp', 'width: 80em;')
        _set_widget_style(form, 'rv_bildtyp', 'width: 80em;')
        
        
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
        _sync_objekte_mtoa([obj.pk for obj in zu_aktualisieren])
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
material_von_nominal_uebernehmen.allowed_permissions = ('change',)


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
        _sync_objekte_mtoa([obj.pk for obj in zu_aktualisieren])
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
material_von_muenztyp_uebernehmen.allowed_permissions = ('change',)


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
    
    actions = ['export_coins', 'export_fund_vorlage', 'create_coin_labels', 'create_catalog', material_von_nominal_uebernehmen, material_von_muenztyp_uebernehmen, 'sync_mtoa_selected']
    
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

    @csrf_protect_m
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        if object_id and request.method == 'POST' and '_download_legenden' in request.POST:
            obj = self.get_object(request, object_id)
            if obj is None or not self.has_change_permission(request, obj):
                raise PermissionDenied
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
        _set_widget_style(form, 'Typ', 'width: 45em;')
        _set_widget_style(form, 'av_bildtyp', 'width: 80em;')
        _set_widget_style(form, 'rv_bildtyp', 'width: 80em;')
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
        ('Typ', admin.EmptyFieldListFilter),  # Typ ist ein FK: IS NULL / IS NOT NULL statt Typ_id = 0/1
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

    def export_fund_vorlage(self, request, queryset):
        """Excel-Vorlage für den Fundinfo-Import (Fundinformationen → Importieren)."""
        from .resources import FundResource
        objs = Obj.objects.filter(pk__in=queryset.values('pk')).select_related('Slg', 'SlgTeil', 'fund', 'fund__fundort').order_by('invnr')
        dataset = FundResource().export_template(objs)
        response = HttpResponse(
            dataset.export('xlsx'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="fundinfo_vorlage.xlsx"'
        return response

    export_fund_vorlage.short_description = "Fundinfo-Vorlage exportieren (für Import bei Fundinformationen)"

    def sync_mtoa_selected(self, request, queryset):
        """Admin-Aktion: Ausgewählte Objekte in MuenztypObjektAnzeige synchronisieren."""
        from .mtoa_sync import sync_objs_to_mtoa

        obj_ids = list(queryset.order_by().values_list('pk', flat=True).distinct())
        created = updated = 0
        # In 500er-Blöcken statt alles auf einmal in einer Transaktion zu laden.
        for start in range(0, len(obj_ids), 500):
            c, u = sync_objs_to_mtoa(obj_ids[start:start + 500])
            created += c
            updated += u

        self.message_user(
            request,
            f"{created + updated} Objekt(e) in MTOA synchronisiert "
            f"({created} neu, {updated} aktualisiert)."
        )
    sync_mtoa_selected.short_description = "MTOA aktualisieren (Anzeige-Tabelle)"
    sync_mtoa_selected.allowed_permissions = ('change',)

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
        if obj.action_flag == DELETION or obj.content_type_id is None:
            return escape(obj.object_repr)
        ct = obj.content_type
        try:
            url = reverse('admin:%s_%s_change' % (ct.app_label, ct.model), args=[obj.object_id])
        except NoReverseMatch:
            # Model ohne Admin-Registrierung (oder entfernte App): nur Text anzeigen
            return escape(obj.object_repr)
        return mark_safe('<a href="%s">%s</a>' % (escape(url), escape(obj.object_repr)))
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
    
    def get_actions(self, request):
        # Entfernt die Sammel-Löschaktion (Objekte nur einzeln löschen).
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        return actions

    def SlgHlHaupt(self, request, queryset):
        ids = list(queryset.values_list('pk', flat=True))
        Obj.objects.filter(pk__in=ids).update(Slg="1", SlgTeil="2")
        _sync_objekte_mtoa(ids)
    SlgHlHaupt.short_description = "Objekte zu Hl gesellen"
    SlgHlHaupt.allowed_permissions = ('change',)

    class Media:
        js = ('Djangoprojekt/js/admin.js',)

class StaatAdmin(admin.ModelAdmin,):
    search_fields = ('name',)

class PersonFunktionAdmin(TranslationAdminMixin, ImportExportModelAdmin,):
    resource_classes = [PersonFunktionTranslationResource, modelresource_factory(PersonFunktion)]
    search_fields = ('name', 'name_en')
    list_display = ('id', 'name', 'name_en')
    list_display_links = ('id', 'name')
    list_editable = ('name_en',)
    list_filter = (TranslationStatusFilter,)
    fields = (('name', 'name_en'),)

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
    search_fields = ('objekttitel', 'invnr')
    



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
            anmerkung = (obj.anmerkung or '').lower()
            #woerter = anmerkung.split()
            # initializing test list
            test_list = list(KatSchlagwort.objects.values('name', 'id', 'synonyme'))
            
            #print("test_list:" + str(test_list))
            # test_list = str(test_list)
            # for split in woerter:
            woerter=[]
            for id_dict in test_list:
                name = (id_dict['name'] or '').strip()
                if name and name.lower() in anmerkung:
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
                        # Leere Synonym-Zeilen ('' in text ist immer True) hätten
                        # das Schlagwort jedem Katalog zugeordnet.
                        syn = syn.strip()
                        if syn and syn.lower() in anmerkung:
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
        _set_widget_style(form, 'titel', 'width: 60em;')
        #form.base_fields['firmen'].widget.attrs['style'] = 'width: 60em;'
        return form

    def get_queryset(self, request):
        return super(KatalogAdmin,self).get_queryset(request).select_related('katalogart', 'monat','workflow',).prefetch_related('schlagworte',)
        # return super(KatalogAdmin,self).get_queryset(request).select_related('katalogart', 'monat',).prefetch_related('schlagworte',Prefetch('Ppl', queryset=KatalogPerson.objects.select_related('idfk_Person__name', 'idfk_PersonFunktion')))

class HerstellungAdmin(TranslationAdminMixin, ImportExportActionModelAdmin, admin.ModelAdmin):
    resource_classes = [HerstellungTranslationResource]
    search_fields = ['name', 'name_en']
    list_display = ['id', 'name', 'name_en', 'name_nom_id']
    list_display_links = ['id', 'name']
    list_editable = ['name_en']
    list_filter = (TranslationStatusFilter,)
    fields = (('name', 'name_en'), 'name_nom_id')

class MetallAdmin(TranslationAdminMixin, ImportExportActionModelAdmin, admin.ModelAdmin):
    resource_classes = [MetallTranslationResource]
    search_fields = ['name', 'name_en', 'name_nom_id']
    list_display = ['id', 'name', 'name_en', 'name_nom_id']
    list_display_links = ['id', 'name']
    list_editable = ['name_en']
    list_filter = (TranslationStatusFilter,)
    fields = (('name', 'name_en'), 'name_nom_id')

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
    
    def has_add_permission(self, request):
        # Vorschläge entstehen nur über das öffentliche Formular; im Admin sind
        # die Pflichtfelder (objekt, feld, neuer_wert …) schreibgeschützt, ein
        # "Hinzufügen" würde beim Speichern scheitern.
        return False

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

# Hinweis: SlgInformationAdmin ist weiter oben vollständig definiert. Ein früher
# hier stehender Stub hat die Klasse überschrieben (Import/Export, Suche, Filter,
# list_display und raw_id_fields gingen verloren) und wurde entfernt.

admin.site.site_header = 'Verwaltung'



# Add before OffizinSymbol if it exists, or at appropriate location
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


@admin.register(Bildabruf)
class BildabrufAdmin(admin.ModelAdmin):
    """Read-only statistics of the image redirect service (/bild/<obj>/<ansicht>/)."""
    change_list_template = 'admin/slg/bildabruf/change_list.html'
    list_display = ('datum', 'herkunft', 'objekt', 'ansicht', 'automatisiert', 'anzahl')
    list_filter = ('herkunft', 'automatisiert', 'ansicht', 'obj__Slg')
    date_hierarchy = 'datum'
    search_fields = ('obj__invnr', '=obj__id', 'herkunft')
    ordering = ('-datum', '-anzahl')
    list_select_related = ('obj',)
    show_full_result_count = False

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        context = getattr(response, 'context_data', None)
        if context and 'cl' in context:
            from .services.image_request_stats import summarize_image_requests

            date_selected = any(key.startswith('datum__') for key in request.GET)
            context['image_stats'] = summarize_image_requests(
                context['cl'].queryset,
                has_selected_date=date_selected,
                monthly='datum__year' in request.GET and 'datum__month' not in request.GET,
            )
        return response

    @admin.display(description='Objekt', ordering='obj__invnr')
    def objekt(self, obj):
        return format_html('<a href="{}">{}</a>', obj.obj.get_absolute_url(), obj.obj.invnr or obj.obj_id)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MtoaSyncAuftrag)
class MtoaSyncAuftragAdmin(admin.ModelAdmin):
    """Nur Einsicht: hängende/fehlgeschlagene Hintergrund-Aktualisierungen erkennen."""
    list_display = ['model_label', 'object_pk', 'created_at', 'claimed_at', 'attempts', 'last_error']
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
