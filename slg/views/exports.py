"""Object exports for API clients and staff."""

import copy
import re

from django.contrib.admin.views.main import IGNORED_PARAMS
from django.http import HttpResponse, JsonResponse
from django.utils.http import content_disposition_header
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..authentication import QueryParamTokenAuthentication
from ..export_safety import neutralize_dataset, neutralize_formula
from ..models import (
    AvBildtyp_Schlagwort,
    Fund,
    Mztyp_Person,
    Obj,
    Obj_Person,
    RvBildtyp_Schlagwort,
)
from ..permissions import staff_with_perms
from ..resources import ObjLSNOResource
from .utils import _request_object

EXPORT_XLSX_NON_FILTER_PARAMS = ('token', 'auth_token', 'e', 'p', '_changelist_filters')


@api_view(['GET'])
@authentication_classes([QueryParamTokenAuthentication, SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def export_xlsx(request):
    """XLSX-Export der Objektliste mit den Filtern der Admin-Changelist.

    Die Filter werden ausschließlich über ``ObjAdmin``/``ChangeList`` ausgewertet.
    Damit gelten dieselben Regeln wie im Admin (``lookup_allowed``): nur die dort
    konfigurierten ``list_filter``-Pfade und Suchfelder sind erlaubt. Beliebige
    ORM-Traversals (z. B. ``aenderungen__bearbeitet_von__password__startswith``)
    werden mit HTTP 400 abgewiesen, statt als Blind-Orakel zu dienen.
    """
    from django.contrib import admin as django_admin
    from django.contrib.admin.options import IncorrectLookupParameters
    from django.core.exceptions import (
        FieldDoesNotExist,
        FieldError,
        SuspiciousOperation,
        ValidationError,
    )

    user = request.user
    if not (user and user.is_active and user.is_staff and user.has_perm('slg.view_obj')):
        return JsonResponse({"error": "Keine Berechtigung für den Objekt-Export."}, status=403)

    model_admin = django_admin.site._registry.get(Obj)
    if model_admin is None:
        return JsonResponse({"error": "Objekt-Admin nicht verfügbar."}, status=500)

    django_request = request._request
    params = django_request.GET.copy()
    for name in EXPORT_XLSX_NON_FILTER_PARAMS:
        params.pop(name, None)

    cl_request = copy.copy(django_request)
    cl_request.GET = params
    cl_request.user = user

    try:
        changelist = model_admin.get_changelist_instance(cl_request)
        queryset = changelist.queryset
    except (IncorrectLookupParameters, SuspiciousOperation, FieldError, FieldDoesNotExist, ValidationError, ValueError):
        return JsonResponse({"error": "Ungültige Filterparameter."}, status=400)

    resource = ObjLSNOResource()
    dataset = neutralize_dataset(resource.export(queryset))
    response = HttpResponse(
        dataset.xlsx,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    has_filters = any(key not in IGNORED_PARAMS for key in params.keys())
    filename_base = 'obj_filter' if has_filters else 'objekte'
    response['Content-Disposition'] = f'attachment; filename="{filename_base}_export.xlsx"'
    return response


@api_view(['POST'])
@authentication_classes([QueryParamTokenAuthentication, SessionAuthentication, TokenAuthentication])
@permission_classes([staff_with_perms('slg.view_obj')])
def export_coins_api(request):
    """Accept a JSON payload {"invnrs": [...]} and return the coin list CSV export.

    Mirrors the behavior of the admin action "Münzliste exportieren" for remote callers
    (e.g. Concordia), but selects the Obj rows by inventory number instead of by admin
    queryset. Optionally accepts a `filename` field for the Content-Disposition.
    """
    payload = _request_object(request)
    invnrs = payload.get('invnrs') or []
    if not isinstance(invnrs, list):
        return Response({'error': "'invnrs' must be a list"}, status=400)

    cleaned_invnrs = []
    seen = set()
    for value in invnrs:
        text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned_invnrs.append(text)

    if not cleaned_invnrs:
        return Response({'error': "'invnrs' list is empty"}, status=400)

    base_qs = Obj.objects.filter(invnr__in=cleaned_invnrs)
    distinct_pks = base_qs.values('pk').distinct().values_list('pk', flat=True)
    queryset = Obj.objects.filter(pk__in=distinct_pks).select_related(
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
        'rv_offizin',
    ).prefetch_related(
        'Herstellungsmerkmale',
        'sekundaere_Merkmale',
        'Ppl',
        'idfk_Ref',
    )

    response = prepare_coin_data_export(queryset)

    filename = re.sub(r'[\x00-\x1f\x7f"\\/;]', '_', str(payload.get('filename') or '')).strip()[:150]
    filename = filename or 'exported_coins.csv'
    if not filename.lower().endswith('.csv'):
        filename = f"{filename}.csv"
    response['Content-Disposition'] = content_disposition_header(True, filename)

    # Informative header for proxies that need to know how many rows matched.
    response['X-Export-Matched-Invnrs'] = str(len(distinct_pks))
    response['X-Export-Requested-Invnrs'] = str(len(cleaned_invnrs))
    return response


def _clean_export_invnrs(values):
    cleaned_invnrs = []
    seen = set()
    for value in values or []:
        text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned_invnrs.append(text)
    return cleaned_invnrs


def _export_datetime(value):
    if not value:
        return ''
    return value.isoformat()


@api_view(['POST'])
@authentication_classes([QueryParamTokenAuthentication, SessionAuthentication, TokenAuthentication])
@permission_classes([staff_with_perms('slg.view_obj')])
def export_coin_states_api(request):
    """Return current object/type modification timestamps for inventory numbers."""
    payload = _request_object(request)
    invnrs = payload.get('invnrs') or []
    if not isinstance(invnrs, list):
        return Response({'error': "'invnrs' must be a list"}, status=400)

    cleaned_invnrs = _clean_export_invnrs(invnrs)
    if not cleaned_invnrs:
        return Response({'error': "'invnrs' list is empty"}, status=400)

    queryset = Obj.objects.filter(invnr__in=cleaned_invnrs).select_related(
        'Slg',
        'SlgTeil',
        'Typ',
    )
    order_map = {invnr: index for index, invnr in enumerate(cleaned_invnrs)}
    rows = sorted(
        queryset,
        key=lambda obj: (order_map.get(str(obj.invnr), len(order_map)), obj.pk),
    )

    results = []
    matched_invnrs = set()
    for obj in rows:
        mztyp = obj.Typ
        invnr = str(obj.invnr or '').strip()
        matched_invnrs.add(invnr)
        results.append({
            'invnr': invnr,
            'obj_pk': obj.pk,
            'typ_pk': mztyp.pk if mztyp else None,
            'obj_modified_at': _export_datetime(obj.modified_at),
            'type_modified_at': _export_datetime(mztyp.modified_at) if mztyp else '',
            'sammlung': str(obj.Slg) if obj.Slg else '',
            'sammlungsteil': str(obj.SlgTeil) if obj.SlgTeil else '',
        })

    return Response({
        'ok': True,
        'requested': len(cleaned_invnrs),
        'matched': len(results),
        'unmatched_invnrs': [invnr for invnr in cleaned_invnrs if invnr not in matched_invnrs],
        'results': results,
    })


def prepare_coin_data_export(queryset):
    # Stelle sicher, dass das queryset eindeutig ist
    queryset = queryset.distinct()

    import csv
    import io
    from django.http import StreamingHttpResponse
    from collections import defaultdict

    # Hilfsfunktion: str() nur wenn nicht None, sonst leerer String
    def safe_str(value):
        return str(value) if value is not None else ''

    # CSV Header definieren
    fieldnames = [
        'pk', 'workflow_objekt', 'workflow_mztyp', 'Inv.-Nr.', 'Objekt zuletzt bearbeitet',
        'Münztyp-ID', 'Münztyp zuletzt bearbeitet', 'Durchmesser', 'Gewicht',
        'Stempelstellung', 'Abnutzung', 'Sammlung', 'Sammlungsteil', 'Münzstätte', 'Region',
        'praegeherren', 'Titel', 'Datierung verbale', 'Datierung von', 'Datierung bis',
        'Objekttyp', 'Münzstand', 'Reichskreis', 'Nominal', 'Metall', 'herstellung',
        'personen_av', 'avleg', 'av_bildtyp', 'av_schlagworte', 'av_beizeichen', 'av_offizin',
        'personen_rv', 'rvleg', 'rv_bildtyp', 'rv_schlagworte', 'rv_beizeichen', 'rv_offizin',
        'Wappen', 'Fälschung', 'Typ', 'Konkordanz', 'Zitate', 'Typ_unsicher', 'TempTyp', 'obj_ref_set',
        'anmerkung', 'Herstellungsmerkmale', 'sekundaere_Merkmale', 'Avers', 'Revers',
        # Fundinformationen
        'fund_maßnahmennr', 'fund_fundnummer', 'fund_fundnummerzusatz', 'fund_kistennr',
        'fund_fundort', 'fund_parzelle', 'fund_fundstelle', 'fund_lm_von', 'fund_lm_bis',
        'fund_niveautiefe_von', 'fund_niveautiefe_bis', 'fund_niveau', 'fund_vn', 'fund_vno',
        'fund_vo', 'fund_vso', 'fund_vs', 'fund_vsw', 'fund_vw', 'fund_vnw', 'fund_schnitt',
        'fund_bereichsbezeichnung', 'fund_sondage', 'fund_quadrant', 'fund_quadrantzusatz',
        'fund_flaeche', 'fund_se', 'fund_stratum', 'fund_funddatum', 'fund_fundjahr',
        'fund_andere_materialien', 'fund_fundposition', 'fund_fundkontext', 'fund_anmerkung',
        'fund_bearbeiter'
    ]

    def data_generator():
        BATCH_SIZE = 500  # Prozessiere 500 Objekte auf einmal
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)

        # Header schreiben
        writer.writeheader()
        yield buffer.getvalue().encode('utf-8')
        buffer.seek(0)
        buffer.truncate(0)

        # Verbesserte Queryset-Optimierung
        optimized_queryset = queryset.select_related(
            'Slg', 'SlgTeil', 'Typ', 'Typ__Objekttyp', 'Typ__Herstellung',
            'Typ__Reichskreis', 'Typ__Muenzstand', 'Typ__Nominal', 'Typ__Metall',
            'Typ__Mzstaette', 'Typ__region', 'Typ__av_bildtyp', 'Typ__rv_bildtyp',
            'Typ__av_beizeichen', 'Typ__rv_beizeichen', 'Typ__workflow',
            'idfk_Nominal', 'Metall', 'idfk_Mzstaette', 'region', 'workflow',
            'av_bildtyp', 'rv_bildtyp', 'av_beizeichen', 'rv_beizeichen',
            'av_offizin', 'rv_offizin', 'faelschung', 'idfk_Muenzstand',
            'idfk_Herstellung', 'Objekttyp'
        ).prefetch_related(
            'Herstellungsmerkmale', 'sekundaere_Merkmale', 'obj_ref_set',
            'Typ__Konkordanz', 'Typ__mztyp_wappen_set__wappen'
        )

        # Prozessiere in Batches
        processed_count = 0
        seen_pks = set()

        # Keyset-Paginierung über pk: LIMIT/OFFSET ohne feste Sortierung kann
        # bei >500 Objekten Zeilen überspringen oder doppelt liefern.
        optimized_queryset = optimized_queryset.order_by('pk')
        last_pk = None
        while True:
            page_qs = optimized_queryset if last_pk is None else optimized_queryset.filter(pk__gt=last_pk)
            batch = list(page_qs[:BATCH_SIZE])

            if not batch:
                break
            last_pk = batch[-1].pk

            # Alle IDs für diese Batch sammeln
            obj_ids = [obj.pk for obj in batch if obj.pk not in seen_pks]
            mztyp_ids = [obj.Typ.pk for obj in batch if obj.Typ and obj.pk not in seen_pks]

            # Bulk-Load aller zusätzlichen Daten
            # 1. Fund-Daten
            fund_data = {}
            if obj_ids:
                funds = Fund.objects.filter(objekt__pk__in=obj_ids).select_related('fundort')
                fund_data = {fund.objekt_id: fund for fund in funds}

            # 2. Schlagwort-Daten
            av_schlagworte_data = defaultdict(list)
            rv_schlagworte_data = defaultdict(list)
            if mztyp_ids:
                av_bildtyp_ids = [obj.Typ.av_bildtyp.pk for obj in batch if obj.Typ and obj.Typ.av_bildtyp]
                rv_bildtyp_ids = [obj.Typ.rv_bildtyp.pk for obj in batch if obj.Typ and obj.Typ.rv_bildtyp]

                if av_bildtyp_ids:
                    av_schlagworte = AvBildtyp_Schlagwort.objects.filter(
                        avbildtyp__pk__in=av_bildtyp_ids
                    ).select_related('schlagwort')
                    for rel in av_schlagworte:
                        av_schlagworte_data[rel.avbildtyp_id].append(str(rel.schlagwort))

                if rv_bildtyp_ids:
                    rv_schlagworte = RvBildtyp_Schlagwort.objects.filter(
                        rvbildtyp__pk__in=rv_bildtyp_ids
                    ).select_related('schlagwort')
                    for rel in rv_schlagworte:
                        rv_schlagworte_data[rel.rvbildtyp_id].append(str(rel.schlagwort))

            # 3. Personen-Daten (bulk)
            mztyp_personen_data = defaultdict(lambda: {'praegeherren': [], 'personen_av': [], 'personen_rv': []})
            obj_personen_data = defaultdict(lambda: {'praegeherren': [], 'personen_av': [], 'personen_rv': []})

            if mztyp_ids:
                mztyp_personen = Mztyp_Person.objects.filter(
                    Mztyp__pk__in=mztyp_ids
                ).select_related('idfk_Person', 'idfk_PersonFunktion')

                for rel in mztyp_personen:
                    person_name = rel.idfk_Person.name
                    if rel.idfk_PersonFunktion.id in [1, 6, 7]:
                        mztyp_personen_data[rel.Mztyp_id]['praegeherren'].append(person_name)
                    elif rel.idfk_PersonFunktion.id == 2:
                        if rel.appears_on_rev:
                            mztyp_personen_data[rel.Mztyp_id]['personen_rv'].append(person_name)
                        else:
                            mztyp_personen_data[rel.Mztyp_id]['personen_av'].append(person_name)

            if obj_ids:
                obj_personen = Obj_Person.objects.filter(
                    idfk_Obj__pk__in=obj_ids
                ).select_related('idfk_Person', 'idfk_PersonFunktion')

                for rel in obj_personen:
                    person_name = rel.idfk_Person.name
                    if rel.idfk_PersonFunktion.id in [1, 6, 7]:
                        obj_personen_data[rel.idfk_Obj_id]['praegeherren'].append(person_name)
                    elif rel.idfk_PersonFunktion.id == 2:
                        if rel.appears_on_rev:
                            obj_personen_data[rel.idfk_Obj_id]['personen_rv'].append(person_name)
                        else:
                            obj_personen_data[rel.idfk_Obj_id]['personen_av'].append(person_name)

            # Jetzt alle Objekte in diesem Batch verarbeiten
            rows_to_write = []

            for obj in batch:
                if obj.pk in seen_pks:
                    continue
                seen_pks.add(obj.pk)

                mztyp = obj.Typ
                fund = fund_data.get(obj.pk)

                # Personen-Daten
                if mztyp:
                    personen = mztyp_personen_data[mztyp.pk]
                else:
                    personen = obj_personen_data[obj.pk]

                # Schlagwort-Daten
                av_schlagworte = av_schlagworte_data.get(mztyp.av_bildtyp.pk if mztyp and mztyp.av_bildtyp else None, [])
                rv_schlagworte = rv_schlagworte_data.get(mztyp.rv_bildtyp.pk if mztyp and mztyp.rv_bildtyp else None, [])

                # Hilfswerte für Münzstätte und Region berechnen
                muenzstaette_val = obj.idfk_Mzstaette or (mztyp.Mzstaette if mztyp else None)
                region_val = obj.region or (mztyp.region if mztyp else None)
                av_bildtyp_val = obj.av_bildtyp or (mztyp.av_bildtyp if mztyp else None)
                rv_bildtyp_val = obj.rv_bildtyp or (mztyp.rv_bildtyp if mztyp else None)
                av_beizeichen_val = obj.av_beizeichen or (mztyp.av_beizeichen if mztyp else None)
                rv_beizeichen_val = obj.rv_beizeichen or (mztyp.rv_beizeichen if mztyp else None)

                data = {
                    'pk': obj.pk,
                    'workflow_objekt': safe_str(obj.workflow),
                    'workflow_mztyp': safe_str(mztyp.workflow) if mztyp else '',
                    'Inv.-Nr.': safe_str(obj.invnr),
                    'Objekt zuletzt bearbeitet': _export_datetime(obj.modified_at),
                    'Münztyp-ID': mztyp.pk if mztyp else '',
                    'Münztyp zuletzt bearbeitet': _export_datetime(mztyp.modified_at) if mztyp else '',
                    'Durchmesser': obj.durchmesser,
                    'Gewicht': obj.gewicht,
                    'Stempelstellung': obj.stempelstellung,
                    'Abnutzung': obj.abnutzung,
                    'Sammlung': safe_str(obj.Slg),
                    'Sammlungsteil': safe_str(obj.SlgTeil),
                    'Münzstätte': safe_str(muenzstaette_val),
                    'Region': safe_str(region_val),
                    'praegeherren': ', '.join(personen['praegeherren']),
                    'Titel': obj.titel or (mztyp.titel if mztyp else '') or '',
                    'Datierung verbale': obj.dat_verb or (mztyp.dat_verb if mztyp else '') or '',
                    'Datierung von': obj.dat_von or (mztyp.dat_von if mztyp else None),
                    'Datierung bis': obj.dat_bis or (mztyp.dat_bis if mztyp else None),
                    'Objekttyp': safe_str(mztyp.Objekttyp if (mztyp and mztyp.Objekttyp) else obj.Objekttyp),
                    'Münzstand': safe_str(obj.idfk_Muenzstand or (mztyp.Muenzstand if mztyp else None)),
                    'Reichskreis': safe_str(mztyp.Reichskreis) if mztyp else '',
                    'Nominal': safe_str(obj.idfk_Nominal or (mztyp.Nominal if mztyp else None)),
                    'Metall': safe_str(obj.Metall or (mztyp.Metall if mztyp else None)),
                    'herstellung': safe_str(obj.idfk_Herstellung or (mztyp.Herstellung if mztyp else None) or 'Prägung'),
                    'personen_av': ', '.join(personen['personen_av']),
                    'avleg': obj.avleg or (mztyp.avleg if mztyp else '') or '',
                    'av_bildtyp': safe_str(av_bildtyp_val),
                    'av_schlagworte': ', '.join(av_schlagworte),
                    'av_beizeichen': safe_str(av_beizeichen_val),
                    'av_offizin': safe_str(obj.av_offizin),
                    'personen_rv': ', '.join(personen['personen_rv']),
                    'rvleg': obj.rvleg or (mztyp.rvleg if mztyp else '') or '',
                    'rv_bildtyp': safe_str(rv_bildtyp_val),
                    'rv_schlagworte': ', '.join(rv_schlagworte),
                    'rv_beizeichen': safe_str(rv_beizeichen_val),
                    'rv_offizin': safe_str(obj.rv_offizin),
                    'Wappen': ', '.join([str(w.wappen) for w in mztyp.mztyp_wappen_set.all()]) if mztyp else '',
                    'Fälschung': safe_str(obj.faelschung),
                    'Typ': safe_str(mztyp),
                    'Konkordanz': ', '.join([str(konkordanz) for konkordanz in mztyp.Konkordanz.all()]) if mztyp else '',
                    'Zitate': ('Referenz unsicher: ' if obj.Typ_unsicher else '') + (' = '.join([str(mztyp)] + [str(konkordanz) for konkordanz in mztyp.Konkordanz.all()]) if mztyp else (obj.anmerkung or '')),
                    'Typ_unsicher': obj.Typ_unsicher,
                    'TempTyp': obj.TempTyp or '',
                    'obj_ref_set': ', '.join([str(ref) for ref in obj.obj_ref_set.all()]),
                    'anmerkung': obj.anmerkung or '',
                    'Herstellungsmerkmale': ', '.join([str(merkmal) for merkmal in obj.Herstellungsmerkmale.all()]),
                    'sekundaere_Merkmale': ', '.join([str(merkmal) for merkmal in obj.sekundaere_Merkmale.all()]),
                }

                # Fundinformationen hinzufügen
                if fund:
                    data.update({
                        'fund_maßnahmennr': fund.maßnahmennr,
                        'fund_fundnummer': fund.fundnummer,
                        'fund_fundnummerzusatz': fund.fundnummerzusatz,
                        'fund_kistennr': fund.kistennr,
                        'fund_fundort': fund.fundort.name if fund.fundort else '',
                        'fund_parzelle': fund.parzelle,
                        'fund_fundstelle': fund.fundstelle,
                        'fund_lm_von': fund.lm_von,
                        'fund_lm_bis': fund.lm_bis,
                        'fund_niveautiefe_von': fund.niveautiefe_in_m_von,
                        'fund_niveautiefe_bis': fund.niveautiefe_in_m_bis,
                        'fund_niveau': fund.niveau,
                        'fund_vn': fund.vn, 'fund_vno': fund.vno, 'fund_vo': fund.vo,
                        'fund_vso': fund.vso, 'fund_vs': fund.vs, 'fund_vsw': fund.vsw,
                        'fund_vw': fund.vw, 'fund_vnw': fund.vnw,
                        'fund_schnitt': fund.schnitt,
                        'fund_bereichsbezeichnung': fund.bereichsbezeichnung,
                        'fund_sondage': fund.sondage, 'fund_quadrant': fund.quadrant,
                        'fund_quadrantzusatz': fund.quadrantzusatz, 'fund_flaeche': fund.flaeche,
                        'fund_se': fund.se, 'fund_stratum': fund.stratum,
                        'fund_funddatum': fund.funddatum, 'fund_fundjahr': fund.fundjahr,
                        'fund_andere_materialien': fund.andere_materialien,
                        'fund_fundposition': fund.fundposition, 'fund_fundkontext': fund.fundkontext,
                        'fund_anmerkung': fund.anmerkung, 'fund_bearbeiter': fund.bearbeiter,
                    })
                else:
                    # Setze alle Fund-Felder auf leeren String
                    for field in fieldnames:
                        if field.startswith('fund_') and field not in data:
                            data[field] = ''

                # Avers/Revers zusammensetzen
                av_components = []
                if data['avleg']:
                    av_components.append(data['avleg'])
                if data['av_bildtyp']:
                    av_components.append(data['av_bildtyp'])
                if data['av_beizeichen']:
                    beizeichen_text = data['av_beizeichen']
                    if "?" in beizeichen_text and data['av_offizin']:
                        beizeichen_text = beizeichen_text.replace("?", data['av_offizin'])
                    av_components.append(beizeichen_text)
                data['Avers'] = '. '.join(filter(None, av_components))

                rv_components = []
                if data['rvleg']:
                    rv_components.append(data['rvleg'])
                if data['rv_bildtyp']:
                    rv_components.append(data['rv_bildtyp'])
                if data['rv_beizeichen']:
                    beizeichen_text = data['rv_beizeichen']
                    if "?" in beizeichen_text and data['rv_offizin']:
                        beizeichen_text = beizeichen_text.replace("?", data['rv_offizin'])
                    rv_components.append(beizeichen_text)
                data['Revers'] = '. '.join(filter(None, rv_components))

                # String-Konvertierung für CSV-Kompatibilität
                for key, value in data.items():
                    if value is None:
                        data[key] = ''
                    elif not isinstance(value, (str, int, float)):
                        data[key] = str(value)

                rows_to_write.append(data)

            # Schreibe alle Zeilen dieses Batches auf einmal
            for row_data in rows_to_write:
                writer.writerow({key: neutralize_formula(value) for key, value in row_data.items()})

            # Yield den gesamten Batch
            if rows_to_write:
                yield buffer.getvalue().encode('utf-8')
                buffer.seek(0)
                buffer.truncate(0)

    response = StreamingHttpResponse(
        data_generator(),
        content_type='text/csv; charset=utf-8'
    )
    response['Content-Disposition'] = 'attachment; filename="exported_coins.csv"'
    return response
