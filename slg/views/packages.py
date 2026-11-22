"""Public collection packages, maps and comparison charts."""

from collections import Counter
from itertools import chain

from django.db.models import Count, F
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from slg import structured_data as sd

from ..models import MuenztypObjektAnzeige, Obj, Paket


def _package_preview_entries(package_mtoa, count=3, chunk_size=24):
    """Erste `count` MTOA-Einträge eines Pakets (nach Objekt-ID) mit Bild,
    sonst die ersten `count` überhaupt. Lädt nur so viele Zeilen wie nötig."""
    ordered = package_mtoa.select_related('slg_fk', 'slgteil_fk').order_by('obj_id')
    first_entries = []
    with_images = []
    offset = 0
    while len(with_images) < count:
        chunk = list(ordered[offset:offset + chunk_size])
        if not chunk:
            break
        _refresh_mtoa_image_urls_from_objects(chunk)
        if not first_entries:
            first_entries = chunk[:count]
        with_images.extend(
            entry for entry in chunk
            if entry.thumbnail_av_url or entry.thumbnail_rv_url or entry.av_url or entry.rv_url
        )
        offset += chunk_size
    return (with_images or first_entries)[:count]

def _build_package_distribution(entries, field_name, limit=4):
    counts = Counter()
    for entry in entries:
        value = getattr(entry, field_name, None)
        if not value:
            continue
        normalized_value = str(value).strip()
        if normalized_value:
            counts[normalized_value] += 1

    total = sum(counts.values())
    if not total:
        return []

    return [
        {
            'label': label,
            'count': count,
            'percent': round((count / total) * 100),
        }
        for label, count in counts.most_common(limit)
    ]

def _build_package_chart_data(entries):
    years_counter = Counter()

    for entry in entries:
        start = entry.datierung_von
        end = entry.datierung_bis
        if start is None or end is None:
            continue

        try:
            start = int(start)
            end = int(end)
        except (TypeError, ValueError):
            continue

        if end < start:
            continue

        span = end - start + 1
        if span <= 0 or span > 3000:
            continue

        weight = 1.0 / span
        for year in range(start, end + 1):
            years_counter[year] += weight

    if not years_counter:
        return {'years': [], 'counts': []}

    min_year = min(years_counter.keys())
    max_year = max(years_counter.keys())
    years = list(range(min_year, max_year + 1))
    counts = [round(years_counter.get(year, 0), 3) for year in years]

    return {'years': years, 'counts': counts}

def _build_package_time_extent(entries):
    starts = [
        entry.datierung_von
        for entry in entries
        if entry.datierung_von is not None
    ]
    ends = [
        entry.datierung_bis
        for entry in entries
        if entry.datierung_bis is not None
    ]

    if not starts or not ends:
        return {
            'start': None,
            'end': None,
            'start_label': '',
            'end_label': '',
        }

    start = min(starts)
    end = max(ends)
    return {
        'start': start,
        'end': end,
        'start_label': _format_package_year(start),
        'end_label': _format_package_year(end),
    }

def _get_package_comparison_packages(paket):
    comparison_packages = []
    seen_package_ids = {paket.id}

    for comparison_package in chain(paket.vergleichspakete.all(), paket.vergleichende_pakete.all()):
        if comparison_package.id in seen_package_ids:
            continue
        # Unveröffentlichte Pakete dürfen auch als Vergleich nicht öffentlich erscheinen.
        if not comparison_package.online_freigegeben:
            continue
        seen_package_ids.add(comparison_package.id)
        comparison_packages.append(comparison_package)

    return comparison_packages

def _build_package_chart_series(paket, entries, comparison_packages, comparison_entries_by_package):
    series = [{
        'name': paket.titel_oeffentlich or paket.name,
        **_build_package_chart_data(entries),
    }]

    for comparison_package in comparison_packages:
        comparison_entries = comparison_entries_by_package.get(comparison_package.id, [])
        chart_data = _build_package_chart_data(comparison_entries)
        if chart_data.get('years'):
            series.append({
                'name': comparison_package.titel_oeffentlich or comparison_package.name,
                **chart_data,
            })

    return series

