"""Public pages, authority popups and contact forms."""

import csv
import hashlib
import logging
import random
from collections import Counter
from urllib.parse import quote, quote_plus, unquote, urlsplit

import requests
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Max, Min, OuterRef, Prefetch, Subquery
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import get_language, ngettext
from requests.exceptions import RequestException

from slg import structured_data as sd

from ..models import (
    AvBildtyp,
    Kontaktanfrage,
    Muenztyp,
    MuenztypObjektAnzeige,
    Nominal,
    Obj,
    ObjektAenderung,
    Paket,
    Person,
    RvBildtyp,
    Slg,
)
from ..seo import clean_text, muenztyp_meta
from ..services.authority_display import display_label as authority_label
from .packages import (
    _format_package_year,
    _package_preview_entries,
    _refresh_mtoa_image_urls_from_objects,
)

logger = logging.getLogger(__name__)


def index(request):
    latest_entries = list(
        MuenztypObjektAnzeige.objects
        .exclude(obj_id__isnull=True)
        .select_related('slg_fk', 'slgteil_fk')
        .order_by('-last_modified')[:10]
    )
    _refresh_mtoa_image_urls_from_objects(latest_entries)
    context_packages = list(
        Paket.objects
        .filter(online_freigegeben=True)
        .annotate(objektanzahl_db=Count('obj', distinct=True))
        .order_by('name')
    )

    # Pro Paket nur, was die Startseite zeigt: Zeitspanne per DB-Aggregat und
    # die ersten drei Objekte (nach Objekt-ID) mit Bild; sonst die ersten drei.
    # Früher wurden alle Objekte aller Pakete aus MTOA und Obj geladen.
    paket_links = Obj.pakete.through.objects
    mtoa_of_link = MuenztypObjektAnzeige.objects.filter(obj_id=OuterRef('obj_id'))
    extents = {
        row['paket_id']: row
        for row in (
            paket_links.filter(paket_id__in=[paket.id for paket in context_packages])
            .annotate(
                von=Subquery(mtoa_of_link.values('datierung_von')[:1]),
                bis=Subquery(mtoa_of_link.values('datierung_bis')[:1]),
            )
            .values('paket_id')
            .annotate(start=Min('von'), end=Max('bis'))
            .order_by()
        )
    }
    for paket in context_packages:
        package_mtoa = MuenztypObjektAnzeige.objects.filter(
            obj_id__in=paket_links.filter(paket_id=paket.id).values('obj_id')
        )
        extent = extents.get(paket.id, {})
        if extent.get('start') is not None and extent.get('end') is not None:
            paket.homepage_date_range_label = f"{_format_package_year(extent['start'])} bis {_format_package_year(extent['end'])}"
        else:
            paket.homepage_date_range_label = ''
        paket.homepage_preview_objects = _package_preview_entries(package_mtoa)

    browse_url = reverse('Objektliste')
    highlighted_context_package = random.choice(context_packages) if context_packages else None
    secondary_context_packages = [
        paket for paket in context_packages
        if paket != highlighted_context_package
    ]

    def build_wordcloud_data(default_field, undetermined_field, filter_name, limit=80):
        # Zählen per GROUP BY in der DB statt jede Objektzeile nach Python zu
        # streamen; Ergebnis ist unabhängig vom Besucher und wird kurz gecacht.
        cache_key = f'index-wordcloud:{filter_name}:{limit}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        counts = Counter()
        for qs, field in (
            (Obj.objects.filter(Typ__isnull=False), default_field),
            (Obj.objects.filter(Typ__isnull=True), undetermined_field),
        ):
            rows = qs.order_by().values(field).annotate(n=Count('pk')).values_list(field, 'n')
            for keyword, n in rows:
                if not keyword:
                    continue
                normalized_keyword = str(keyword).strip()
                if normalized_keyword:
                    counts[normalized_keyword] += n

        data = [
            {
                'text': keyword,
                'value': count,
                'url': f"{browse_url}?{filter_name}={quote_plus(keyword)}",
            }
            for keyword, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[:limit]
        ]
        cache.set(cache_key, data, 60 * 10)
        return data

    av_wordcloud_data = build_wordcloud_data(
        'Typ__av_bildtyp__avbildtyp_schlagwort__schlagwort__name',
        'av_bildtyp__avbildtyp_schlagwort__schlagwort__name',
        'av_schlagwort',
    )
    rv_wordcloud_data = build_wordcloud_data(
        'Typ__rv_bildtyp__rvbildtyp_schlagwort__schlagwort__name',
        'rv_bildtyp__rvbildtyp_schlagwort__schlagwort__name',
        'rv_schlagwort',
    )

    context = {
        'latest_entries': latest_entries,
        'context_packages': context_packages,
        'highlighted_context_package': highlighted_context_package,
        'secondary_context_packages': secondary_context_packages,
        'av_wordcloud_data': av_wordcloud_data,
        'rv_wordcloud_data': rv_wordcloud_data,
    }

    return render(request, 'slg/index.html', context)


