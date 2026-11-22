"""Object browsing, facets and the chronology chart."""

import logging
from collections import Counter, defaultdict

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..filter_config import FILTER_PARAMETERS
from ..filters import is_valid_qparam
from ..models import Obj
from ..services import browse_cache
from ..services.search import _get_filtered_mtoa_queryset
from .utils import json_for_script

logger = logging.getLogger(__name__)


def area_chart_data(request):
    payload = browse_cache.get_or_compute(request, 'area-chart', lambda: _area_chart_payload(request))
    if payload is None:
        return JsonResponse({
            'error': 'Ungültige oder inkompatible Filterparameter.',
            'years': [],
            'counts': [],
            'percentages': []
        }, status=400)
    return JsonResponse(payload)


def _area_chart_payload(request):
    try:
        filtered_qs, _, _ = _get_filtered_mtoa_queryset(request)
        object_count = filtered_qs.count()
        logger.debug("area_chart_data: %d MTOA-Objekte", object_count)

        if not object_count:
            return {
                'years': [],
                'counts': [],
                'percentages': [],
                'debug': {'message': 'Keine Objekte mit passenden Filtern gefunden'}
            }

        pairs = list(
            filtered_qs.exclude(
                Q(datierung_von=None) | Q(datierung_bis=None)
            ).values_list('datierung_von', 'datierung_bis')
        )
        logger.debug(f"area_chart_data: MTOA-Datumswerte: {len(pairs)} Paare gefunden")

        # Wenn Datierungsfilter aktiv sind, die Zeitspannen für den Chart
        # auf den angeforderten Bereich begrenzen. Sonst bleibt der Ausschnitt
        # durch lange Objektspannen unnötig weit.
        requested_from = request.GET.get('dat_von')
        requested_to = request.GET.get('dat_bis')
        chart_from = None
        chart_to = None

        try:
            if is_valid_qparam(requested_from):
                chart_from = int(requested_from)
            if is_valid_qparam(requested_to):
                chart_to = int(requested_to)
        except (TypeError, ValueError):
            chart_from = None
            chart_to = None

        if chart_from is not None and chart_to is not None and chart_from > chart_to:
            chart_from, chart_to = chart_to, chart_from

        logger.debug(f"area_chart_data: chart_from={chart_from}, chart_to={chart_to}")

        # Obergrenze gilt immer: sonst hebt ?dat_von=-100000&dat_bis=100000 das
        # Limit auf und jede Objektspanne wird jahresweise aufaddiert (CPU/RAM).
        max_span = 3000
        if chart_from is not None and chart_to is not None:
            max_span = min(max_span, chart_to - chart_from + 2)

        years_counter = Counter()
        diff = defaultdict(float)
        error_count = 0

        for start, end in pairs:
            try:
                start = int(start)
                end = int(end)

                if chart_from is not None:
                    start = max(start, chart_from)
                if chart_to is not None:
                    end = min(end, chart_to)

                if end < start:
                    continue

                span = end - start + 1

                if span <= 0 or span > max_span:
                    error_count += 1
                    continue

                # Differenz-Array statt Schleife über jedes Jahr der Spanne:
                # O(Objekte + Jahre) statt O(Objekte × Spanne).
                weight = 1.0 / span
                diff[start] += weight
                diff[end + 1] -= weight
            except (TypeError, ValueError) as e:
                error_count += 1
                continue

        if diff:
            running = 0.0
            for y in range(min(diff), max(diff)):
                running += diff.get(y, 0.0)
                # Rundungsreste der Prefix-Summe (±1e-16) nicht als Werte führen.
                if running > 1e-9:
                    years_counter[y] = running

        logger.debug(f"area_chart_data: Fehlerhafte Datumsbereiche: {error_count}")
        logger.debug(f"area_chart_data: Verarbeitete Jahre im Counter: {len(years_counter)}")

        # Vollständige Jahresliste
        if years_counter:
            try:
                min_year = min(years_counter.keys())
                max_year = max(years_counter.keys())
                years = list(range(min_year, max_year + 1))
                counts = [years_counter.get(y, 0) for y in years]
            except ValueError:
                years = []
                counts = []
        else:
            years = []
            counts = []

        # Prozent-Rechnung
        total = sum(counts)
        if total > 0:
            percentages = [round(c / total * 100, 1) for c in counts]
        else:
            percentages = [0 for _ in counts]

        return {
            'years': years,
            'counts': counts,
            'percentages': percentages,
            'debug': {
                'filtered_objects': object_count,
                'date_pairs': len(pairs),
                'error_count': error_count,
                'years_counter_items': len(years_counter),
                'chart_from': chart_from,
                'chart_to': chart_to,
                'years_min': years[0] if years else None,
                'years_max': years[-1] if years else None,
            }
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"ERROR in area_chart_data: {error_details}")

        return None  # Fehler: nicht cachen, Antwort baut area_chart_data






