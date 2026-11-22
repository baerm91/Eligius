"""Public object details and presentation data."""

import re
from itertools import chain

from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext

from slg import structured_data as sd

from ..models import (
    AvBildtyp_Schlagwort,
    Muenztyp,
    Mztyp_Person,
    Mztyp_Wappen,
    Obj,
    Obj_Person,
    Obj_Ref,
    RvBildtyp_Schlagwort,
)
from ..seo import clean_text
from ..services.authority_display import (
    display_label as authority_label,
)
from ..services.authority_display import (
    display_text as authority_text,
)
from .utils import render_beizeichen_html


def _object_labels(obj, coin_data):
    """Lokalisierte Anzeigenamen für die strukturierten Daten einer Objektseite."""
    labels = {
        'collection': authority_label(coin_data['slg']) if coin_data['slg'] else '',
        'nominal': authority_label(coin_data['nominal']) if coin_data['nominal'] else '',
        'metal': authority_label(coin_data['metall']) if coin_data['metall'] else '',
        'mint': authority_label(coin_data['mzstaette']) if coin_data['mzstaette'] else '',
        'object_type': authority_label(coin_data['objekttyp']) if coin_data['objekttyp'] else '',
        'persons': {rel.idfk_Person.pk: authority_text(rel.idfk_Person.name, 'Person')
                    for rel in coin_data['personen'] if getattr(rel, 'idfk_Person', None)},
    }
    labels['title'] = clean_text(coin_data['titel'], limit=0) or obj.invnr
    rulers = list(dict.fromkeys(
        labels['persons'][rel.idfk_Person.pk] for rel in coin_data['personen']
        if getattr(rel, 'idfk_Person', None) and getattr(rel, 'idfk_PersonFunktion_id', None) in sd.RULER_ROLES))
    dating = clean_text(coin_data['dat_verb'], limit=0)
    facts = [labels['nominal'], labels['mint'], dating]
    labels['description'] = clean_text(' – '.join(
        part for part in (f"{labels['collection']} {obj.invnr}".strip(), labels['title'],
                          ', '.join(f for f in facts if f)) if part), limit=300)

    # Seitentitel, Meta-Description und Social Preview
    labels['page_title'] = f"{labels['collection']}: {obj.invnr} - {labels['title']}" if labels['collection'] \
        else f"{obj.invnr} - {labels['title']}"
    summary = ', '.join(f for f in (' / '.join(rulers), labels['nominal'], labels['mint'], dating) if f)
    labels['meta_description'] = clean_text(
        (gettext('Münze %(invnr)s aus der Sammlung %(collection)s: %(title)s.') % {
            'invnr': obj.invnr, 'collection': labels['collection'], 'title': labels['title']}
         if labels['collection'] else f"{obj.invnr}: {labels['title']}.")
        + (f" {summary.rstrip('.')}." if summary else ''))

    # Alt-Texte der Hauptbilder: Seite, Bildbeschreibung, Münze, Inventarnummer, Sammlung
    origin = ', '.join(p for p in (obj.invnr, labels['collection']) if p)
    labels['alt'] = {}
    for side, side_label in (('av', gettext('Avers')), ('rv', gettext('Revers'))):
        motif = coin_data.get(f'{side}_bildtyp')
        motif_text = clean_text(getattr(motif, 'display_name', '') or '', limit=0) if motif else ''
        if not motif_text:
            source = getattr(obj, f'{side}beschr', None) or (getattr(coin_data['Typ'], f'{side}beschr', None)
                                                             if coin_data['Typ'] else None)
            motif_text = clean_text(source, limit=0)
        text = f'{side_label}: {motif_text} – {labels["title"]}' if motif_text else f'{side_label}: {labels["title"]}'
        labels['alt'][side] = clean_text(f'{text} ({origin})', limit=250)
    return labels