def neuerschliessungen(request):
    latest_entries_qs = (
        MuenztypObjektAnzeige.objects
        .exclude(obj_id__isnull=True)
        .select_related('slg_fk', 'slgteil_fk')
        .order_by('-last_modified')
    )

    page = request.GET.get('page', 1)
    paginator = Paginator(latest_entries_qs, 24)

    try:
        latest_entries = paginator.page(page)
    except PageNotAnInteger:
        latest_entries = paginator.page(1)
    except EmptyPage:
        latest_entries = paginator.page(paginator.num_pages)

    return render(request, 'slg/neuerschliessungen.html', {
        'latest_entries': latest_entries,
    })

def sammlungen_uebersicht(request):
    sammlungen = (
        Slg.objects
        .only('id', 'name', 'beschreibung', 'cover')
        .annotate(obj_count=Count('obj'))
        .order_by('-obj_count', 'name')
    )
    return render(request, 'slg/sammlungen_uebersicht.html', {
        'sammlungen': sammlungen,
    })

# Neue API-Endpoints für die ausgelagerten Daten


def _nomisma_uri(value):
   from slg.services.authority_inventory import identify_authority
   ref = identify_authority(value, allow_nomisma_id=True)
   return f'http://nomisma.org/id/{ref[1]}' if ref and ref[0] == 'nomisma' else ''


def NomismaInfo(link):
   """exactMatch-Links und englische Definition; leer statt Fehler, wenn Nomisma nicht antwortet."""
   uri = _nomisma_uri(link)
   if not uri:
      return [], ""
   query = ('PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n'
            'SELECT * WHERE {\n'
            f'  OPTIONAL {{ <{uri}> skos:exactMatch ?link }}\n'
            f'  <{uri}> skos:definition ?def.\n'
            "  FILTER langMatches(lang(?def), 'en')\n"
            '}')
   # Ohne Cache blockierte jeder Modal-Aufruf einen Worker bis zu 5 s auf Nomisma.
   cache_key = 'nomisma-info:' + hashlib.sha256(uri.encode()).hexdigest()
   cached = cache.get(cache_key)
   if cached is not None:
      return cached
   try:
      response = requests.get('https://nomisma.org/query', params={'query': query, 'output': 'csv'}, timeout=5)
      response.raise_for_status()
      rows = list(csv.DictReader(response.content.decode('utf-8').splitlines(), delimiter=','))
   except (RequestException, ValueError):
      # Fehlschläge kurz merken, damit ein hängender Endpunkt nicht jeden
      # Aufruf erneut ausbremst.
      cache.set(cache_key, ([], ""), 60 * 5)
      return [], ""
   definition = rows[0].get('def', '') if rows else ""
   result = ([row for row in rows if row.get('link')], definition)
   cache.set(cache_key, result, 60 * 60 * 24)
   return result


WIKIPEDIA_USER_AGENT = 'Eligius/1.0 (https://eligius.at; numismatic catalogue)'


def _wikipedia_summary(url):
   """(Kurztext, Vorschaubild) über die Wikipedia-REST-API; bei Fehlern leer."""
   if not url:
      return "", ""
   try:
      parts = urlsplit(url)
      if not parts.scheme:
         parts = urlsplit(unquote(url))
      host = parts.hostname or ''
   except ValueError:
      return "", ""
   if not host.endswith('.wikipedia.org') or not parts.path.startswith('/wiki/'):
      return "", ""
   title = unquote(parts.path[len('/wiki/'):])
   cache_key = 'wiki-summary:' + hashlib.sha256(f'{host}/{title}'.encode()).hexdigest()
   cached = cache.get(cache_key)
   if cached is not None:
      return cached
   try:
      response = requests.get(f'https://{host}/api/rest_v1/page/summary/{quote(title, safe="")}',
                              headers={'User-Agent': WIKIPEDIA_USER_AGENT}, timeout=5)
      response.raise_for_status()
      data = response.json()
      result = (data.get('extract', ''), (data.get('thumbnail') or {}).get('source', ''))
   except (RequestException, ValueError):
      return "", ""
   cache.set(cache_key, result, 60 * 60 * 24)
   return result