# In views.py

@api_view(['GET'])
@permission_classes([AllowAny])  # Diese Zeile hinzufügen
def facet_api(request):
    from ..services.public_api import facet_values
    try:
        facet = request.GET.get('facet')
        include_current = (request.GET.get('include_current_facet') == '1'
                           or request.GET.get('include_selected') == '1')
        return Response(browse_cache.get_or_compute(
            request, ('facet', facet, include_current),
            lambda: facet_values(request, facet, include_current=include_current,
                                 term=request.GET.get('term'))[:50],
            localized=True,
        ))
    except (ValueError, TypeError):
        return Response({'error': 'Ungültige Facette oder Filterparameter.'}, status=400)


def objekt_list_view_mtoa(request):
    """
    Browse-View auf Basis der MuenztypObjektAnzeige (MTOA).
    Nutzt die flache MTOA-Tabelle und MtoaPerson-Bridge für effiziente Abfragen.
    """
    from ..services.authority_display import display_text
    invnr = request.GET.get('invnr')
    if invnr:
        obj = Obj.objects.only('id').filter(invnr=invnr).first()
        if obj:
            return redirect('Objekt', id=obj.id)
    qs, is_unbestimmt, needs_distinct = _get_filtered_mtoa_queryset(request)

    # Kartenpunkte und Trefferzahl sind besucherunabhängig: gemeinsam cachen
    # (ungefilterte Ansicht / ein Filterwert, siehe services.browse_cache).
    def compute_overview():
        # Database-agnostic grouping for maps
        mints_qs = (
            qs.exclude(mzstaette_fk__isnull=True)
            .values(
                'mzstaette_fk__id',
                'mzstaette',
                'region',
                'mzstaette_fk__lat',
                'mzstaette_fk__long',
            )
            .annotate(
                mint_id     = F('mzstaette_fk__id'),
                mint_name   = F('mzstaette'),
                mint_region = F('region'),
                mint_lat    = F('mzstaette_fk__lat'),
                mint_lon    = F('mzstaette_fk__long'),
                obj_count   = Count('pk', distinct=needs_distinct),
            )
            .order_by('mzstaette_fk__id')
        )

        mints_for_js = [
            {
                'id': m['mint_id'],
                'name': display_text(m['mint_name'], 'Mzstaette'),
                # Filterwert immer der gespeicherte (deutsche) DB-Name; der
                # übersetzte 'name' ist nur Anzeige (sonst 0 Treffer auf /en/).
                'filter_value': m['mint_name'],
                'region': display_text(m['mint_region'], 'Region'),
                'longitude': float(m['mint_lon']) if m['mint_lon'] is not None else None,
                'latitude': float(m['mint_lat']) if m['mint_lat'] is not None else None,
                'count': m['obj_count'],
            }
            for m in mints_qs
            if m['mint_lon'] and m['mint_lat']
        ]
        return {'mints': mints_for_js, 'count': qs.count()}

    overview = browse_cache.get_or_compute(request, 'browse-overview', compute_overview, localized=True)
    mints_for_js = overview['mints']

    page = request.GET.get('page', 1)
    paginator = Paginator(qs, 30)
    paginator.__dict__['count'] = overview['count']  # cached_property vorbelegen: kein zweites COUNT
    anzahl = paginator.count
    variables = request.GET.copy()
    if 'page' in variables:
        del variables['page']

    try:
        qs = paginator.page(page)
    except PageNotAnInteger:
        qs = paginator.page(1)
    except EmptyPage:
        qs = paginator.page(paginator.num_pages)

    context_key = 'unbestimmt' if is_unbestimmt else 'default'
    parameters = FILTER_PARAMETERS.get(context_key, {})

    context = {
        'Objekte': qs,
        'mints_map': json_for_script(mints_for_js),
        'Anzahl': anzahl,
        'getvars': '&{0}'.format(variables.urlencode()),
        'filter_config': parameters,
    }

    return render(request, 'slg/Objektliste_mtoa.html', context)