def _refresh_mtoa_image_urls_from_objects(entries):
    obj_ids = [entry.obj_id for entry in entries if entry.obj_id]
    if not obj_ids:
        return entries

    objects_by_id = {
        obj.id: obj
        for obj in (
            Obj.objects
            .filter(id__in=obj_ids)
            .select_related('Slg', 'SlgTeil', 'SlgTeil__idfk_Slg_SlgTeil')
        )
    }

    for entry in entries:
        obj = objects_by_id.get(entry.obj_id)
        if not obj:
            continue

        bild_urls = obj.get_bild_urls() or {}
        entry.av_url = bild_urls.get('av') or entry.av_url
        entry.rv_url = bild_urls.get('rv') or entry.rv_url
        entry.thumbnail_av_url = bild_urls.get('thumbnail_av') or entry.thumbnail_av_url
        entry.thumbnail_rv_url = bild_urls.get('thumbnail_rv') or entry.thumbnail_rv_url
        entry.av_alt_url = bild_urls.get('av_alt') or ''
        entry.rv_alt_url = bild_urls.get('rv_alt') or ''
        entry.thumbnail_av_alt_url = bild_urls.get('thumbnail_av_alt') or ''
        entry.thumbnail_rv_alt_url = bild_urls.get('thumbnail_rv_alt') or ''

    return entries

def _format_package_year(year):
    if year is None:
        return ''
    if year < 0:
        return f"{abs(year)} v.Chr."
    return str(year)