def prepare_coin_data(obj):
    mztyp = obj.Typ

    # Use prefetched data instead of new queries
    av_bildtyp_obj = obj.av_bildtyp or (mztyp.av_bildtyp if mztyp else None)
    rv_bildtyp_obj = obj.rv_bildtyp or (mztyp.rv_bildtyp if mztyp else None)

    # Schlagworte from prefetched sets
    av_schlagworte_qs = av_bildtyp_obj.avbildtyp_schlagwort_set.all() \
        if av_bildtyp_obj and hasattr(av_bildtyp_obj, 'avbildtyp_schlagwort_set') else []

    rv_schlagworte_qs = rv_bildtyp_obj.rvbildtyp_schlagwort_set.all() \
        if rv_bildtyp_obj and hasattr(rv_bildtyp_obj, 'rvbildtyp_schlagwort_set') else []

    # Personen from prefetched sets
    mztyp_personen = mztyp.mztyp_person_set.all() \
        if mztyp and hasattr(mztyp, 'mztyp_person_set') else []
    obj_personen = obj.obj_person_set.all() if hasattr(obj, 'obj_person_set') else []

    # Wappen from prefetched set
    wappen_qs = mztyp.mztyp_wappen_set.all() \
        if mztyp and hasattr(mztyp, 'mztyp_wappen_set') else None

    data = {
         'pk': obj.pk,
         'invnr': obj.invnr,
         'durchmesser': obj.durchmesser,
         'gewicht': obj.gewicht,
         'stempelstellung': obj.stempelstellung,
         'av_beizeichen': obj.av_beizeichen or (mztyp.av_beizeichen if mztyp else None),
         'rv_beizeichen': obj.rv_beizeichen or (mztyp.rv_beizeichen if mztyp else None),
         'av_offizin': obj.av_offizin,
         'rv_offizin': obj.rv_offizin,
         'av_offizin_symbol': obj.av_offizin_symbol or (mztyp.av_offizin_symbol if mztyp else None),
         'rv_offizin_symbol': obj.rv_offizin_symbol or (mztyp.rv_offizin_symbol if mztyp else None),
         'bild_urls': obj.get_bild_urls(),
         'titel': obj.titel or (mztyp.titel if mztyp else None),
         'dat_verb': obj.dat_verb or (mztyp.dat_verb if mztyp else None),
         'objekttyp': mztyp.Objekttyp if (mztyp and mztyp.Objekttyp) else (obj.Objekttyp or None),
         'muenzstand': obj.idfk_Muenzstand or (mztyp.Muenzstand if mztyp else None),
         'reichskreis': mztyp.Reichskreis if mztyp else None,
         'nominal': obj.idfk_Nominal or (mztyp.Nominal if mztyp else None),
         'metall': obj.Metall or (mztyp.Metall if mztyp else None),
         'herstellung': obj.idfk_Herstellung or (mztyp.Herstellung if mztyp else None),
         'avleg': obj.avleg or (mztyp.avleg if mztyp else None),
         'rvleg': obj.rvleg or (mztyp.rvleg if mztyp else None),
         # vom Änderungsvorschlag-Formular (scripte.html) vorbelegt
         'avbeschr': obj.avbeschr or (mztyp.avbeschr if mztyp else None),
         'rvbeschr': obj.rvbeschr or (mztyp.rvbeschr if mztyp else None),
         'av_bildtyp': obj.av_bildtyp or (mztyp.av_bildtyp if mztyp else None),
         'rv_bildtyp': obj.rv_bildtyp or (mztyp.rv_bildtyp if mztyp else None),
         'av_schlagworte': av_schlagworte_qs,
         'rv_schlagworte': rv_schlagworte_qs,
         'personen': list(chain(mztyp_personen, obj_personen)),
         'wappen': wappen_qs,
         'slg': obj.Slg,
         'slgteil': obj.SlgTeil,
         'mzstaette': obj.idfk_Mzstaette or (mztyp.Mzstaette if mztyp else None),
         'av_bildrand': obj.av_bildrand or (mztyp.av_bildrand if mztyp else None),
         'rv_bildrand': obj.rv_bildrand or (mztyp.rv_bildrand if mztyp else None),
         'faelschung': obj.faelschung,
         'region': obj.region or (mztyp.region if mztyp else None),
         'Typ': mztyp,
         'Konkordanz': mztyp.Konkordanz.all() if mztyp else None,
         'idfk_Ref': obj.idfk_Ref,
         'Typ_unsicher': obj.Typ_unsicher,
         'obj_ref_set': list(obj.obj_ref_set.all()),
         'anmerkung': obj.anmerkung,
         'Herstellungsmerkmale': list(obj.Herstellungsmerkmale.all()),
         'sekundaere_Merkmale': list(obj.sekundaere_Merkmale.all()),
         'av_beizeichen_display': None,
         'rv_beizeichen_display': None,
         'av_offizin_display': None,
         'rv_offizin_display': None,
         'av_offizin_symbol_html': None,
         'rv_offizin_symbol_html': None,
         'auflage': mztyp.auflage if mztyp else None,
         'beschlussdatum': mztyp.beschlussdatum if mztyp else None,
         'ausgabedatum': mztyp.ausgabedatum if mztyp else None,
    }

    # Prepare offizin symbol HTML if available
    if data['av_offizin_symbol']:
        data['av_offizin_symbol_html'] = data['av_offizin_symbol'].get_svg_html()

    if data['rv_offizin_symbol']:
        data['rv_offizin_symbol_html'] = data['rv_offizin_symbol'].get_svg_html()

    # Browse-Filterwerte für Beizeichen: MTOA speichert den Textnamen mit
    # ersetztem '?' (sync_mtoa.generate_mtoa_from_obj), keine ID.
    for side in ('av', 'rv'):
        bz = data[f'{side}_beizeichen']
        name = (bz.name or '') if bz else ''
        if name and data[f'{side}_offizin']:
            name = name.replace('?', data[f'{side}_offizin'].name or '')
        data[f'{side}_beizeichen_filter'] = name or None

    # Anpassung der Beizeichen-Anzeige für Vorderseite
    if data['av_beizeichen']:
        offizin = data['av_offizin']
        html, offizin_used = render_beizeichen_html(
            data['av_beizeichen'].name, data['av_offizin_symbol_html'],
            (offizin.name or '') if offizin else None)
        # Offizin-Name nur separat anzeigen, wenn er nicht schon im Beizeichen steht
        data['av_offizin_display'] = None if offizin_used else (offizin.name if offizin else None)
        data['av_beizeichen_display'] = html
    elif data['av_offizin']:
        data['av_beizeichen_display'] = None
        data['av_offizin_display'] = data['av_offizin'].name

    # Ähnliche Logik für die Rückseite
    if data['rv_beizeichen']:
        offizin = data['rv_offizin']
        html, offizin_used = render_beizeichen_html(
            data['rv_beizeichen'].name, data['rv_offizin_symbol_html'],
            (offizin.name or '') if offizin else None)
        # Offizin-Name nur separat anzeigen, wenn er nicht schon im Beizeichen steht
        data['rv_offizin_display'] = None if offizin_used else (offizin.name if offizin else None)
        data['rv_beizeichen_display'] = html
    elif data['rv_offizin']:
        data['rv_beizeichen_display'] = None
        data['rv_offizin_display'] = data['rv_offizin'].name

    return data

