"""REST endpoints for coin types, concordances and duplication."""

import re

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Min, Q
from django.http import JsonResponse
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import QueryParamTokenAuthentication
from ..models import (
    AvBildtyp,
    Muenzstand,
    Muenztyp,
    Mzstaette,
    Mztyp_Person,
    Mztyp_Schlagwort,
    Nominal,
    OffizinSymbol,
    Person,
    PersonFunktion,
    Ref,
    RvBeizeichen,
    RvBildtyp,
    Typ_Ref,
)
from ..permissions import AuthenticatedReadStaffModelWrite, staff_with_perms
from ..serializers import MuenztypFilterSerializer, MuenztypSerializer
from ..services.type_metadata import process_download_infos
from .utils import _request_object


@api_view(['GET'])
@authentication_classes([QueryParamTokenAuthentication, SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_konkordanzen(request):
    typ_id = request.GET.get('typ', None)
    konkordanzen = []

    if not typ_id:
        return JsonResponse({"konkordanzen": konkordanzen})

    try:
        typ_id = int(typ_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "Parameter 'typ' muss eine Zahl sein.", "konkordanzen": []}, status=400)

    typ = Muenztyp.objects.filter(id=typ_id).first()
    if not typ:
        return JsonResponse({"error": "Muenztyp nicht gefunden.", "konkordanzen": []}, status=404)

    for konkordanz in typ.Konkordanz.all():
        konkordanzen.append({"id": konkordanz.id, "titel": str(konkordanz)})

    return JsonResponse({"konkordanzen": konkordanzen})

@api_view(['POST'])
@authentication_classes([QueryParamTokenAuthentication, SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def konkordanzen_bulk(request):
    data = _request_object(request)
    raw_type_ids = data.get('type_ids') or data.get('ids') or []
    if not isinstance(raw_type_ids, list):
        return Response({'ok': False, 'error': 'type_ids must be a list'}, status=400)

    type_ids = []
    seen = set()
    for raw in raw_type_ids:
        try:
            type_id = int(raw)
        except (TypeError, ValueError):
            continue
        if type_id <= 0 or type_id in seen:
            continue
        seen.add(type_id)
        type_ids.append(type_id)

    if not type_ids:
        return Response({'ok': True, 'konkordanzen_by_type': {}, 'errors': {}})

    konkordanzen_by_type = {str(type_id): [] for type_id in type_ids}
    qs = Muenztyp.objects.filter(id__in=type_ids).prefetch_related('Konkordanz')
    for typ in qs:
        konkordanzen_by_type[str(typ.id)] = [
            {'id': konkordanz.id, 'titel': str(konkordanz)}
            for konkordanz in typ.Konkordanz.all()
        ]

    return Response({'ok': True, 'konkordanzen_by_type': konkordanzen_by_type, 'errors': {}})


@api_view(['POST'])
@authentication_classes([QueryParamTokenAuthentication, SessionAuthentication, TokenAuthentication])
@permission_classes([staff_with_perms('slg.change_muenztyp')])
def muenztyp_konkordanz_create(request, type_id=None):
    data = _request_object(request)
    source_type_id = type_id or data.get('source_type_id') or data.get('typ')
    target_type_id = data.get('target_type_id') or data.get('konkordanz') or data.get('Konkordanz')

    try:
        source_type_id = int(source_type_id)
        target_type_id = int(target_type_id)
    except (TypeError, ValueError):
        return Response({'ok': False, 'error': 'source_type_id and target_type_id must be numeric'}, status=400)

    if source_type_id <= 0 or target_type_id <= 0:
        return Response({'ok': False, 'error': 'source_type_id and target_type_id must be positive'}, status=400)
    if source_type_id == target_type_id:
        return Response({'ok': False, 'error': 'Ein Münztyp kann nicht mit sich selbst konkordiert werden'}, status=400)

    source = Muenztyp.objects.filter(pk=source_type_id).first()
    target = Muenztyp.objects.filter(pk=target_type_id).first()
    if not source:
        return Response({'ok': False, 'error': 'Quell-Münztyp nicht gefunden'}, status=404)
    if not target:
        return Response({'ok': False, 'error': 'Ziel-Münztyp nicht gefunden'}, status=404)

    already_linked = source.Konkordanz.filter(pk=target.pk).exists()
    with transaction.atomic():
        source.Konkordanz.add(target)

    konkordanzen = [
        {'id': konkordanz.id, 'titel': str(konkordanz)}
        for konkordanz in source.Konkordanz.all()
    ]
    return Response({
        'ok': True,
        'source_type_id': source.pk,
        'target_type_id': target.pk,
        'created': not already_linked,
        'konkordanzen': konkordanzen,
    }, status=200)


class MuenztypListCreate(generics.ListCreateAPIView):
    serializer_class = MuenztypSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = Muenztyp.objects.all()
        muenztyptitel = self.request.query_params.get('muenztyptitel', None)
        if muenztyptitel is not None:
            queryset = queryset.filter(muenztyptitel=muenztyptitel)
        link = self.request.query_params.get('link', None)
        if link is not None:
            link_clean = link.strip()
            links = [link_clean]
            if link_clean.startswith('http://'):
                links.append('https://' + link_clean[7:])
            elif link_clean.startswith('https://'):
                links.append('http://' + link_clean[8:])

            slash_variants = []
            for l in links:
                slash_variants.append(l.rstrip('/'))
                slash_variants.append(l.rstrip('/') + '/')
            queryset = queryset.filter(link__in=list(dict.fromkeys(slash_variants)))
        return queryset

    def perform_create(self, serializer):
        instance = serializer.save()  # Speichert das Objekt
        process_download_infos(instance)      # Führt Ihre benutzerdefinierte Funktion aus

def _clean_concordia_value(value):
    value = "" if value is None else str(value).strip()
    return value or None

def _nomisma_candidates(value):
    clean = _clean_concordia_value(value)
    if not clean:
        return []
    values = [clean]
    if not clean.startswith("http://") and not clean.startswith("https://"):
        values.append(f"http://nomisma.org/id/{clean}")
        values.append(f"https://nomisma.org/id/{clean}")
    return values

def _lookup_by_name_or_nomisma(model, value):
    clean = _clean_concordia_value(value)
    if not clean:
        return None
    candidates = _nomisma_candidates(clean)
    if hasattr(model, "name_nom_id"):
        obj = model.objects.filter(name_nom_id__in=candidates).first()
        if obj:
            return obj
    obj = model.objects.filter(name__iexact=clean).first()
    if obj:
        return obj
    if hasattr(model, "name_nom_id"):
        suffix = clean.rstrip("/").split("/")[-1]
        obj = model.objects.filter(name_nom_id__iendswith=f"/{suffix}").first()
        if obj:
            return obj
    return model.objects.filter(name__icontains=clean).first()

def _lookup_by_id_or_name(model, value, label=None):
    raw_id = None
    raw_label = label
    if isinstance(value, dict):
        raw_id = value.get("id") or value.get("target_id") or value.get("pk")
        raw_label = raw_label or value.get("name") or value.get("label") or value.get("target_label")
    else:
        raw_id = value

    try:
        if raw_id not in (None, ""):
            obj = model.objects.filter(pk=int(raw_id)).first()
            if obj:
                return obj
    except (TypeError, ValueError):
        pass

    return _lookup_by_name_or_nomisma(model, raw_label if raw_label not in (None, "") else value)

def _lookup_ref(value, ref_id=None):
    clean_id = _clean_concordia_value(ref_id)
    if clean_id:
        try:
            obj = Ref.objects.filter(pk=int(clean_id)).first()
            if obj:
                return obj
        except (TypeError, ValueError):
            pass
    clean = _clean_concordia_value(value)
    if not clean:
        return None
    obj = Ref.objects.filter(abk__iexact=clean).first()
    if obj:
        return obj
    return Ref.objects.filter(abk__icontains=clean).first()


def _unique_muenztyp_title(base_title):
    base = _clean_concordia_value(base_title) or "Kopie"
    candidate = base
    suffix = 2
    while Muenztyp.objects.filter(muenztyptitel=candidate).exists():
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def _payload_clean_value(payload, *keys, allow_blank=False):
    for key in keys:
        if key in payload:
            value = "" if payload.get(key) is None else str(payload.get(key)).strip()
            if value or allow_blank:
                return value
    return None


def _copy_muenztyp_clone_relations(source, target):
    for relation in Mztyp_Person.objects.filter(Mztyp=source):
        Mztyp_Person.objects.get_or_create(
            Mztyp=target,
            idfk_Person=relation.idfk_Person,
            idfk_PersonFunktion=relation.idfk_PersonFunktion,
            appears_on_rev=relation.appears_on_rev,
        )
    for relation in Mztyp_Schlagwort.objects.filter(mztyp=source):
        Mztyp_Schlagwort.objects.get_or_create(
            mztyp=target,
            schlagwort=relation.schlagwort,
        )
    for relation in Typ_Ref.objects.filter(Typ=source):
        Typ_Ref.objects.get_or_create(
            Typ=target,
            Ref=relation.Ref,
            nummer=relation.nummer,
        )


def _duplicate_konkordanz_targets(payload, default_type_id):
    raw_value = (
        payload.get("Konkordanz")
        or payload.get("konkordanz")
        or payload.get("konkordanz_id")
        or default_type_id
    )
    raw_values = raw_value if isinstance(raw_value, list) else [raw_value]
    target_ids = []
    seen_ids = set()

    for raw in raw_values:
        parts = [part.strip() for part in str(raw or "").replace(";", ",").split(",")]
        for part in parts:
            if not part:
                continue
            target = None
            try:
                target = Muenztyp.objects.filter(pk=int(part)).only("id").first()
            except (TypeError, ValueError):
                target = None
            if target is None:
                target = Muenztyp.objects.filter(
                    Q(muenztyptitel__iexact=part) | Q(titel__iexact=part)
                ).only("id").first()
            target_id = getattr(target, "pk", None)
            if target_id and target_id != default_type_id and target_id not in seen_ids:
                seen_ids.add(target_id)
                target_ids.append(target_id)

    if default_type_id not in seen_ids:
        target_ids.insert(0, default_type_id)
    return target_ids


class MuenztypDuplicateView(APIView):
    required_write_permissions = ['slg.add_muenztyp']
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def post(self, request, type_id):
        source = Muenztyp.objects.filter(pk=type_id).first()
        if not source:
            return Response({"ok": False, "error": "Muenztyp nicht gefunden"}, status=404)

        payload = _request_object(request)
        ref_requested = any(key in payload for key in ("Ref", "RefId"))
        ref_obj = _lookup_ref(payload.get("Ref"), payload.get("RefId")) if ref_requested else source.Ref
        if ref_requested and not ref_obj:
            return Response({"ok": False, "error": "Referenz konnte nicht gefunden werden"}, status=400)

        title = _payload_clean_value(payload, "muenztyptitel", "prefLabel", "title")
        nummer = _payload_clean_value(payload, "nummer")
        link = _payload_clean_value(payload, "link", "subject_base", allow_blank=True)

        data = {}
        for field in Muenztyp._meta.concrete_fields:
            if field.primary_key or getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
                continue
            data[field.attname] = getattr(source, field.attname)

        data["muenztyptitel"] = _unique_muenztyp_title(title or f"{source.muenztyptitel} Kopie")
        data["Ref_id"] = ref_obj.pk if ref_obj else None
        if nummer is not None:
            data["nummer"] = nummer
        if link is not None:
            data["link"] = link

        try:
            with transaction.atomic():
                duplicate = Muenztyp.objects.create(**data)
                _copy_muenztyp_clone_relations(source, duplicate)
                target_ids = _duplicate_konkordanz_targets(payload, source.pk)
                konkordanzen = Muenztyp.objects.filter(pk__in=target_ids).exclude(pk=duplicate.pk)
                duplicate.Konkordanz.add(*konkordanzen)
        except IntegrityError:
            return Response({"ok": False, "error": "Münztyp mit diesem Titel existiert bereits"}, status=409)

        return Response({
            "ok": True,
            "source_type_id": source.pk,
            "created_type_id": duplicate.pk,
            "type": MuenztypFilterSerializer([duplicate], many=True).data[0],
        }, status=201)


def _safe_int(value):
    clean = _clean_concordia_value(value)
    if clean is None:
        return None
    try:
        return int(clean)
    except (TypeError, ValueError):
        return None

def _add_concordia_person(muenztyp, raw_value, funktion_id, appears_on_rev, unresolved):
    clean = _clean_concordia_value(raw_value)
    if not clean:
        return
    values = [part.strip() for part in re.split(r"[,;]", clean) if part.strip()]
    for value in values:
        person = _lookup_by_name_or_nomisma(Person, value)
        if not person:
            unresolved.append({"field": "person", "value": value})
            continue
        funktion = PersonFunktion.objects.filter(pk=funktion_id).first()
        if not funktion:
            unresolved.append({"field": "person_function", "value": funktion_id})
            continue
        Mztyp_Person.objects.get_or_create(
            Mztyp=muenztyp,
            idfk_Person=person,
            idfk_PersonFunktion=funktion,
            appears_on_rev=appears_on_rev,
        )

class ConcordiaMuenztypCreateView(APIView):
    required_write_permissions = ['slg.add_muenztyp']
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def post(self, request):
        payload = _request_object(request)
        unresolved = []
        muenztyptitel = _clean_concordia_value(payload.get("muenztyptitel") or payload.get("prefLabel"))
        if not muenztyptitel:
            return Response({"ok": False, "error": "muenztyptitel or prefLabel is required"}, status=400)

        with transaction.atomic():
            obj = Muenztyp(
                muenztyptitel=muenztyptitel,
                titel=_clean_concordia_value(payload.get("titel") or payload.get("generated_title")),
                link=_clean_concordia_value(payload.get("link") or payload.get("subject_base")),
                dat_von=_safe_int(payload.get("dat_von") or payload.get("hasStartDate")),
                dat_bis=_safe_int(payload.get("dat_bis") or payload.get("hasEndDate")),
                avleg=_clean_concordia_value(payload.get("avleg") or payload.get("legend_obv")),
                rvleg=_clean_concordia_value(payload.get("rvleg") or payload.get("legend_rev")),
                avbeschr=_clean_concordia_value(payload.get("avbeschr") or payload.get("desc_obv")),
                rvbeschr=_clean_concordia_value(payload.get("rvbeschr") or payload.get("desc_rev")),
                nummer=_clean_concordia_value(payload.get("nummer")),
            )

            obj.Nominal = _lookup_by_name_or_nomisma(Nominal, payload.get("Nominal") or payload.get("hasDenomination"))
            obj.Mzstaette = _lookup_by_name_or_nomisma(Mzstaette, payload.get("Mzstaette") or payload.get("hasMint"))
            obj.Muenzstand = _lookup_by_name_or_nomisma(Muenzstand, payload.get("Muenzstand") or payload.get("hasMuenzstand") or "Antike Herrscherprägung")
            obj.Ref = _lookup_ref(payload.get("Ref"), payload.get("RefId"))
            obj.av_bildtyp = _lookup_by_id_or_name(AvBildtyp, payload.get("av_bildtyp"), payload.get("av_bildtyp_label"))
            obj.rv_bildtyp = _lookup_by_id_or_name(RvBildtyp, payload.get("rv_bildtyp"), payload.get("rv_bildtyp_label"))
            obj.rv_beizeichen = _lookup_by_name_or_nomisma(RvBeizeichen, payload.get("rv_beizeichen") or payload.get("rv_beizeichen_suggestion") or payload.get("mintMark"))
            if "OffizinSymbol" in globals():
                obj.rv_offizin_symbol = _lookup_by_name_or_nomisma(OffizinSymbol, payload.get("rv_offizin_symbol") or payload.get("rv_offizin_symbol_suggestion") or payload.get("officinaMark"))

            for field_name, raw_value, resolved in [
                ("hasDenomination", payload.get("hasDenomination"), obj.Nominal),
                ("hasMint", payload.get("hasMint"), obj.Mzstaette),
                ("hasMuenzstand", payload.get("hasMuenzstand"), obj.Muenzstand),
                ("Ref", payload.get("Ref"), obj.Ref),
                ("av_bildtyp", payload.get("av_bildtyp") or payload.get("av_bildtyp_label") or payload.get("desc_obv"), obj.av_bildtyp),
                ("rv_bildtyp", payload.get("rv_bildtyp") or payload.get("rv_bildtyp_label") or payload.get("desc_rev"), obj.rv_bildtyp),
                ("rv_beizeichen", payload.get("rv_beizeichen_suggestion") or payload.get("mintMark"), obj.rv_beizeichen),
                ("rv_offizin_symbol", payload.get("rv_offizin_symbol_suggestion") or payload.get("officinaMark"), getattr(obj, "rv_offizin_symbol", None)),
            ]:
                if _clean_concordia_value(raw_value) and not resolved:
                    unresolved.append({"field": field_name, "value": raw_value})

            try:
                obj.save()
            except IntegrityError:
                return Response({"ok": False, "error": "Münztyp mit diesem Titel existiert bereits"}, status=409)
            _add_concordia_person(obj, payload.get("hasAuthority"), 1, False, unresolved)
            _add_concordia_person(obj, payload.get("hasIssuer"), 1, False, unresolved)
            _add_concordia_person(obj, payload.get("dargestellt_av_eligius") or payload.get("dargestellt_av"), 2, False, unresolved)
            _add_concordia_person(obj, payload.get("dargestellt_rv"), 2, True, unresolved)

        return Response({
            "ok": True,
            "created_type_id": obj.id,
            "type": MuenztypFilterSerializer([obj], many=True).data[0],
            "unresolved": unresolved,
        }, status=201)

class MuenztypFilterView(APIView):
    """Return Muenztypen in Concordia type_filter format with rich filtering."""
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    MAX_LIMIT = 5000

    def get(self, request):
        qs = Muenztyp.objects.select_related(
            'Nominal', 'Mzstaette', 'av_bildtyp', 'rv_bildtyp', 'Ref',
            'rv_beizeichen', 'rv_offizin_symbol',
        )

        # --- text search across title, citation and represented person ---
        q = (request.query_params.get('q') or '').strip()
        if q:
            for word in q.split():
                word = word.strip()
                if word:
                    qs = qs.filter(
                        Q(muenztyptitel__icontains=word)
                        | Q(titel__icontains=word)
                        | Q(Ref__abk__icontains=word)
                        | Q(Ref__zitat__icontains=word)
                        | Q(nummer__icontains=word)
                        | Q(mztyp_person__idfk_Person__name__icontains=word)
                    ).distinct()

        # --- legend filters ---
        for param, field in [('legend_obv', 'avleg'), ('legend_rev', 'rvleg')]:
            raw = (request.query_params.get(param) or '').strip()
            if raw:
                for term in [t.strip() for t in raw.split(',') if t.strip()]:
                    pattern = self._wildcard_to_lookup(term)
                    qs = qs.filter(**{f'{field}__{pattern[0]}': pattern[1]})

        # --- description filters ---
        for param, field in [('desc_obv', 'avbeschr'), ('desc_rev', 'rvbeschr')]:
            raw = (request.query_params.get(param) or '').strip()
            if raw:
                for term in [t.strip() for t in raw.split(',') if t.strip()]:
                    qs = qs.filter(**{f'{field}__icontains': term})

        # --- dargestellt_search (person name via Mztyp_Person) ---
        dargestellt_search = (request.query_params.get('dargestellt_search') or '').strip()
        if dargestellt_search:
            qs = qs.filter(
                mztyp_person__idfk_Person__name__icontains=dargestellt_search,
            ).distinct()

        # --- denomination (Nominal.name) ---
        denominations = request.query_params.getlist('denomination')
        denominations = [d.strip() for d in denominations if d.strip()]
        if denominations:
            qs = qs.filter(Nominal__name__in=denominations)

        # --- mintMark (rv_beizeichen.name; der Serializer liefert rv_*) ---
        mint_marks = request.query_params.getlist('mintMark')
        mint_marks = [m.strip() for m in mint_marks if m.strip()]
        if mint_marks:
            qs = qs.filter(rv_beizeichen__name__in=mint_marks)

        # --- mintMark_search (text search) ---
        mintmark_search = (request.query_params.get('mintMark_search') or '').strip()
        if mintmark_search:
            qs = qs.filter(rv_beizeichen__name__iregex=self._wildcard_mintmark_regex(mintmark_search))

        # --- officinaMark (rv_offizin_symbol.name) ---
        officina_marks = request.query_params.getlist('officinaMark')
        officina_marks = [o.strip() for o in officina_marks if o.strip()]
        if officina_marks:
            qs = qs.filter(rv_offizin_symbol__name__in=officina_marks)

        # --- dargestellt pills (exact person name) ---
        dargestellt_values = request.query_params.getlist('dargestellt')
        dargestellt_values = [d.strip() for d in dargestellt_values if d.strip()]
        if dargestellt_values:
            qs = qs.filter(
                mztyp_person__idfk_Person__name__in=dargestellt_values,
            ).distinct()

        # --- description delta filters ---
        for param, field in [('obv_desc_delta', 'avbeschr'), ('rev_desc_delta', 'rvbeschr')]:
            for delta in request.query_params.getlist(param):
                delta = (delta or '').strip().lower()
                if len(delta) < 2:
                    continue
                sign, word = delta[0], delta[1:]
                if not word:
                    continue
                if sign == '+':
                    qs = qs.filter(**{f'{field}__icontains': word})
                elif sign == '-':
                    qs = qs.exclude(**{f'{field}__icontains': word})

        # --- stats ---
        stats = qs.aggregate(
            total=Count('id'),
            range_start=Min('dat_von'),
            range_end=Max('dat_bis'),
        )
        total = stats['total'] or 0

        # --- limit ---
        try:
            limit = int(request.query_params.get('limit', self.MAX_LIMIT))
        except (TypeError, ValueError):
            limit = self.MAX_LIMIT
        limit = max(1, min(limit, self.MAX_LIMIT))

        type_ids = list(qs.order_by('muenztyptitel').values_list('id', flat=True)[:limit])
        types_qs = Muenztyp.objects.filter(id__in=type_ids).select_related(
            'Nominal', 'Mzstaette', 'av_bildtyp', 'rv_bildtyp', 'Ref',
            'rv_beizeichen', 'rv_offizin_symbol',
        ).order_by('muenztyptitel')

        # Prefetch person names for dargestellt_av_eligius
        person_map = {}
        mztp_rows = Mztyp_Person.objects.filter(
            Mztyp_id__in=type_ids,
        ).select_related('idfk_Person').values_list('Mztyp_id', 'idfk_Person__name')
        for mztyp_id, pname in mztp_rows:
            person_map.setdefault(mztyp_id, []).append(pname)

        results = []
        for obj in types_qs:
            obj._dargestellt_names = ', '.join(person_map.get(obj.id, []))
            results.append(obj)

        serializer = MuenztypFilterSerializer(results, many=True)
        return Response({
            'ok': True,
            'total': total,
            'returned': len(serializer.data),
            'limit': limit,
            'range_start': stats.get('range_start'),
            'range_end': stats.get('range_end'),
            'types': serializer.data,
        })

    @staticmethod
    def _wildcard_to_lookup(raw_term):
        """Convert Concordia wildcard syntax (^, €, ?) to Django ORM lookup."""
        starts_with = raw_term.startswith('^')
        ends_with = raw_term.endswith('€') and len(raw_term) > 1
        core = raw_term
        if starts_with:
            core = core[1:]
        if ends_with:
            core = core[:-1]

        if '?' in core:
            # Django escaped '_' in (i)contains/startswith → '?' als echtes
            # Einzelzeichen-Wildcard über einen Regex abbilden.
            pattern = ''.join('.' if ch == '?' else re.escape(ch) for ch in core)
            if starts_with:
                pattern = f'^{pattern}'
            if ends_with:
                pattern = f'{pattern}$'
            return ('iregex', pattern)

        if starts_with and ends_with:
            return ('iexact', core)
        if starts_with:
            return ('istartswith', core)
        if ends_with:
            return ('iendswith', core)
        return ('icontains', core)

    @staticmethod
    def _wildcard_mintmark_regex(raw_term):
        """Convert mintMark wildcard syntax so ? matches one char or a [symbol]."""
        starts_with = raw_term.startswith('^')
        ends_with = raw_term.endswith('€') and len(raw_term) > 1
        core = raw_term
        if starts_with:
            core = core[1:]
        if ends_with:
            core = core[:-1]

        parts = []
        for char in core:
            if char == '?':
                parts.append(r'(\[[^]]+\]|.)')
            else:
                parts.append(re.escape(char))

        pattern = ''.join(parts)
        if starts_with:
            pattern = f'^{pattern}'
        if ends_with:
            pattern = f'{pattern}$'
        return pattern