def PersonModalView(request, id):
   person = get_object_or_404(Person, id=id)
   english_ui = (get_language() or '').startswith('en')
   # Bei englischer Oberfläche bevorzugt den englischen Artikel.
   sources = [person.WikiEn, person.WikiDe] if english_ui else [person.WikiDe, person.WikiEn]
   wiki, thumbnail = "", ""
   wiki_url = next((source for source in sources if source), "")
   for source in sources:
      if source:
         wiki, thumbnail = _wikipedia_summary(source)
         if wiki:
            wiki_url = source
            break

   if person.name_nom_id:
      exactmatch, definition = NomismaInfo(person.name_nom_id)
   else:
      exactmatch = []
      definition = ""

   context = {
      'Person': person,
      'Wiki': wiki,
      'WikiBild': thumbnail,
      'WikiUrl': wiki_url,
      'Exactmatch': exactmatch,
      'Definition': definition,
   }

   return render(request, 'slg/modal_person.html', context)

def NominalModalView(request, id):
   nominal = get_object_or_404(Nominal, id=id)
   exactmatch, definition = [], ""
   if nominal.name_nom_id:
      exactmatch, definition = NomismaInfo(nominal.name_nom_id)
   context = {
      'Nominal': nominal,
      'Exactmatch': exactmatch,
      'Definition': definition,
   }

   return render(request, 'slg/modal_nominal.html', context)

def TypView(request, id):
    """
    Detailansicht für einen Münztyp.
    Holt den Typ selbst, alle für die linke Infospalte benötigten FK‑Felder
    und alle zugehörigen Objekte (inklusive deren wichtigsten FK‑Felder)
    in möglichst wenigen Datenbank‑Queries.
    """

    # ---------------------------------------------------------------
    # 1. Münztyp mit allen FK/M2M in wenigen Queries laden
    obj = get_object_or_404(
        Muenztyp.objects.select_related(
            'Nominal',
            'Mzstaette',
            'Muenzstand',
            'Reichskreis',
            'region',
            'Metall',
            'Objekttyp',
            'workflow',
            'av_bildtyp',
            'rv_bildtyp',
        ).prefetch_related(
            'mztyp_person_set__idfk_Person',
            'mztyp_person_set__idfk_PersonFunktion',
            'typ_ref_set__Ref',
            'Konkordanz__Ref',
            'av_bildtyp__avbildtyp_schlagwort_set__schlagwort',
            'rv_bildtyp__rvbildtyp_schlagwort_set__schlagwort',
        ),
        id=id,
    )

    # ---------------------------------------------------------------
    # 2. Bereits geprefetchte Daten abgreifen
    # ---------------------------------------------------------------
    personen = obj.mztyp_person_set.all()

    av_schlagworte = (
        obj.av_bildtyp.avbildtyp_schlagwort_set.all()
        if obj.av_bildtyp else []
    )
    rv_schlagworte = (
        obj.rv_bildtyp.rvbildtyp_schlagwort_set.all()
        if obj.rv_bildtyp else []
    )

    # ---------------------------------------------------------------
    # 3. Objekte über MuenztypObjektAnzeige laden (denormalisiert,
    #    keine JOINs nötig) mit DB-Level Pagination (LIMIT/OFFSET)
    # ---------------------------------------------------------------
    objekte_qs = (
        MuenztypObjektAnzeige.objects
            .filter(typ_fk_id=id)
            .only(
                "id", "obj_id", "Slg", "objekttitel",
                "datierung_verbale",
                "thumbnail_av_url", "thumbnail_rv_url",
                "av_url", "rv_url",
            )
            .order_by("obj_id")
    )
    paginator = Paginator(objekte_qs, 12)
    page = request.GET.get("page", 1)
    try:
        objekte_page = paginator.page(page)
    except PageNotAnInteger:
        objekte_page = paginator.page(1)
    except EmptyPage:
        objekte_page = paginator.page(paginator.num_pages)

    # ---------------------------------------------------------------
    # 4. Template Kontext
    # ---------------------------------------------------------------
    seo = muenztyp_meta(obj, personen, paginator.count)
    first_with_image = next((o for o in objekte_page if o.av_url or o.thumbnail_av_url), None)
    if first_with_image:
        seo['image'] = first_with_image.av_url or first_with_image.thumbnail_av_url

    context = {
        "Muenztyp": obj,
        "objekte_page": objekte_page,
        "MztypPersonen": personen,
        "avschlagworte": av_schlagworte,
        "rvschlagworte": rv_schlagworte,
        "seo": seo,
        "structured_data": sd.typ_graph(request, obj, seo['title']),
    }

    return render(request, "slg/typ_detail.html", context)

