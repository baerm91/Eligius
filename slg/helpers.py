from django.db.models import Subquery, OuterRef, Prefetch, Count, Min, Max
from collections import defaultdict, OrderedDict
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist

from .models import *
# apply_filters is in views.py, so this import is tricky.
# It's better if apply_filters is in its own filters.py or here.
# For now, assuming it can be imported or we adapt.
from .filters import apply_filters

def serializable_obj(obj, count=None):
    """Objekt in JSON‑freundliches Dict verwandeln."""
    if not obj:
        return None
    
    thumbnail_url = None
    bild_urls = obj.get_bild_urls()
    if bild_urls and bild_urls.get('thumbnail_rv'):
        thumbnail_url = bild_urls['thumbnail_rv']
    elif bild_urls and bild_urls.get('rv'):
        thumbnail_url = bild_urls['rv']

    obj_absolute_url = None
    if hasattr(obj, 'get_absolute_url'):
        try:
            obj_absolute_url = obj.get_absolute_url()
        except Exception:
            pass

    # Erweiterte Münzdaten für Timeline-Tooltips
    mztyp = obj.Typ
    
    # Averslegende: zuerst Objekt, dann Typ
    avleg = obj.avleg or (mztyp.avleg if mztyp else None)
    
    # Rückseitenlegende: zuerst Objekt, dann Typ  
    rvleg = obj.rvleg or (mztyp.rvleg if mztyp else None)
    
    # Aversbeschreibung: zuerst Objekt, dann Typ
    av_bildtyp_name = None
    av_bildtyp = obj.av_bildtyp or (mztyp.av_bildtyp if mztyp else None)
    if av_bildtyp:
        av_bildtyp_name = getattr(av_bildtyp, 'name', str(av_bildtyp))
    
    # Rückseitenbeschreibung: zuerst Objekt, dann Typ
    rv_bildtyp_name = None
    rv_bildtyp = obj.rv_bildtyp or (mztyp.rv_bildtyp if mztyp else None)
    if rv_bildtyp:
        rv_bildtyp_name = getattr(rv_bildtyp, 'name', str(rv_bildtyp))

    result = {
        "id":    obj.pk,
        "thumb": thumbnail_url,
        "url":   obj_absolute_url,
        "avleg": avleg or "",
        "rvleg": rvleg or "",
        "av_bildtyp": av_bildtyp_name or "",
        "rv_bildtyp": rv_bildtyp_name or "",
        "invnr": obj.invnr or ""
    }
    
    if count is not None:
        result["count"] = count
        
    return result