def paket_detail(request, slug):
    paket = get_object_or_404(
        Paket.objects
        .filter(online_freigegeben=True)
        .prefetch_related('vergleichspakete', 'vergleichende_pakete', 'literatur'),
        slug=slug
    )
    objekt_ids = list(Obj.objects.filter(pakete=paket).values_list('id', flat=True))
    kontrollierte_objektanzahl = Obj.objects.filter(
        id__in=objekt_ids,
        workflow__name__iexact='kontrolliert',
    ).count()
    objektanzahl_db = len(objekt_ids)
    offene_objektanzahl = max(objektanzahl_db - kontrollierte_objektanzahl, 0)
    kontrolliert_prozent = round((kontrollierte_objektanzahl / objektanzahl_db) * 100) if objektanzahl_db else 0
    package_entries_qs = (
        MuenztypObjektAnzeige.objects
        .filter(obj_id__in=objekt_ids)
        .select_related('slg_fk', 'slgteil_fk')
        .order_by('-last_modified')
    )
    package_entries = list(
        package_entries_qs
    )
    _refresh_mtoa_image_urls_from_objects(package_entries)
    package_entries_by_obj_id = {entry.obj_id: entry for entry in package_entries}
    package_object_entries = [
        package_entries_by_obj_id[obj_id]
        for obj_id in objekt_ids
        if obj_id in package_entries_by_obj_id
    ]
    entries_with_images = [
        entry for entry in package_entries
        if entry.thumbnail_av_url or entry.thumbnail_rv_url
    ]
    teaser_entries = (entries_with_images or package_entries)[:3]
    teaser_obj_ids = {entry.obj_id for entry in teaser_entries}
    catalog_entries = [
        entry
        for entry in package_entries
        if entry.obj_id not in teaser_obj_ids
    ][:12]

    denomination_distribution = _build_package_distribution(package_object_entries, 'nominal')
    denomination_distribution_full = _build_package_distribution(package_object_entries, 'nominal', limit=None)
    material_distribution = _build_package_distribution(package_object_entries, 'metall', limit=None)
    mint_distribution = _build_package_distribution(package_object_entries, 'mzstaette')
    mint_distribution_full = _build_package_distribution(package_object_entries, 'mzstaette', limit=None)
    mint_markers_qs = (
        package_entries_qs
        .exclude(mzstaette_fk__isnull=True)
        .values(
            'mzstaette_fk__id',
            'mzstaette',
            'region',
            'mzstaette_fk__lat',
            'mzstaette_fk__long',
        )
        .annotate(
            mint_id=F('mzstaette_fk__id'),
            mint_name=F('mzstaette'),
            mint_region=F('region'),
            mint_lat=F('mzstaette_fk__lat'),
            mint_lon=F('mzstaette_fk__long'),
            obj_count=Count('pk'),
        )
        .order_by('mzstaette_fk__id')
    )
    map_markers = [
        {
            'type': 'fund',
            'name': paket.titel_oeffentlich or paket.name,
            'region': paket.get_fundplatz_kontext_display() if paket.fundplatz_kontext else '',
            'latitude': float(paket.fund_lat),
            'longitude': float(paket.fund_lng),
            'count': objektanzahl_db,
        }
        for _ in [paket]
        if paket.fund_lat is not None and paket.fund_lng is not None
    ]
    map_markers.extend([
        {
            'type': 'mint',
            'id': marker['mint_id'],
            'name': marker['mint_name'],
            'region': marker['mint_region'],
            'latitude': float(marker['mint_lat']),
            'longitude': float(marker['mint_lon']),
            'count': marker['obj_count'],
        }
        for marker in mint_markers_qs
        if marker['mint_lat'] is not None and marker['mint_lon'] is not None
    ])

    package_chart_data = _build_package_chart_data(package_object_entries)
    comparison_entries_by_package = {}
    comparison_packages = _get_package_comparison_packages(paket)
    comparison_package_ids = [comparison_package.id for comparison_package in comparison_packages]
    if comparison_package_ids:
        comparison_obj_pairs = list(
            Obj.pakete.through.objects
            .filter(paket_id__in=comparison_package_ids)
            .values_list('paket_id', 'obj_id')
        )
        comparison_obj_ids = [obj_id for _, obj_id in comparison_obj_pairs]
        comparison_entries_by_obj_id = {
            entry.obj_id: entry
            for entry in MuenztypObjektAnzeige.objects.filter(obj_id__in=comparison_obj_ids)
        }
        for comparison_package_id, obj_id in comparison_obj_pairs:
            entry = comparison_entries_by_obj_id.get(obj_id)
            if entry:
                comparison_entries_by_package.setdefault(comparison_package_id, []).append(entry)

    package_chart_series = _build_package_chart_series(
        paket,
        package_object_entries,
        comparison_packages,
        comparison_entries_by_package,
    )
    package_time_extent = _build_package_time_extent(package_object_entries)

    context = {
        'paket': paket,
        'objektanzahl_db': objektanzahl_db,
        'structured_data': sd.paket_graph(request, paket, paket.titel_oeffentlich or paket.name),
        'package_workflow_progress': {
            'added': objektanzahl_db,
            'controlled': kontrollierte_objektanzahl,
            'open': offene_objektanzahl,
            'percent': kontrolliert_prozent,
        },
        'package_entries': package_entries,
        'teaser_entries': teaser_entries,
        'catalog_entries': catalog_entries,
        'denomination_distribution': denomination_distribution,
        'denomination_distribution_full': denomination_distribution_full,
        'material_distribution': material_distribution,
        'primary_material': material_distribution[0] if material_distribution else None,
        'mint_distribution': mint_distribution,
        'mint_distribution_full': mint_distribution_full,
        'package_chart_data': package_chart_data,
        'package_chart_series': package_chart_series,
        'package_time_extent': package_time_extent,
        'package_map_markers': map_markers,
        'package_browse_url': f"{reverse('Objektliste')}?Paket={paket.id}",
    }

    return render(request, 'slg/paket_detail.html', context)