def SammlungView(request, id):

   sammlung = get_object_or_404(Slg, id=id)
   # avbildtypen = AvBildtyp.objects.prefetch_related('avmztypen','avmztypen__objekte','avmztypen__objekte__SlgTeil').filter(schlagworte=id,)
   # typen = Muenztyp.objects.select_related('rv_bildtyp_set',).filter(rv_bildtyp__schlagworte=id,)
   # rvbildtypen = typen.values_list('rv_bildtyp__name', 'rv_bildtyp__id',).exclude(rv_bildtyp__name=None).distinct()
   # print(rvbildtypen.muenztyp.all())

   objektanzahl = Obj.objects.filter(Slg=sammlung).count()
   name = authority_label(sammlung)
   description = clean_text(sammlung.beschreibung, limit=0)
   if len(description) < 50:
      # Google Dataset Search verlangt mindestens 50 Zeichen Beschreibung.
      description = ngettext(
         '%(counter)s Münze und numismatisches Objekt der Sammlung „%(name)s“ – digital erschlossen und frei recherchierbar in Eligius.',
         '%(counter)s Münzen und numismatische Objekte der Sammlung „%(name)s“ – digital erschlossen und frei recherchierbar in Eligius.',
         objektanzahl,
      ) % {'counter': objektanzahl, 'name': name}
   context = {
      'Sammlung': sammlung,
      'objektanzahl': objektanzahl,
      'structured_data': sd.collection_graph(request, sammlung, name, description, objektanzahl, sammlung.cover),
   }

   return render(request, 'slg/Sammlung.html', context)

def _schlagwort_nav(current_id):
   """Blätter-Navigation (±1, ±2, ±10) für die Schlagwort-Detailseiten."""
   items = [{'id': max(1, current_id - 10), 'symbol': '&laquo;', 'label': 'Previous'}]
   items += [{'id': current_id + offset, 'current': offset == 0}
             for offset in (-2, -1, 0, 1, 2) if current_id + offset >= 1]
   items.append({'id': current_id + 10, 'symbol': '&raquo;', 'label': 'Next'})
   return items


def AvSchlagwortView(request, id):

   # obj = Muenztyp.objects.select_related('Muenzstand', 'Herstellung', 'Nominal', 'Mzstaette', 'Metall', 'region', 'av_bildtyp', 'rv_bildtyp', 'av_beizeichen', 'rv_beizeichen', 'Objekttyp',).prefetch_related('obj_set', 'mztyp_person_set', 'typ_ref_set',).get(id=id)
   # rvbildtypen = RvBildtyp.objects.prefetch_related('muenztyp_set','obj_set').exclude(name__isnull=True).filter(schlagworte=id,)
   avbildtypen = AvBildtyp.objects.prefetch_related('avmztypen','avmztypen__objekte','avmztypen__objekte__SlgTeil').filter(schlagworte=id,)
   # typen = Muenztyp.objects.select_related('rv_bildtyp_set',).filter(rv_bildtyp__schlagworte=id,)
   # rvbildtypen = typen.values_list('rv_bildtyp__name', 'rv_bildtyp__id',).exclude(rv_bildtyp__name=None).distinct()
   # print(rvbildtypen.muenztyp.all())

   context = {
      'avbildtypen': avbildtypen,
      'schlagwort_nav': _schlagwort_nav(id),
   }

   return render(request, 'slg/avschlagwort_detail.html', context)


def RvSchlagwortView(request, id):

   # obj = Muenztyp.objects.select_related('Muenzstand', 'Herstellung', 'Nominal', 'Mzstaette', 'Metall', 'region', 'av_bildtyp', 'rv_bildtyp', 'av_beizeichen', 'rv_beizeichen', 'Objekttyp',).prefetch_related('obj_set', 'mztyp_person_set', 'typ_ref_set',).get(id=id)
   # rvbildtypen = RvBildtyp.objects.prefetch_related('muenztyp_set','obj_set').exclude(name__isnull=True).filter(schlagworte=id,)
   rvbildtypen = RvBildtyp.objects.prefetch_related('rvmztypen','rvmztypen__objekte','rvmztypen__objekte__SlgTeil').filter(schlagworte=id,)
   # typen = Muenztyp.objects.select_related('rv_bildtyp_set',).filter(rv_bildtyp__schlagworte=id,)
   # rvbildtypen = typen.values_list('rv_bildtyp__name', 'rv_bildtyp__id',).exclude(rv_bildtyp__name=None).distinct()
   # print(rvbildtypen.muenztyp.all())
   context = {
      'rvbildtypen': rvbildtypen,
      'schlagwort_nav': _schlagwort_nav(id),
   }

   return render(request, 'slg/rvschlagwort_detail.html', context)

