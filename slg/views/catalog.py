"""Catalogue ordering, generation and coin labels."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from ..models import Obj
from .utils import replace_monogram_references


def prepare_coin_labels_html(queryset):
    """
    Bereitet die Daten für HTML-Unterlagszettel vor
    """
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    # Queryset deduplizieren und optimieren
    queryset = queryset.distinct().select_related(
        'Slg', 'SlgTeil', 'Typ', 'idfk_Nominal', 'Metall', 'idfk_Mzstaette',
        'region', 'av_bildtyp', 'rv_bildtyp', 'av_beizeichen', 'rv_beizeichen',
        'av_offizin', 'rv_offizin', 'av_offizin_symbol', 'rv_offizin_symbol',
        'Typ__Mzstaette', 'Typ__Nominal', 'Typ__Metall', 'Typ__Ref', 'Typ__Reichskreis',
        'Typ__Muenzstand', 'idfk_Muenzstand', 'Typ__av_beizeichen', 'Typ__rv_beizeichen',
        'Typ__av_offizin_symbol', 'Typ__rv_offizin_symbol', 'fund'
    )

    coins_data = []

    for obj in queryset:
        mztyp = obj.Typ

        # Systematische Datensammlung orientiert am Export-System
        titel = obj.titel or (mztyp.titel if mztyp else None) or ""

        # Nominal - vollständig ausgeschrieben (robustere Behandlung)
        nominal_obj = obj.idfk_Nominal or (mztyp.Nominal if mztyp else None)
        if nominal_obj and str(nominal_obj) != "None":
            nominal_str = str(nominal_obj)
        else:
            nominal_str = ""

        # Münzstätte bestimmen (robustere Behandlung)
        muenzstaette_obj = obj.idfk_Mzstaette or (mztyp.Mzstaette if mztyp else None)
        if muenzstaette_obj and str(muenzstaette_obj) != "None":
            muenzstaette_str = str(muenzstaette_obj)
        else:
            muenzstaette_str = ""

        # Datierung - orientiert am Export-System
        datierung_verbale = obj.dat_verb or (mztyp.dat_verb if mztyp else None) or ""
        datierung_von = obj.dat_von or (mztyp.dat_von if mztyp else None)
        datierung_bis = obj.dat_bis or (mztyp.dat_bis if mztyp else None)

        # Datierung zusammensetzen falls keine verbale Datierung vorhanden
        if not datierung_verbale and (datierung_von or datierung_bis):
            if datierung_von == datierung_bis and datierung_von:
                datierung = str(datierung_von)
            elif datierung_von and datierung_bis:
                datierung = f"{datierung_von}-{datierung_bis}"
            elif datierung_von:
                datierung = f"ab {datierung_von}"
            elif datierung_bis:
                datierung = f"bis {datierung_bis}"
            else:
                datierung = ""
        else:
            datierung = datierung_verbale

        # Münzstätte und Datierung kombinieren
        muenzstaette_datierung = muenzstaette_str
        if muenzstaette_str and datierung:
            muenzstaette_datierung += f", {datierung}"
        elif datierung:
            muenzstaette_datierung = datierung

        # Kurzzitat - orientiert am Export-System
        kurzzitat = ""
        if mztyp:
            if mztyp.muenztyptitel:
                kurzzitat = mztyp.muenztyptitel
            elif mztyp.Ref:
                kurzzitat = str(mztyp.Ref.abk) if mztyp.Ref.abk else ""
                if mztyp.nummer:
                    kurzzitat += f" {mztyp.nummer}" if kurzzitat else str(mztyp.nummer)
            # Fragezeichen für unsichere Typen hinzufügen
            if kurzzitat and obj.Typ_unsicher:
                kurzzitat += "?"

        # Technische Daten
        durchmesser = obj.durchmesser
        gewicht = obj.gewicht
        stempelstellung = obj.stempelstellung

        # Formatierung der technischen Daten
        gewicht_str = f"{gewicht:.1f}" if gewicht else ""
        durchmesser_str = f"{durchmesser:.1f}" if durchmesser else ""
        stempelstellung_str = f"{stempelstellung}" if stempelstellung else ""

        # Beizeichen-Logik (adaptiert aus prepare_coin_data)
        rv_beizeichen_display = ""
        rv_beizeichen_obj = obj.rv_beizeichen or (mztyp.rv_beizeichen if mztyp else None)
        rv_offizin_obj = obj.rv_offizin
        rv_offizin_symbol_obj = obj.rv_offizin_symbol or (mztyp.rv_offizin_symbol if mztyp else None)

        if rv_beizeichen_obj:
            beizeichen_text = rv_beizeichen_obj.name

            # SVG-Symbole ersetzen (für HTML-Darstellung vereinfacht)
            if rv_offizin_symbol_obj:
                # Vereinfachte Darstellung ohne HTML für Labels
                if "[Offizinszeichen]" in beizeichen_text:
                    symbol_name = getattr(rv_offizin_symbol_obj, 'name', 'Symbol')
                    beizeichen_text = beizeichen_text.replace("[Offizinszeichen]", f"[{symbol_name}]")
                if "[Monogramm]" in beizeichen_text:
                    symbol_name = getattr(rv_offizin_symbol_obj, 'name', 'Symbol')
                    beizeichen_text = beizeichen_text.replace("[Monogramm]", f"[{symbol_name}]")

            # Monogramm-Referenzen ersetzen (vereinfacht)
            beizeichen_text = replace_monogram_references(beizeichen_text)
            # HTML-Tags entfernen für cleane Textdarstellung
            import re
            beizeichen_text = re.sub(r'<[^>]+>', '', beizeichen_text)

            # ? durch Offizin-Namen ersetzen
            if "?" in beizeichen_text and rv_offizin_obj:
                beizeichen_text = beizeichen_text.replace("?", rv_offizin_obj.name)

            rv_beizeichen_display = beizeichen_text
        elif rv_offizin_obj:
            rv_beizeichen_display = rv_offizin_obj.name

        # Fundnummer und Fundjahr (neu hinzugefügt)
        fund_nr_jahr = ""
        try:
            fund = obj.fund if hasattr(obj, 'fund') else None
            if fund:
                if fund.fundnummer and fund.fundjahr:
                    fund_nr_jahr = f"Fdnr./Jahr {fund.fundnummer}/{fund.fundjahr}"
                elif fund.fundnummer:
                    fund_nr_jahr = f"Fdnr. {fund.fundnummer}"
                elif fund.fundjahr:
                    fund_nr_jahr = f"Jahr {fund.fundjahr}"
        except:
            fund_nr_jahr = ""

        coin_data = {
            'titel': titel,
            'nominal': nominal_str,
            'muenzstaette_datierung': muenzstaette_datierung,
            'kurzzitat': kurzzitat,
            'rv_beizeichen': rv_beizeichen_display,
            'gewicht': gewicht_str,
            'durchmesser': durchmesser_str,
            'stempelstellung': stempelstellung_str,
            'inventarnummer': str(obj.invnr),
            'fund_nr_jahr': fund_nr_jahr,  # Neu hinzugefügt
        }

        coins_data.append(coin_data)

    # HTML mit Template rendern
    html_content = render_to_string('slg/coin_labels.html', {
        'coins': coins_data
    })

    # HTTP Response erstellen
    response = HttpResponse(html_content, content_type='text/html; charset=utf-8')
    response['Content-Disposition'] = 'inline; filename="unterlagszettel.html"'

    return response

@staff_member_required
@permission_required(('slg.add_titel', 'slg.change_titel'), raise_exception=True)
def catalog_sort_titles(request):
    """
    View zum Sortieren der Titel für die Katalog-Erstellung
    """
    obj_ids = request.GET.get('obj_ids', '')
    if not obj_ids:
        messages.error(request, 'Keine Objekte ausgewählt.')
        return redirect('admin:slg_obj_changelist')

    try:
        obj_id_list = [int(id_str) for id_str in obj_ids.split(',') if id_str.strip()]
    except ValueError:
        messages.error(request, 'Ungültige Objekt-IDs.')
        return redirect('admin:slg_obj_changelist')

    # Alle verwendeten Titel sammeln
    obj_queryset = Obj.objects.filter(id__in=obj_id_list).select_related('Typ')
    used_titles = set()

    for obj in obj_queryset:
        # Titel vom Objekt oder vom Typ verwenden
        titel = obj.titel or (obj.Typ.titel if obj.Typ else None)
        if titel and titel.strip():
            used_titles.add(titel.strip())

    # Titel in der Datenbank erstellen/aktualisieren
    from ..models import Titel
    titel_objects = []
    for titel_name in used_titles:
        titel_obj, created = Titel.objects.get_or_create(
            name=titel_name,
            defaults={'sortierung': 0}
        )
        titel_objects.append(titel_obj)

    # Titel nach aktueller Sortierung laden
    titel_objects = Titel.objects.filter(name__in=used_titles).order_by('sortierung', 'name')

    if request.method == 'POST' and request.POST.get('action') == 'save_order':
        # Sortierung speichern
        titel_ids = request.POST.getlist('titel_order[]')
        for index, titel_id in enumerate(titel_ids):
            try:
                titel = Titel.objects.get(id=int(titel_id))
                titel.sortierung = index
                titel.save()
            except (ValueError, Titel.DoesNotExist):
                continue

        messages.success(request, 'Titel-Reihenfolge gespeichert.')
        # Weiterleitung zur Katalog-Generierung; nur die geprüften IDs übernehmen,
        # der Rohwert kann \r\n enthalten (BadHeaderError im Location-Header).
        return redirect('/catalog/generate/?' + urlencode({'obj_ids': ','.join(map(str, obj_id_list))}))

    context = {
        'titel_objects': titel_objects,
        'obj_ids': obj_ids,
    }

    return render(request, 'slg/catalog_sort_titles.html', context)

@staff_member_required
@permission_required('slg.view_obj', raise_exception=True)
def catalog_generate(request):
    """
    View zur Generierung des Katalogs als HTML
    """
    obj_ids = request.GET.get('obj_ids', '')
    if not obj_ids:
        messages.error(request, 'Keine Objekte ausgewählt.')
        return redirect('admin:slg_obj_changelist')

    try:
        obj_id_list = [int(id_str) for id_str in obj_ids.split(',') if id_str.strip()]
    except ValueError:
        messages.error(request, 'Ungültige Objekt-IDs.')
        return redirect('admin:slg_obj_changelist')

    # Objekte laden mit optimierten Queries
    obj_queryset = Obj.objects.filter(id__in=obj_id_list).select_related(
        'Slg', 'SlgTeil', 'Typ', 'idfk_Nominal', 'Metall', 'idfk_Mzstaette',
        'region', 'av_bildtyp', 'rv_bildtyp', 'av_beizeichen', 'rv_beizeichen',
        'av_offizin', 'rv_offizin', 'av_offizin_symbol', 'rv_offizin_symbol',
        'Typ__Mzstaette', 'Typ__Nominal', 'Typ__Metall', 'Typ__Ref', 'Typ__Reichskreis',
        'Typ__Muenzstand', 'idfk_Muenzstand', 'Typ__av_beizeichen', 'Typ__rv_beizeichen',
        'Typ__av_offizin_symbol', 'Typ__rv_offizin_symbol', 'faelschung'
    ).prefetch_related(
        'Herstellungsmerkmale', 'sekundaere_Merkmale'
    )

    # Titel sortiert laden
    from ..models import Titel
    titel_objects = Titel.objects.all().order_by('sortierung', 'name')

    # Objekte nach Titeln gruppieren (Original-Objekte behalten für Sortierung)
    from collections import defaultdict
    grouped_original_objects = defaultdict(list)

    for obj in obj_queryset:
        titel = obj.titel or (obj.Typ.titel if obj.Typ else None)
        if titel and titel.strip():
            grouped_original_objects[titel.strip()].append(obj)

    # Sortierungsfunktion für Objekte innerhalb einer Gruppe
    def sort_objects_within_group(obj):
        # Primäre Sortierung: Datierung (dat_von)
        datierung_von = obj.dat_von or (obj.Typ.dat_von if obj.Typ else None)
        datierung_bis = obj.dat_bis or (obj.Typ.dat_bis if obj.Typ else None)

        # Sekundäre Sortierung: Münzstätte
        muenzstaette_obj = obj.idfk_Mzstaette or (obj.Typ.Mzstaette if obj.Typ else None)
        muenzstaette_name = str(muenzstaette_obj) if muenzstaette_obj else ""

        # Sortierkriterien: (datierung_von, datierung_bis, münzstätte_name)
        # None-Werte werden als sehr große Zahlen behandelt, um sie ans Ende zu setzen
        return (
            datierung_von if datierung_von is not None else 9999,
            datierung_bis if datierung_bis is not None else 9999,
            muenzstaette_name
        )

    # Finale Gruppierung nach Titel-Sortierung mit interner Sortierung
    catalog_groups = []
    for titel_obj in titel_objects:
        if titel_obj.name in grouped_original_objects:
            # Objekte innerhalb der Gruppe sortieren
            sorted_objects = sorted(
                grouped_original_objects[titel_obj.name],
                key=sort_objects_within_group
            )

            # Münzdaten für sortierte Objekte vorbereiten
            sorted_coin_data = [
                prepare_coin_data_for_catalog(obj) for obj in sorted_objects
            ]

            catalog_groups.append({
                'title': titel_obj.name,
                'objects': sorted_coin_data
            })

    # HTML rendern
    from django.template.loader import render_to_string
    html_content = render_to_string('slg/catalog.html', {
        'catalog_groups': catalog_groups
    })

    # HTTP Response erstellen
    response = HttpResponse(html_content, content_type='text/html; charset=utf-8')
    response['Content-Disposition'] = 'inline; filename="katalog.html"'

    return response

def prepare_coin_data_for_catalog(obj):
    """
    Bereitet die Münzdaten für den Katalog auf, ähnlich wie prepare_coin_data aus der Detail-Ansicht
    """
    mztyp = obj.Typ

    # Grunddaten
    data = {
        'invnr': obj.invnr,
        'durchmesser': obj.durchmesser,
        'gewicht': obj.gewicht,
        'stempelstellung': obj.stempelstellung,
        'abnutzung': obj.abnutzung,
        'titel': obj.titel or (mztyp.titel if mztyp else None),
        'has_typ': mztyp is not None,
        'anmerkung': obj.anmerkung or "",
    }

    # Avers/Revers Informationen für Objekte ohne Typ
    if not mztyp:
        data['avleg'] = obj.avleg or ""
        data['av_bildtyp'] = str(obj.av_bildtyp) if obj.av_bildtyp else ""
        data['rvleg'] = obj.rvleg or ""
        data['rv_bildtyp'] = str(obj.rv_bildtyp) if obj.rv_bildtyp else ""
    else:
        data['avleg'] = ""
        data['av_bildtyp'] = ""
        data['rvleg'] = ""
        data['rv_bildtyp'] = ""

    # Nominal
    nominal_obj = obj.idfk_Nominal or (mztyp.Nominal if mztyp else None)
    data['nominal'] = str(nominal_obj) if nominal_obj else ""

    # Münzstätte
    muenzstaette_obj = obj.idfk_Mzstaette or (mztyp.Mzstaette if mztyp else None)
    data['muenzstaette'] = str(muenzstaette_obj) if muenzstaette_obj else ""

    # Datierung
    datierung_verbale = obj.dat_verb or (mztyp.dat_verb if mztyp else None) or ""
    datierung_von = obj.dat_von or (mztyp.dat_von if mztyp else None)
    datierung_bis = obj.dat_bis or (mztyp.dat_bis if mztyp else None)

    if not datierung_verbale and (datierung_von or datierung_bis):
        if datierung_von == datierung_bis and datierung_von:
            data['datierung'] = str(datierung_von)
        elif datierung_von and datierung_bis:
            data['datierung'] = f"{datierung_von}-{datierung_bis}"
        elif datierung_von:
            data['datierung'] = f"ab {datierung_von}"
        elif datierung_bis:
            data['datierung'] = f"bis {datierung_bis}"
        else:
            data['datierung'] = ""
    else:
        data['datierung'] = datierung_verbale

    # Kurzzitat (Literatur)
    if mztyp:
        if mztyp.muenztyptitel:
            kurzzitat = mztyp.muenztyptitel
        elif mztyp.Ref:
            kurzzitat = str(mztyp.Ref.abk) if mztyp.Ref.abk else ""
            if mztyp.nummer:
                kurzzitat += f" {mztyp.nummer}" if kurzzitat else str(mztyp.nummer)
        else:
            kurzzitat = ""

        # Fragezeichen für unsichere Typen hinzufügen
        if kurzzitat and obj.Typ_unsicher:
            kurzzitat += "?"
        data['literatur'] = kurzzitat
    else:
        data['literatur'] = ""

    # Beizeichen-Logik für Avers (adaptiert aus prepare_coin_labels_html)
    av_beizeichen_display = ""
    av_beizeichen_obj = obj.av_beizeichen or (mztyp.av_beizeichen if mztyp else None)
    av_offizin_obj = obj.av_offizin
    av_offizin_symbol_obj = obj.av_offizin_symbol or (mztyp.av_offizin_symbol if mztyp else None)

    if av_beizeichen_obj:
        beizeichen_text = av_beizeichen_obj.name

        # SVG-Symbole ersetzen (für HTML-Darstellung vereinfacht)
        if av_offizin_symbol_obj:
            # Vereinfachte Darstellung ohne HTML für Katalog
            if "[Offizinszeichen]" in beizeichen_text:
                symbol_name = getattr(av_offizin_symbol_obj, 'name', 'Symbol')
                beizeichen_text = beizeichen_text.replace("[Offizinszeichen]", f"[{symbol_name}]")
            if "[Monogramm]" in beizeichen_text:
                symbol_name = getattr(av_offizin_symbol_obj, 'name', 'Symbol')
                beizeichen_text = beizeichen_text.replace("[Monogramm]", f"[{symbol_name}]")

        # Monogramm-Referenzen ersetzen (vereinfacht)
        beizeichen_text = replace_monogram_references(beizeichen_text)
        # HTML-Tags entfernen für cleane Textdarstellung
        import re
        beizeichen_text = re.sub(r'<[^>]+>', '', beizeichen_text)

        # ? durch Offizin-Namen ersetzen
        if "?" in beizeichen_text and av_offizin_obj:
            beizeichen_text = beizeichen_text.replace("?", av_offizin_obj.name)

        av_beizeichen_display = beizeichen_text
    elif av_offizin_obj:
        av_beizeichen_display = av_offizin_obj.name

    data['av_beizeichen'] = av_beizeichen_display

    # Beizeichen-Logik für Revers (adaptiert aus prepare_coin_labels_html)
    rv_beizeichen_display = ""
    rv_beizeichen_obj = obj.rv_beizeichen or (mztyp.rv_beizeichen if mztyp else None)
    rv_offizin_obj = obj.rv_offizin
    rv_offizin_symbol_obj = obj.rv_offizin_symbol or (mztyp.rv_offizin_symbol if mztyp else None)

    if rv_beizeichen_obj:
        beizeichen_text = rv_beizeichen_obj.name

        # SVG-Symbole ersetzen (für HTML-Darstellung vereinfacht)
        if rv_offizin_symbol_obj:
            # Vereinfachte Darstellung ohne HTML für Katalog
            if "[Offizinszeichen]" in beizeichen_text:
                symbol_name = getattr(rv_offizin_symbol_obj, 'name', 'Symbol')
                beizeichen_text = beizeichen_text.replace("[Offizinszeichen]", f"[{symbol_name}]")
            if "[Monogramm]" in beizeichen_text:
                symbol_name = getattr(rv_offizin_symbol_obj, 'name', 'Symbol')
                beizeichen_text = beizeichen_text.replace("[Monogramm]", f"[{symbol_name}]")

        # Monogramm-Referenzen ersetzen (vereinfacht)
        beizeichen_text = replace_monogram_references(beizeichen_text)
        # HTML-Tags entfernen für cleane Textdarstellung
        import re
        beizeichen_text = re.sub(r'<[^>]+>', '', beizeichen_text)

        # ? durch Offizin-Namen ersetzen
        if "?" in beizeichen_text and rv_offizin_obj:
            beizeichen_text = beizeichen_text.replace("?", rv_offizin_obj.name)

        rv_beizeichen_display = beizeichen_text
    elif rv_offizin_obj:
        rv_beizeichen_display = rv_offizin_obj.name

    data['rv_beizeichen'] = rv_beizeichen_display

    # Herstellungsmerkmale, sekundäre Merkmale und Fälschung
    herstellungsmerkmale = list(obj.Herstellungsmerkmale.all()) if hasattr(obj, 'Herstellungsmerkmale') else []
    data['herstellungsmerkmale'] = ', '.join([str(merkmal) for merkmal in herstellungsmerkmale]) if herstellungsmerkmale else ""

    sekundaere_merkmale = list(obj.sekundaere_Merkmale.all()) if hasattr(obj, 'sekundaere_Merkmale') else []
    data['sekundaere_merkmale'] = ', '.join([str(merkmal) for merkmal in sekundaere_merkmale]) if sekundaere_merkmale else ""

    data['faelschung'] = str(obj.faelschung) if obj.faelschung else ""

    # Fundkontext (falls vorhanden)
    try:
        fund = obj.fund if hasattr(obj, 'fund') else None
        if fund:
            fund_context_parts = []
            if fund.fundort:
                fund_context_parts.append(str(fund.fundort))
            if fund.parzelle:
                fund_context_parts.append(f"Parzelle {fund.parzelle}")

            # Fundnummer und Fundjahr mit "/" verbinden
            fundnr_jahr = ""
            if fund.fundnummer and fund.fundjahr:
                fundnr_jahr = f"{fund.fundnummer}/{fund.fundjahr}"
            elif fund.fundnummer:
                fundnr_jahr = str(fund.fundnummer)
            elif fund.fundjahr:
                fundnr_jahr = str(fund.fundjahr)

            if fundnr_jahr:
                fund_context_parts.append(fundnr_jahr)

            data['fundkontext'] = ', '.join(fund_context_parts)
        else:
            data['fundkontext'] = ""
    except:
        data['fundkontext'] = ""

    return data