def get_matrix_from_muenztypen(request, obj_pk): # Added obj_pk
    """
    Erzeugt eine Matrix:
        staetten[mz_id]['rows'][rv_id]['cells'][nom_id] = Obj‑Dict|None
    Keys bleiben IDs, Werte sind Strings / Dicts → direkt seriell.
    """
    # --- Establish context from the main object (obj_pk) ---
    try:
        current_obj = Obj.objects.select_related('Typ').get(pk=obj_pk)
    except Obj.DoesNotExist:
        return {"nominale": OrderedDict(), "staetten": OrderedDict(), "error": "Object not found"}

    if not current_obj.Typ:
        return {"nominale": OrderedDict(), "staetten": OrderedDict(), "info": "Object has no Type"}

    dat_von, dat_bis = current_obj.Typ.dat_von, current_obj.Typ.dat_bis
    PH_FUNCS = (1, 6, 7) # Assuming these are PersonFunktion IDs for rulers

    # Get rulers of the current object's type
    # This requires Mztyp_Person model to be accessible via current_obj.Typ.mztyp_person_set
    current_obj_rulers = list(
        current_obj.Typ.mztyp_person_set
        .filter(idfk_PersonFunktion_id__in=PH_FUNCS)
        .values_list('idfk_Person_id', flat=True)
        .distinct()
    )

    if not current_obj_rulers:
        return {"nominale": OrderedDict(), "staetten": OrderedDict(), "info": "No rulers found for context"}
    
    # --- Base QuerySet for Muenztypen based on context ---
    base_typ_qs = (
        Muenztyp.objects
        .filter(dat_von=dat_von, dat_bis=dat_bis)
        .filter(mztyp_person__idfk_Person_id__in=current_obj_rulers,
                mztyp_person__idfk_PersonFunktion_id__in=PH_FUNCS)
    )

    # --- Filter aus der URL gelten für OBJEKTE ---
    # apply_filters kennt nur Obj-Felder (Typ__..., Slg, ...); auf ein
    # Muenztyp-QuerySet angewendet ergab jeder Parameter einen FieldError.
    context_objects = apply_filters(
        request, Obj.objects.filter(Typ_id__in=base_typ_qs.values('pk'))
    )
    # Pro Typ: Anzahl passender Objekte und ein Beispielobjekt (kleinste ID) –
    # eine gruppierte Abfrage statt aller Objekte im Speicher.
    type_stats = {
        row['Typ_id']: (row['anzahl'], row['beispiel'])
        for row in context_objects.order_by().values('Typ_id')
        .annotate(anzahl=Count('pk', distinct=True), beispiel=Min('pk'))
        if row['Typ_id']
    }
    typ_qs = (
        Muenztyp.objects.filter(pk__in=list(type_stats))
        .select_related('Mzstaette', 'Nominal', 'rv_bildtyp', 'av_bildtyp')
    )
    samples = {
        obj.pk: obj for obj in Obj.objects.filter(pk__in=[sample for _, sample in type_stats.values()])
        .select_related('Slg', 'SlgTeil', 'Typ', 'av_bildtyp', 'rv_bildtyp',
                        'Typ__av_bildtyp', 'Typ__rv_bildtyp')
    }

    # --- Strukturen vorbereiten ---
    staetten, nominale, rv_typen = OrderedDict(), OrderedDict(), OrderedDict()
    matrix_tmp = defaultdict(lambda: defaultdict(lambda: defaultdict(dict))) 

    for t in typ_qs:
        mz, nom, rv = t.Mzstaette, t.Nominal, t.rv_bildtyp

        if not (mz and nom and rv): 
            continue
        
        # Ensure 'bezeichnung' or 'name' attribute exists
        mz_name_attr = getattr(mz, 'bezeichnung', getattr(mz, 'name', str(mz.id)))
        nom_name_attr = getattr(nom, 'bezeichnung', getattr(nom, 'name', str(nom.id)))
        rv_name_attr = getattr(rv, 'bezeichnung', getattr(rv, 'name', str(rv.id)))

        staetten.setdefault(mz.id, mz_name_attr)
        nominale.setdefault(nom.id, nom_name_attr)
        rv_typen.setdefault(rv.id, rv_name_attr)

        anzahl, sample_id = type_stats[t.pk]
        matrix_tmp[mz.id][rv.id][nom.id] = serializable_obj(samples.get(sample_id), anzahl)

    # --- In template‑freundliche Struktur umwandeln ---
    matrix_data = OrderedDict() 
    for mz_id, mz_name in staetten.items():
        rows = OrderedDict()
        for rv_id, rv_name in rv_typen.items():
            cells = {
                n_id: matrix_tmp.get(mz_id, {}).get(rv_id, {}).get(n_id)
                for n_id in nominale.keys()
            }
            rows[rv_id] = {"name": rv_name, "cells": cells}
        matrix_data[mz_id] = {"name": mz_name, "rows": rows}

    # Add a summary of counts by reverse side description
    rv_counts = OrderedDict()
    for rv_id, rv_name in rv_typen.items():
        rv_count = 0
        for mz_id in staetten.keys():
            for nom_id in nominale.keys():
                cell = matrix_tmp.get(mz_id, {}).get(rv_id, {}).get(nom_id)
                if cell and 'count' in cell:
                    rv_count += cell['count']
        rv_counts[rv_id] = {"name": rv_name, "count": rv_count}
    
    # --- Häufigkeit der Motive für die Prägeherren (unabhängig von Datierung/Münzstätte/Nominal) ---
    # Gruppiert in der Datenbank statt alle Objekte zu laden und pro Motiv 2 Abfragen.
    ruler_filter = dict(mztyp_person__idfk_Person_id__in=current_obj_rulers,
                        mztyp_person__idfk_PersonFunktion_id__in=PH_FUNCS)
    motif_rows = list(
        Obj.objects
        .filter(Typ__mztyp_person__idfk_Person_id__in=current_obj_rulers,
                Typ__mztyp_person__idfk_PersonFunktion_id__in=PH_FUNCS,
                Typ__rv_bildtyp__isnull=False)
        .order_by()
        .values('Typ__rv_bildtyp_id', 'Typ__rv_bildtyp__name')
        .annotate(anzahl=Count('pk', distinct=True))
    )
    sorted_motifs = sorted(motif_rows, key=lambda row: (-row['anzahl'], row['Typ__rv_bildtyp__name'] or ''))
    motif_ids = [row['Typ__rv_bildtyp_id'] for row in sorted_motifs]
    total_coins = sum(row['anzahl'] for row in sorted_motifs)
    ruler_dates = {
        row['rv_bildtyp_id']: row for row in
        Muenztyp.objects.filter(rv_bildtyp_id__in=motif_ids, **ruler_filter).order_by()
        .values('rv_bildtyp_id').annotate(first_date=Min('dat_von'), last_date=Max('dat_bis'))
    }
    full_dates = {
        row['rv_bildtyp_id']: row for row in
        Muenztyp.objects.filter(rv_bildtyp_id__in=motif_ids).order_by()
        .values('rv_bildtyp_id').annotate(first_used=Min('dat_von'), last_used=Max('dat_bis'))
    }

    motif_list = []
    current_motif_rank = 0
    current_motif_frequency = 0
    current_motif_percentage = 0
    current_motif_first_date = None
    current_motif_last_date = None
    current_motif_id = current_obj.Typ.rv_bildtyp_id if current_obj.Typ and current_obj.Typ.rv_bildtyp else None

    for rank, row in enumerate(sorted_motifs, 1):
        motif_id, motif_count = row['Typ__rv_bildtyp_id'], row['anzahl']
        percentage = (motif_count / total_coins * 100) if total_coins > 0 else 0
        motif_dates = ruler_dates.get(motif_id, {})
        motif_full_date_range = full_dates.get(motif_id, {})
        motif_list.append({
            "id": motif_id,
            "name": row['Typ__rv_bildtyp__name'],
            "count": motif_count,
            "percentage": round(percentage, 1),
            "rank": rank,
            "first_date": motif_dates.get('first_date'),
            "last_date": motif_dates.get('last_date'),
            "first_used": motif_full_date_range.get('first_used'),
            "last_used": motif_full_date_range.get('last_used'),
        })

        # Check if this is the current coin's motif
        if motif_id == current_motif_id:
            current_motif_rank = rank
            current_motif_frequency = motif_count
            current_motif_percentage = round(percentage, 1)
            current_motif_first_date = motif_dates.get('first_date')
            current_motif_last_date = motif_dates.get('last_date')

    ruler_name_str = None
    if current_obj_rulers:
        try:
            # Assuming the first ruler is representative for the context title
            first_ruler_id = current_obj_rulers[0]
            ruler_person = Person.objects.get(pk=first_ruler_id)
            ruler_name_str = ruler_person.name
        except Person.DoesNotExist:
            ruler_name_str = "Unbekannter Prägeherr"
        except IndexError:
            pass # Should not happen if current_obj_rulers is not empty and check above passed

    # dat_von and dat_bis are already defined from current_obj.Typ.dat_von and current_obj.Typ.dat_bis
    # These represent the overall period for the ruler's coin type context.

    ruler_motif_stats = {
        "ruler_name": ruler_name_str,
        "period_start": dat_von, # From current_obj.Typ.dat_von
        "period_end": dat_bis,   # From current_obj.Typ.dat_bis
        "all_motifs": motif_list, # Renamed from "motifs" to "all_motifs"
        "total_coin_count": total_coins,
        "current_motif": {
            "id": current_motif_id,
            "rank": current_motif_rank,
            "frequency": current_motif_frequency,
            "percentage": current_motif_percentage,
            "first_date": current_motif_first_date,
            "last_date": current_motif_last_date
        }
    }

    if not nominale and not staetten and not type_stats:
         return {
             "nominale": nominale, 
             "staetten": matrix_data, 
             "rv_counts": rv_counts,
             "ruler_motif_stats": ruler_motif_stats,
             "info": "No context types found matching criteria."
         }

    # After creating matrix_data but before returning
    # Ensure all motifs in ruler_motif_stats appear in the matrix structure
    for rv_id, rv_name in rv_typen.items():
        # For each mint, ensure this motif has a row
        for mz_id in matrix_data.keys():
            if rv_id not in matrix_data[mz_id]["rows"]:
                # Add empty row for this motif
                cells = {n_id: None for n_id in nominale.keys()}
                matrix_data[mz_id]["rows"][rv_id] = {"name": rv_name, "cells": cells}

    return {
        "nominale": nominale, 
        "staetten": matrix_data, 
        "rv_counts": rv_counts,
        "ruler_motif_stats": ruler_motif_stats
    }