def RvSchlagwortTimelineView(request, id):

   # obj = Muenztyp.objects.select_related('Muenzstand', 'Herstellung', 'Nominal', 'Mzstaette', 'Metall', 'region', 'av_bildtyp', 'rv_bildtyp', 'av_beizeichen', 'rv_beizeichen', 'Objekttyp',).prefetch_related('obj_set', 'mztyp_person_set', 'typ_ref_set',).get(id=id)
   # rvbildtypen = RvBildtyp.objects.prefetch_related('muenztyp_set','obj_set').exclude(name__isnull=True).filter(schlagworte=id,)
   rvbildtypen = RvBildtyp.objects.prefetch_related('rvmztypen','rvmztypen__objekte','rvmztypen__objekte__SlgTeil').filter(schlagworte=id,)
   startandenddate = rvbildtypen.aggregate(start=Min('rvmztypen__dat_von'), end=Max('rvmztypen__dat_bis'))

   # typen = Muenztyp.objects.select_related('rv_bildtyp_set',).filter(rv_bildtyp__schlagworte=id,)
   # rvbildtypen = typen.values_list('rv_bildtyp__name', 'rv_bildtyp__id',).exclude(rv_bildtyp__name=None).distinct()
   # print(rvbildtypen.muenztyp.all())
   context = {
      'rvbildtypen': rvbildtypen,
      'startandenddate': startandenddate,
   }

   return render(request, 'slg/timeline_bildtypen.html', context)

def PraegeherrTimelineView(request, id):

   typen = Muenztyp.objects.filter(mztyp_person__idfk_Person=id).distinct()
   # Nur die Typen dieses Prägeherrn vorladen; ein ungefiltertes
   # prefetch('rvmztypen') holte alle Typen anderer Prägeherren mit.
   rvbildtypen = RvBildtyp.objects.prefetch_related(
      Prefetch('rvmztypen',
               queryset=Muenztyp.objects.filter(pk__in=typen.values('pk'))
               .prefetch_related('objekte', 'objekte__SlgTeil'))
   ).filter(rvmztypen__mztyp_person__idfk_Person=id).distinct()

   startandenddate = typen.aggregate(start=Min('dat_von'), end=Max('dat_bis'))
   datierungen = typen.values('dat_von')

   context = {
      'rvbildtypen': rvbildtypen,
      'startandenddate': startandenddate,
      'mztyp': typen,
      'datierungen': datierungen,
   }

   return render(request, 'slg/timeline_praegeherr.html', context)


PUBLIC_FORM_LIMIT = 5            # Einsendungen …
PUBLIC_FORM_WINDOW = 10 * 60     # … pro 10 Minuten und IP
PUBLIC_TEXT_MAX = 5000


def _client_ip(request):
    """Client-IP wie DRF (NUM_PROXIES): letzter vom eigenen Proxy angehängter Eintrag."""
    from django.conf import settings
    num_proxies = getattr(settings, 'REST_FRAMEWORK', {}).get('NUM_PROXIES')
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if num_proxies and forwarded:
        addrs = [a.strip() for a in forwarded.split(',') if a.strip()]
        if addrs:
            return addrs[-min(num_proxies, len(addrs))]
    return request.META.get('REMOTE_ADDR', '')


def _public_form_problem(request, scope, fields):
    """Prüft ein öffentliches Formular. Gibt eine Fehlermeldung oder None zurück.

    fields: [(Bezeichnung, Wert, Maximallänge)], alle Pflichtfelder; ein Feld
    namens 'E-Mail' wird zusätzlich als Adresse validiert.
    """
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    for label, value, max_len in fields:
        if not value:
            return 'Bitte alle Pflichtfelder ausfüllen.'
        if len(value) > max_len:
            return f'{label} ist zu lang (max. {max_len} Zeichen).'
        if label == 'E-Mail':
            try:
                validate_email(value)
            except ValidationError:
                return 'Bitte eine gültige E-Mail-Adresse angeben.'
    key = 'public-form:%s:%s' % (scope, hashlib.sha256(_client_ip(request).encode()).hexdigest())
    if cache.get(key, 0) >= PUBLIC_FORM_LIMIT:
        return 'Zu viele Einsendungen. Bitte versuchen Sie es in einigen Minuten erneut.'
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, PUBLIC_FORM_WINDOW)
    return None