def ObjektView(request, id):

    # Custom prefetch for schlagworte to avoid N+1 queries
    av_schlagwort_prefetch = Prefetch(
        'av_bildtyp__avbildtyp_schlagwort_set',
        queryset=AvBildtyp_Schlagwort.objects.select_related('schlagwort')
    )

    rv_schlagwort_prefetch = Prefetch(
        'rv_bildtyp__rvbildtyp_schlagwort_set',
        queryset=RvBildtyp_Schlagwort.objects.select_related('schlagwort')
    )

    # Custom prefetch for Typ's av/rv bildtyp schlagworte
    typ_av_schlagwort_prefetch = Prefetch(
        'Typ__av_bildtyp__avbildtyp_schlagwort_set',
        queryset=AvBildtyp_Schlagwort.objects.select_related('schlagwort')
    )

    typ_rv_schlagwort_prefetch = Prefetch(
        'Typ__rv_bildtyp__rvbildtyp_schlagwort_set',
        queryset=RvBildtyp_Schlagwort.objects.select_related('schlagwort')
    )

    # Custom prefetch for person relationships
    obj_person_prefetch = Prefetch(
        'obj_person_set',
        queryset=Obj_Person.objects.select_related('idfk_Person', 'idfk_PersonFunktion').order_by('idfk_PersonFunktion__name')
    )

    mztyp_person_prefetch = Prefetch(
        'Typ__mztyp_person_set',
        queryset=Mztyp_Person.objects.select_related('idfk_Person', 'idfk_PersonFunktion').order_by('idfk_PersonFunktion__name')
    )

    # Custom prefetch for wappen
    mztyp_wappen_prefetch = Prefetch(
        'Typ__mztyp_wappen_set',
        queryset=Mztyp_Wappen.objects.select_related('wappen').order_by('wappen__name')
    )

    obj_ref_prefetch = Prefetch(
        'obj_ref_set',
        queryset=Obj_Ref.objects.select_related('idfk_Ref', 'variante')
    )

    # details.html zeigt pro Konkordanz Ref/Ref.zitat an.
    konkordanz_prefetch = Prefetch(
        'Typ__Konkordanz',
        queryset=Muenztyp.objects.select_related('Ref')
    )

    obj_queryset = Obj.objects.select_related(
        # Existing relationships
        'idfk_Muenzstand', 'idfk_Herstellung', 'Slg', 'SlgTeil', 'idfk_Nominal',
        'idfk_Mzstaette', 'Metall', 'Typ', 'faelschung', 'region', 'av_bildtyp',
        'rv_bildtyp', 'av_beizeichen', 'rv_beizeichen', 'av_bildrand', 'rv_bildrand',
        'Objekttyp',

        # Missing relationships that cause extra queries
        'workflow',
        'av_offizin', 'rv_offizin',
        'av_offizin_symbol', 'rv_offizin_symbol',
        'rand',

        # Typ relationships to reduce queries
        'Typ__workflow',
        'Typ__Objekttyp', 'Typ__Herstellung', 'Typ__Muenzstand', 'Typ__Nominal',
        'Typ__Metall', 'Typ__Mzstaette', 'Typ__region', 'Typ__av_bildtyp',
        'Typ__rv_bildtyp', 'Typ__av_beizeichen', 'Typ__rv_beizeichen',
        'Typ__av_bildrand', 'Typ__rv_bildrand', 'Typ__rand',
        'Typ__av_offizin_symbol', 'Typ__rv_offizin_symbol',
        'Typ__auflage', 'Typ__Ref', 'Typ__Reichskreis',
        'SlgTeil__idfk_Slg_SlgTeil',

    ).prefetch_related(
        'Herstellungsmerkmale', 'sekundaere_Merkmale',
        obj_ref_prefetch,
        obj_person_prefetch,
        mztyp_person_prefetch,
        konkordanz_prefetch,

        av_schlagwort_prefetch,
        rv_schlagwort_prefetch,
        typ_av_schlagwort_prefetch,
        typ_rv_schlagwort_prefetch,

        mztyp_wappen_prefetch,

        'Typ__schlagworte',
        'idfk_Ref'

    )

    obj = get_object_or_404(obj_queryset, id=id)

    coin_data = prepare_coin_data(obj)
    labels = _object_labels(obj, coin_data)

    context = {
        'coin_data': coin_data,
        'test': obj,
        'structured_data': sd.object_graph(request, obj, coin_data, labels),
        'seo': labels,
    }

    return render(request, 'slg/details.html', context)


def objekt_detail_partial(request, id=None):
    # Die Route /objekt_detail_partial/ übergibt keine ID; sie kommt als ?id=.
    obj_id = id if id is not None else request.GET.get('id', '')
    if not re.fullmatch(r'[0-9]+', str(obj_id)):
        raise Http404('Objekt-ID fehlt oder ist ungültig.')
    obj = get_object_or_404(Obj.objects.select_related('Slg'), id=int(obj_id))
    return render(request, 'slg/objekt_detail_partial.html', {'Obj': obj})