def get_timeline_data(request):
    """
    Gibt Ereignisse für die Zeitleiste basierend auf den Anfrageparametern zurück.
    
    Parameter:
    - von: Startjahr (optional)
    - bis: Endjahr (optional)
    - sammlung: ID der Sammlung (optional)
    - person: ID der Person (optional)
    - thema: Thema/Schlagwort (optional)
    
    Rückgabe:
    Ein Dictionary mit Ereignissen und Metadaten für die Zeitleiste.
    """
    # Parameter aus der Anfrage extrahieren
    params = request.GET
    dat_von = params.get('von')
    dat_bis = params.get('bis')
    sammlung_id = params.get('sammlung')
    person_param = params.get('person')
    thema = params.get('thema')
    
    # Basisabfrage für SLGInformation
    query = SlgInformation.objects.all()
    
    # Filter basierend auf Parametern anwenden
    # Ein Ereignis ohne dat_bis gilt als Zeitpunkt dat_von (wie in der Ausgabe
    # unten: 'dat_bis': info.dat_bis or info.dat_von).
    if dat_von:
        # Ereignisse, die nach oder während des Startdatums stattfinden
        query = query.filter(
            Q(dat_von__gte=dat_von) |
            Q(dat_bis__gte=dat_von)
        )

    if dat_bis:
        # Ereignisse, die vor oder während des Enddatums beginnen; dat_bis IS NULL
        # darf hier nicht herausfallen.
        query = query.filter(
            Q(dat_von__lte=dat_bis) |
            Q(dat_von__isnull=True, dat_bis__lte=dat_bis)
        )
    
    if sammlung_id:
        if str(sammlung_id).strip().isdigit():
            query = query.filter(Slg_id=int(sammlung_id))
        else:
            # Ungültige Sammlungs-ID ignorieren statt ValueError beim Auswerten
            sammlung_id = None
    
    if person_param:
        # Versuchen, nach ID zu filtern, wenn es sich um eine Zahl handelt
        if person_param.isdigit():
            try:
                query = query.filter(person__id=person_param)
            except ValueError:
                pass
        else:
            # Ansonsten nach Name filtern (hier wird die Änderung umgesetzt)
            query = query.filter(person__name__icontains=person_param)
    
    if thema:
        # Ereignisse zu einem bestimmten Thema (einfache Textsuche)
        query = query.filter(
            Q(information__icontains=thema) | 
            Q(dat_verb__icontains=thema)
        )

    # Effizientes Prefetching der verknüpften Daten
    query = query.prefetch_related('person', 'slginformation_ref_set__Ref')
    
    # Nach Datum sortieren
    query = query.order_by('dat_von', 'dat_bis')
    
    # Ereignisse in das Format umwandeln, das die Timeline-Komponente erwartet
    ereignisse = []
    for info in query:
        # Referenzen sammeln
        referenzen = []
        for ref_link in info.slginformation_ref_set.all():
            ref = ref_link.Ref
            referenzen.append({
                'name': str(ref),
                'zitat': ref.zitat if hasattr(ref, 'zitat') else '',
                'nummer': ref_link.nummer
            })
        
        # Personen sammeln
        personen = []
        for person in info.person.all():
            personen.append({
                'id': person.id,
                'name': person.name
            })
        
        # Ereignis erstellen
        ereignis = {
            'id': info.id,
            'dat_von': info.dat_von,
            'dat_bis': info.dat_bis or info.dat_von,
            'dat_verb': info.dat_verb or '',
            'information': info.information,
            'name': info.name,
            'referenzen': referenzen,
            'personen': personen
        }
        ereignisse.append(ereignis)
    
    # Titel und Metadaten bestimmen
    title = "Ereignisse"
    if sammlung_id:
        try:
            sammlung = Slg.objects.get(id=sammlung_id)
            title = f"Geschichte der {sammlung.name}"
        except (ObjectDoesNotExist, ValueError, TypeError):
            pass
    elif person_param:
        try:
            # Wenn person_param eine ID ist
            if person_param.isdigit():
                person = Person.objects.get(id=person_param)
                title = f"Ereignisse zu {person.name}"
            # Wenn person_param ein Name ist
            else:
                title = f"Ereignisse zu {person_param}"
        except ObjectDoesNotExist:
            pass
    elif dat_von and dat_bis:
        title = f"Ereignisse {dat_von}-{dat_bis}"
    elif dat_von:
        title = f"Ereignisse ab {dat_von}"
    elif dat_bis:
        title = f"Ereignisse bis {dat_bis}"
    elif thema:
        title = f"Ereignisse zum Thema '{thema}'"
    
    # Ergebnis zusammenstellen
    result = {
        'title': title,
        'ereignisse': ereignisse,
        'filters': {
            'von': dat_von,
            'bis': dat_bis,
            'sammlung': sammlung_id,
            'person': person_param,
            'thema': thema
        },
        'count': len(ereignisse)
    }
    
    return result