def kontakt(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        betreff = request.POST.get('betreff', '').strip()
        nachricht = request.POST.get('nachricht', '').strip()
        success = 'Ihre Nachricht wurde erfolgreich gesendet. Wir werden uns so bald wie möglich bei Ihnen melden.'
        if request.POST.get('website'):
            # Honeypot ausgefüllt → Bot; nichts speichern, aber nichts verraten.
            messages.success(request, success)
            return redirect('/#kontakt')
        problem = _public_form_problem(request, 'kontakt', [
            ('Name', name, 100), ('E-Mail', email, 254), ('Betreff', betreff, 200),
            ('Nachricht', nachricht, PUBLIC_TEXT_MAX)])
        if problem:
            messages.error(request, problem)
            return redirect('/#kontakt')

        # Kontaktanfrage in der Datenbank speichern
        try:
            Kontaktanfrage.objects.create(
                name=name,
                email=email,
                betreff=betreff,
                nachricht=nachricht
            )
            messages.success(request, success)
        except Exception:
            messages.error(request, 'Beim Speichern Ihrer Nachricht ist ein Fehler aufgetreten. Bitte versuchen Sie es später erneut.')
            logger.exception('Kontaktformular konnte nicht gespeichert werden')

        # Zurück zur Startseite mit Anker zum Kontaktformular
        return redirect('/#kontakt')

    # Bei GET-Anfragen einfach zur Startseite weiterleiten
    return redirect('/')

def objekt_aenderung(request, objekt_id):
    objekt = get_object_or_404(Obj, id=objekt_id)
    back = HttpResponseRedirect(f'/objekt/{objekt_id}/')
    if request.method != 'POST':
        return back

    from ..admin_site import OBJECT_CHANGE_FIELD_LABELS
    data = {key: request.POST.get(key, '').strip()
            for key in ('name', 'email', 'feld', 'alter_wert', 'neuer_wert', 'begruendung')}
    success = 'Ihr Änderungsvorschlag wurde erfolgreich übermittelt und wird geprüft.'
    if request.POST.get('website'):
        messages.success(request, success)  # Honeypot: Bot, nichts speichern
        return back
    if data['feld'] not in OBJECT_CHANGE_FIELD_LABELS:
        messages.error(request, 'Bitte ein gültiges Feld auswählen.')
        return back
    if len(data['alter_wert']) > PUBLIC_TEXT_MAX:
        messages.error(request, f'Alter Wert ist zu lang (max. {PUBLIC_TEXT_MAX} Zeichen).')
        return back
    problem = _public_form_problem(request, 'objekt_aenderung', [
        ('Name', data['name'], 100), ('E-Mail', data['email'], 254),
        ('Neuer Wert', data['neuer_wert'], PUBLIC_TEXT_MAX),
        ('Begründung', data['begruendung'], PUBLIC_TEXT_MAX)])
    if problem:
        messages.error(request, problem)
        return back
    try:
        ObjektAenderung.objects.create(objekt=objekt, **data)
        messages.success(request, success)
    except Exception:
        logger.exception('Änderungsvorschlag zu Objekt %s konnte nicht gespeichert werden', objekt_id)
        messages.error(request, 'Beim Speichern Ihres Änderungsvorschlags ist ein Fehler aufgetreten. '
                                'Bitte versuchen Sie es später erneut.')
    return back

# Fügen Sie diese Funktion zu Ihrer views.py hinzu
def about(request):
    return render(request, 'slg/about.html')

def impressum(request):
    return render(request, 'slg/impressum.html')

def datenschutz(request):
    return render(request, 'slg/datenschutz.html')

def graph_view(request):
    """View function to display the graph visualization tool."""
    return render(request, 'slg/graphv0.2.html')


def timeline_view(request):
    """
    Rendert die Timeline-Ansicht.
    
    Die Daten werden asynchron über die REST API geladen.
    """
    # Titel für die Seite bestimmen
    title = "Ereigniszeitleiste"

    # Parameter für die Timeline
    context = {
        'title': title,
        'api_url': '/api/ereignisse/',
    }

    return render(request, 'slg/timeline.html', context)
