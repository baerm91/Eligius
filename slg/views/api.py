"""REST endpoints for objects, vocabulary, statistics and events."""

import hashlib
import logging
import re
import shlex

from django.core.cache import cache
from django.db import transaction
from django.db.models import Max, Min, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from rest_framework import generics, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import QueryParamTokenAuthentication
from ..filters import is_int_qparam
from ..helpers import get_matrix_from_muenztypen, get_timeline_data
from ..models import (
    AvBeizeichen,
    AvBildtyp,
    AvBildtyp_Schlagwort,
    AvOffizin,
    Herstellungsmerkmale,
    Muenzstand,
    Muenztyp,
    Mzstaette,
    Nominal,
    Obj,
    Obj_Person,
    Person,
    PersonFunktion,
    Ref,
    RvBeizeichen,
    RvBildtyp,
    RvOffizin,
    Sek_Merkmale,
    Slg,
    SlgTeil,
    Workflow,
)
from ..permissions import AuthenticatedReadStaffModelWrite, PublicReadStaffModelWrite
from ..serializers import (
    AvBeizeichenSerializer,
    AvBildtypSerializer,
    AvOffizinSerializer,
    AvSchlagwortSerializer,
    HerstellungsmerkmaleSerializer,
    MuenzstandSerializer,
    MzstaettenSerializer,
    NominalSerializer,
    ObjDetailSerializer,
    ObjDetailUpdateSerializer,
    ObjInventorySerializer,
    PersonCoinImageSerializer,
    PersonSerializer,
    RefSerializer,
    RvBeizeichenSerializer,
    RvBildtypSerializer,
    RvOffizinSerializer,
    Sek_MerkmaleSerializer,
    SlgSerializer,
    SlgTeilSerializer,
    WorkflowSerializer,
)
from .utils import _request_object

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])  # Diese Zeile hinzufügen
def get_adjacent_invnrs(request):
    """Nachbarn einer Inventarnummer (±2) innerhalb einer Sammlung.

    Früher wurden alle Obj-Instanzen der Sammlung in den RAM geladen; jetzt
    holen je zwei sortierte, begrenzte Abfragen nur die benötigten Nachbarn.
    """
    current_invnr = request.GET.get('invnr')
    slg_id = request.GET.get('slg_id')
    slgteil_id = request.GET.get('slgteil_id')

    if not current_invnr or not slg_id:
        return Response({'error': 'Inventarnummer und Sammlungs-ID sind erforderlich'}, status=400)
    if not is_int_qparam(slg_id) or (slgteil_id and not is_int_qparam(slgteil_id)):
        return Response({'error': 'Sammlungs-ID und Sammlungsteil-ID müssen ganze Zahlen sein.'}, status=400)

    filter_kwargs = {'Slg_id': int(slg_id)}
    if slgteil_id and int(slgteil_id):
        filter_kwargs['SlgTeil_id'] = int(slgteil_id)
    objects = Obj.objects.filter(**filter_kwargs)

    current_id = (objects.filter(invnr=current_invnr).order_by('pk')
                  .values_list('id', flat=True).first())
    if current_id is None:
        return Response({'error': f"Inventarnummer '{current_invnr}' nicht gefunden in der gefilterten Liste."},
                        status=404)

    previous = list(objects.filter(invnr__lt=current_invnr).order_by('-invnr', '-pk')
                    .values_list('invnr', 'id')[:2])
    following = list(objects.filter(invnr__gt=current_invnr).order_by('invnr', 'pk')
                     .values_list('invnr', 'id')[:2])

    def neighbour(rows, index):
        return rows[index] if len(rows) > index else (None, None)

    prev1, prev1_id = neighbour(previous, 0)
    prev2, prev2_id = neighbour(previous, 1)
    next1, next1_id = neighbour(following, 0)
    next2, next2_id = neighbour(following, 1)
    return Response({
        'prev2': prev2, 'prev2_id': prev2_id,
        'prev1': prev1, 'prev1_id': prev1_id,
        'current': current_invnr, 'current_id': current_id,
        'next1': next1, 'next1_id': next1_id,
        'next2': next2, 'next2_id': next2_id,
    })

class SlgTeilListAPIView(generics.ListAPIView):
    serializer_class = SlgTeilSerializer

    def get_queryset(self):
        slg_id = self.kwargs.get('slg_id')
        return SlgTeil.objects.filter(
            Q(obj__Slg__id=slg_id) |
            Q(idfk_Slg_SlgTeil__id=slg_id)
        ).distinct()

# Query-Parameter, die nur der Authentifizierung/Steuerung dienen und nie als
# Filter an das ORM weitergereicht werden dürfen.


@api_view(['GET'])
@permission_classes([AllowAny])  # Diese Zeile hinzufügen
def statistics_api(request):
    """API-Endpoint für Sammlungsstatistiken."""
    anzahl_qs = Obj.objects.count()
    max_min_datierung = Muenztyp.objects.aggregate(Max('dat_von'), Min('dat_von'))
    max_min_gewicht = Obj.objects.aggregate(
        Max('gewicht'), Min('gewicht'),
        Max('durchmesser'), Min('durchmesser')
    )
    anzahl_mt = Muenztyp.objects.count()
    anzahl_person = Person.objects.count()
    anzahl_mstaetten = Mzstaette.objects.count()
    anzahl_kontrolliert = Obj.objects.filter(workflow__name="kontrolliert").count()
    anzahl_zurkontrolle = Obj.objects.filter(workflow__name="Bereit zur Kontrolle").count()

    return Response({
        'anzahl_qs': anzahl_qs,
        'anzahl_mt': anzahl_mt,
        'anzahl_person': anzahl_person,
        'anzahl_mstaetten': anzahl_mstaetten,
        'max_min_datierung': max_min_datierung,
        'max_min_gewicht': max_min_gewicht,
        'anzahl_kontrolliert': anzahl_kontrolliert,
        'anzahl_zurkontrolle': anzahl_zurkontrolle,
    })

@api_view(['GET'])
@permission_classes([AllowAny])  # Diese Zeile hinzufügen
def sammlungen_api(request):
    """API-Endpoint für alle Sammlungen."""
    try:
        # Debug: Prüfe Anzahl der Sammlungen
        sammlungen_count = Slg.objects.count()
        logger.info(f"Gefundene Sammlungen: {sammlungen_count}")

        if sammlungen_count == 0:
            # Wenn keine Sammlungen vorhanden sind, geben wir ein Test-Objekt zurück
            logger.warning("Keine Sammlungen in der Datenbank!")
            return Response([{
                "id": 1,
                "name": "Test-Sammlung",
                "beschreibung": "Dies ist ein Test",
                "cover": "",
                "kategorie": {"id": 1, "name": "Test-Kategorie"}
            }])

        sammlungen = Slg.objects.all().select_related('kategorie')
        serializer = SlgSerializer(sammlungen, many=True)
        logger.info(f"Serialisierte Sammlungen: {len(serializer.data)}")
        return Response(serializer.data)

    except Exception:
        logger.exception('Fehler in sammlungen_api')
        return Response({"error": "Fehler beim Laden der Sammlungen."}, status=500)


class _AvSchlagwortPagination(PageNumberPagination):
    page_size = 200
    max_page_size = 1000
    page_size_query_param = 'page_size'


class AvSchlagwortList(generics.ListAPIView):
    serializer_class = AvSchlagwortSerializer
    queryset = AvBildtyp_Schlagwort.objects.select_related('schlagwort').order_by('pk')
    pagination_class = _AvSchlagwortPagination

class AvBildtypSchlagwortList(generics.ListAPIView):
    serializer_class = AvBildtypSerializer

    def get_queryset(self):
        queryset = AvBildtyp.objects.all()
        bildtyp_query = self.request.query_params.get('bildtyp', None)
        schlagwort_query = self.request.query_params.get('schlagwort', None)

        if bildtyp_query:
            queryset = queryset.filter(
                Q(name__icontains=bildtyp_query) | Q(abk__icontains=bildtyp_query)
            )

        if schlagwort_query:
            queryset = queryset.filter(schlagworte__name__icontains=schlagwort_query)

        return queryset.distinct()


class MzstaettenRView(viewsets.ModelViewSet):
# class MzstaettenRView(generics.RetrieveUpdateDestroyAPIView):

    queryset         = Mzstaette.objects.all()
    serializer_class = MzstaettenSerializer
    permission_classes = [PublicReadStaffModelWrite]

   #  def get_queryset(self):
   #      return Mzstaette.objects.all()

    # def get_object(self):
    #     id = self.kwargs.get("id")
    #     return Mzstaette.objects.get(id=id)


class ObjektList(generics.ListAPIView):
    serializer_class = ObjInventorySerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = Obj.objects.select_related('Typ', 'Typ__workflow', 'workflow', 'rv_offizin')
        invnr = self.request.query_params.get('invnr')
        if invnr:
            queryset = queryset.filter(invnr__iexact=invnr)
        return queryset


@api_view(['POST'])
@authentication_classes([QueryParamTokenAuthentication, SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def objekte_bulk_api(request):
    payload = _request_object(request)
    raw_invnrs = payload.get('invnrs') or payload.get('objects') or []
    if not isinstance(raw_invnrs, list):
        return Response({'error': "'invnrs' must be a list"}, status=400)

    cleaned_invnrs = []
    seen = set()
    for value in raw_invnrs:
        if isinstance(value, dict):
            text = str(value.get('invnr') or value.get('inv') or '').strip()
        else:
            text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned_invnrs.append(text)

    if not cleaned_invnrs:
        return Response({'error': "'invnrs' list is empty"}, status=400)
    if len(cleaned_invnrs) > 5000:
        return Response({'error': 'Too many objects requested (max 5000)'}, status=400)

    queryset = Obj.objects.filter(invnr__in=cleaned_invnrs).select_related(
        'Typ',
        'Typ__workflow',
        'workflow',
        'rv_offizin',
    )
    serialized = ObjInventorySerializer(queryset, many=True).data
    objects = {}
    matched_invnrs = set()
    for obj in serialized:
        invnr = str(obj.get('invnr') or '').strip()
        if invnr and invnr not in objects:
            objects[invnr] = obj
            matched_invnrs.add(invnr)

    return Response({
        'ok': True,
        'requested': len(cleaned_invnrs),
        'matched': len(objects),
        'objects': objects,
        'unmatched_invnrs': [invnr for invnr in cleaned_invnrs if invnr not in matched_invnrs],
    })


class ObjektDetail(generics.RetrieveUpdateAPIView):
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'invnr'
    lookup_url_kwarg = 'invnr'

    def get_object(self):
        """invnr ist nur je Sammlung(-steil) eindeutig.

        Optional mit ?slg=<id>&slgteil=<id> eingrenzen; bleibt die Nummer
        mehrdeutig, antwortet die API mit 409 und den Kandidaten statt mit
        einem MultipleObjectsReturned (HTTP 500).
        """
        from rest_framework.exceptions import APIException, NotFound, ValidationError as DRFValidationError
        queryset = self.filter_queryset(self.get_queryset()).filter(invnr=self.kwargs[self.lookup_url_kwarg])
        for param, field in (('slg', 'Slg_id'), ('slgteil', 'SlgTeil_id')):
            value = self.request.query_params.get(param)
            if value not in (None, ''):
                if not is_int_qparam(value):
                    raise DRFValidationError({param: 'Ganzzahlige ID erwartet.'})
                queryset = queryset.filter(**{field: int(value)})
        matches = list(queryset.order_by('pk')[:21])
        if not matches:
            raise NotFound()
        if len(matches) > 1:
            conflict = APIException({
                'detail': 'Inventarnummer ist mehrdeutig. Mit ?slg=<id> (und ggf. &slgteil=<id>) eingrenzen.',
                'kandidaten': [{'id': o.pk, 'slg': o.Slg_id, 'slgteil': o.SlgTeil_id} for o in matches[:20]],
            })
            conflict.status_code = 409
            raise conflict
        obj = matches[0]
        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        return Obj.objects.select_related(
            'Typ', 'Typ__workflow', 'workflow',
            'idfk_Muenzstand', 'idfk_Nominal', 'idfk_Mzstaette',
            'av_bildtyp', 'av_beizeichen', 'av_offizin',
            'rv_bildtyp', 'rv_beizeichen', 'rv_offizin'
        )

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return ObjDetailUpdateSerializer
        return ObjDetailSerializer

    def update(self, request, *args, **kwargs):
        # Bei PATCH immer partial=True, damit nur gesendete Felder aktualisiert werden
        partial = kwargs.pop('partial', False) or request.method == 'PATCH'
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        read_serializer = ObjDetailSerializer(instance, context=self.get_serializer_context())
        return Response(read_serializer.data)

class ObjektPersonenView(generics.GenericAPIView):
    required_write_permissions = ['slg.change_obj']
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'invnr'
    lookup_url_kwarg = 'invnr'

    role_function_ids = {
        'issuer': 1,
        'depicted_av': 2,
        'depicted_rv': 2,
    }

    queryset = Obj.objects.all()
    # Gleiche Auflösung wie ObjektDetail: ?slg=/&slgteil= zum Eingrenzen, 409 bei
    # Mehrdeutigkeit statt MultipleObjectsReturned (HTTP 500).
    get_object = ObjektDetail.get_object

    def _serialize_relations(self, obj):
        relations = Obj_Person.objects.filter(idfk_Obj=obj).select_related(
            'idfk_Person',
            'idfk_PersonFunktion',
        ).order_by('idfk_Person__name', 'idfk_PersonFunktion_id', 'appears_on_rev')

        result = []
        for rel in relations:
            result.append({
                'id': rel.id,
                'person': {
                    'id': rel.idfk_Person_id,
                    'name': rel.idfk_Person.name,
                    'name_nom_id': rel.idfk_Person.name_nom_id,
                },
                'funktion': {
                    'id': rel.idfk_PersonFunktion_id,
                    'name': rel.idfk_PersonFunktion.name,
                },
                'appears_on_rev': rel.appears_on_rev,
            })
        return result

    def get(self, request, *args, **kwargs):
        obj = self.get_object()
        return Response({'object': {'id': obj.id, 'invnr': obj.invnr}, 'personen': self._serialize_relations(obj)})

    def put(self, request, *args, **kwargs):
        obj = self.get_object()
        raw_entries = request.data.get('personen') if isinstance(request.data, dict) else request.data
        if not isinstance(raw_entries, list):
            return Response({'detail': 'Expected "personen" as list.'}, status=400)

        person_ids = []
        entries = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                return Response({'detail': 'Each person entry must be an object.'}, status=400)
            person_id = raw.get('person_id') or raw.get('id')
            if isinstance(raw.get('person'), dict):
                person_id = person_id or raw['person'].get('id')
            try:
                person_id = int(person_id)
            except (TypeError, ValueError):
                return Response({'detail': 'Each person entry needs a valid person_id.'}, status=400)
            roles = raw.get('roles') or {}
            if not isinstance(roles, dict):
                return Response({'detail': 'roles must be an object.'}, status=400)
            entries.append((person_id, roles))
            person_ids.append(person_id)

        existing_person_ids = set(Person.objects.filter(id__in=person_ids).values_list('id', flat=True))
        missing_person_ids = sorted(set(person_ids) - existing_person_ids)
        if missing_person_ids:
            return Response({'detail': 'Unknown person ids.', 'person_ids': missing_person_ids}, status=400)

        function_ids = set(self.role_function_ids.values())
        existing_function_ids = set(PersonFunktion.objects.filter(id__in=function_ids).values_list('id', flat=True))
        if function_ids != existing_function_ids:
            return Response({'detail': 'Required person functions are missing.', 'function_ids': sorted(function_ids - existing_function_ids)}, status=500)
        managed_function_ids = set(PersonFunktion.objects.filter(id__in=[1, 2, 6, 7]).values_list('id', flat=True))

        with transaction.atomic():
            if person_ids:
                Obj_Person.objects.filter(
                    idfk_Obj=obj,
                    idfk_Person_id__in=person_ids,
                    idfk_PersonFunktion_id__in=managed_function_ids,
                ).delete()

            for person_id, roles in entries:
                if roles.get('issuer'):
                    Obj_Person.objects.get_or_create(
                        idfk_Obj=obj,
                        idfk_Person_id=person_id,
                        idfk_PersonFunktion_id=self.role_function_ids['issuer'],
                        appears_on_rev=False,
                    )
                if roles.get('depicted_av'):
                    Obj_Person.objects.get_or_create(
                        idfk_Obj=obj,
                        idfk_Person_id=person_id,
                        idfk_PersonFunktion_id=self.role_function_ids['depicted_av'],
                        appears_on_rev=False,
                    )
                if roles.get('depicted_rv'):
                    Obj_Person.objects.get_or_create(
                        idfk_Obj=obj,
                        idfk_Person_id=person_id,
                        idfk_PersonFunktion_id=self.role_function_ids['depicted_rv'],
                        appears_on_rev=True,
                    )

        return Response({'object': {'id': obj.id, 'invnr': obj.invnr}, 'personen': self._serialize_relations(obj)})

class RefList(generics.ListCreateAPIView):
    serializer_class = RefSerializer

    def get_queryset(self):
        queryset = Ref.objects.all()
        abk = self.request.query_params.get('abk', None)
        if abk is not None:
            queryset = queryset.filter(abk=abk)
        return queryset

class AvBildtypList(generics.ListCreateAPIView):
    serializer_class = AvBildtypSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = AvBildtyp.objects.all()
        query = self.request.query_params.get('query', None)
        schlagwort = self.request.query_params.get('schlagwort', None)

        if query is not None:
            # Mehrere Suchbegriffe erlauben - Anführungszeichen respektieren
            # "geht n. l." bleibt zusammen, normale Wörter werden getrennt
            try:
                # shlex.split respektiert Anführungszeichen
                tokens = shlex.split(query.strip())
            except ValueError:
                # Falls shlex fehlschlägt, auf einfaches Splitting zurückfallen
                tokens = [t for t in re.split(r"[\s,]+", query.strip()) if t]

            for token in tokens:
                queryset = queryset.filter(
                    Q(name__icontains=token) |
                    Q(abk__icontains=token) |
                    Q(schlagworte__name__icontains=token)
                )

        if schlagwort is not None:
            queryset = queryset.filter(schlagworte__name__icontains=schlagwort)

        return queryset.distinct()

class AvBildtypDetail(generics.RetrieveUpdateAPIView):
    serializer_class = AvBildtypSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = AvBildtyp.objects.all()

class RvBildtypList(generics.ListCreateAPIView):
    serializer_class = RvBildtypSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = RvBildtyp.objects.all()
        query = self.request.query_params.get('query', None)

        if query is not None:
            # Zuerst exakte Übereinstimmung prüfen (ganzer String)
            exact_match_queryset = queryset.filter(
                Q(name__iexact=query) | Q(abk__iexact=query)
            )
            if exact_match_queryset.exists():
                return exact_match_queryset

            # Mehrere Suchbegriffe erlauben - Anführungszeichen respektieren
            # "geht n. l." bleibt zusammen, normale Wörter werden getrennt
            try:
                # shlex.split respektiert Anführungszeichen
                tokens = shlex.split(query.strip())
            except ValueError:
                # Falls shlex fehlschlägt, auf einfaches Splitting zurückfallen
                tokens = [t for t in re.split(r"[\s,]+", query.strip()) if t]

            for token in tokens:
                queryset = queryset.filter(
                    Q(name__icontains=token) |
                    Q(abk__icontains=token) |
                    Q(schlagworte__name__icontains=token)
                )

        return queryset.distinct()

class RvBildtypDetail(generics.RetrieveUpdateAPIView):
    serializer_class = RvBildtypSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = RvBildtyp.objects.all()

class MzstaetteList(generics.ListCreateAPIView):
    serializer_class = MzstaettenSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [PublicReadStaffModelWrite]

    def get_queryset(self):
        queryset = Mzstaette.objects.all()
        query = self.request.query_params.get('query', None)
        name_nom_id = self.request.query_params.get('name_nom_id', None)
        nomisma_id = self.request.query_params.get('nomisma_id', None)

        if query is not None:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(name_nom_id__icontains=query)
            )

        # Suche nach Nomisma ID - bevorzuge exakte Übereinstimmung
        if nomisma_id is not None:
            queryset = queryset.filter(name_nom_id__iexact=nomisma_id)
        elif name_nom_id is not None:
            queryset = queryset.filter(name_nom_id__iexact=name_nom_id)

        return queryset.distinct()

class MzstaetteDetail(generics.RetrieveUpdateAPIView):
    serializer_class = MzstaettenSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = Mzstaette.objects.all()

class NominalList(generics.ListCreateAPIView):
    serializer_class = NominalSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [PublicReadStaffModelWrite]

    def get_queryset(self):
        queryset = Nominal.objects.all()
        query = self.request.query_params.get('query', None)
        name_nom_id = self.request.query_params.get('name_nom_id', None)

        if query is not None:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(name_nom_id__icontains=query)
            )

        if name_nom_id is not None:
            queryset = queryset.filter(name_nom_id__iexact=name_nom_id)

        return queryset.distinct()

class NominalDetail(generics.RetrieveUpdateAPIView):
    serializer_class = NominalSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = Nominal.objects.all()

class HerstellungsmerkmaleList(generics.ListCreateAPIView):
    serializer_class = HerstellungsmerkmaleSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        return Herstellungsmerkmale.objects.all()

class Sek_MerkmaleList(generics.ListCreateAPIView):
    serializer_class = Sek_MerkmaleSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        return Sek_Merkmale.objects.all()

class PersonList(generics.ListCreateAPIView):
    serializer_class = PersonSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = Person.objects.all()
        query = self.request.query_params.get('query', None)
        name_nom_id = self.request.query_params.get('name_nom_id', None)

        if query is not None:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(name_nom_id__icontains=query)
            )

        if name_nom_id is not None:
            queryset = queryset.filter(name_nom_id__iexact=name_nom_id)

        return queryset.distinct()

class _PersonCoinImagesPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100
    page_size_query_param = 'page_size'


class PersonCoinImagesView(generics.ListAPIView):
    serializer_class = PersonCoinImageSerializer
    # Früher unpaginiert über ALLE Personen (2N+1 Queries)
    pagination_class = _PersonCoinImagesPagination

    def get_queryset(self):
        name = self.request.query_params.get('name', None)
        # Nur Personen, die als Dargestellte (Funktion 2) auf Münztypen vorkommen
        queryset = Person.objects.filter(mztyp_person__idfk_PersonFunktion=2)
        if name:
            queryset = queryset.filter(name__icontains=name)
        return queryset.distinct().order_by('name', 'pk')

class MuenzstandList(generics.ListCreateAPIView):
    serializer_class = MuenzstandSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = Muenzstand.objects.all()
        query = self.request.query_params.get('query', None)
        if query is not None:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')

class MuenzstandDetail(generics.RetrieveUpdateAPIView):
    serializer_class = MuenzstandSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = Muenzstand.objects.all()

class AvBeizeichenList(generics.ListCreateAPIView):
    serializer_class = AvBeizeichenSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = AvBeizeichen.objects.all()
        query = self.request.query_params.get('query', None)
        if query is not None:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')

class AvBeizeichenDetail(generics.RetrieveUpdateAPIView):
    serializer_class = AvBeizeichenSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = AvBeizeichen.objects.all()

class AvOffizinList(generics.ListCreateAPIView):
    serializer_class = AvOffizinSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = AvOffizin.objects.all()
        query = self.request.query_params.get('query', None)
        if query is not None:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')

class AvOffizinDetail(generics.RetrieveUpdateAPIView):
    serializer_class = AvOffizinSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = AvOffizin.objects.all()

class RvBeizeichenList(generics.ListCreateAPIView):
    serializer_class = RvBeizeichenSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = RvBeizeichen.objects.all()
        query = self.request.query_params.get('query', None)
        if query is not None:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')

class RvBeizeichenDetail(generics.RetrieveUpdateAPIView):
    serializer_class = RvBeizeichenSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = RvBeizeichen.objects.all()

class RvOffizinList(generics.ListCreateAPIView):
    serializer_class = RvOffizinSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = RvOffizin.objects.all()
        query = self.request.query_params.get('query', None)
        if query is not None:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')

class RvOffizinDetail(generics.RetrieveUpdateAPIView):
    serializer_class = RvOffizinSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = RvOffizin.objects.all()

class WorkflowList(generics.ListAPIView):
    serializer_class = WorkflowSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]

    def get_queryset(self):
        queryset = Workflow.objects.all()
        query = self.request.query_params.get('query', None)
        if query is not None:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('reihenfolge')

class WorkflowDetail(generics.RetrieveAPIView):
    serializer_class = WorkflowSerializer
    authentication_classes = [
        QueryParamTokenAuthentication,
        SessionAuthentication,
        TokenAuthentication,
    ]
    permission_classes = [AuthenticatedReadStaffModelWrite]
    lookup_field = 'pk'
    queryset = Workflow.objects.all()

@api_view(['GET'])
@permission_classes([AllowAny])  # Diese Zeile hinzufügen
def collections_api(request):
    qs = Slg.objects.select_related('kategorie').all()
    return Response(SlgSerializer(qs, many=True).data)

@api_view(['GET'])
@permission_classes([AllowAny])  # Diese Zeile hinzufügen
def stats_api(request):
    if request.GET:
        from ..services.public_api import statistics_for_request
        try:
            return Response(statistics_for_request(request))
        except (ValueError, TypeError):
            return Response({'error': 'Ungültige Filterparameter.'}, status=400)
    data = cache.get_or_set(
        'index_stats',
        lambda: {
            "anzahl_qs": Obj.objects.count(),
            "anzahl_mt": Muenztyp.objects.count(),
            "anzahl_person": Person.objects.count(),
            "anzahl_mstaetten": Mzstaette.objects.count(),
            "max_min_gewicht": Obj.objects.aggregate(gewicht__min=Min('gewicht'), gewicht__max=Max('gewicht')),
            "max_min_datierung": Muenztyp.objects.aggregate(dat_von__min=Min('dat_von'), dat_von__max=Max('dat_von')),
        },
        3600
    )
    return Response(data)

class CoinsContextAPI(APIView):
    permission_classes = [AllowAny] # Or IsAuthenticated if you prefer

    def get(self, request, pk):
        # Basic existence check for the main object
        # You might want to add more specific permission checks here
        # or reuse logic from your existing detail view if applicable.
        get_object_or_404(Obj.objects.select_related('Typ'), pk=pk)

        # The 'request' object passed to get_matrix_from_muenztypen
        # will contain URL parameters. Your apply_filters function
        # should be able to use these to filter Muenztyp.
        matrix = get_matrix_from_muenztypen(request, pk)
        return Response(matrix, status=200)

@api_view(['GET'])
@permission_classes([AllowAny])  # Diese Zeile hinzufügen (falls noch nicht vorhanden)
def cycle_coin(request):
    """
    /api/cycle-coin/?type_id=<mztyp>&current_obj_id=<obj>&direction=next|prev
    liefert {next_obj_id, card_html}
    """
    mt_id      = request.GET.get('type_id')
    current_id = request.GET.get('current_obj_id')
    direction  = request.GET.get('direction', 'next')

    if not (mt_id and current_id):
        return Response({"detail": "type_id oder current_obj_id fehlt"}, status=400)
    if not (is_int_qparam(mt_id) and is_int_qparam(current_id)):
        return Response({"detail": "type_id und current_obj_id müssen ganze Zahlen sein"}, status=400)

    objs = list(
        Obj.objects
            .filter(Typ_id=mt_id)
            .only('id', 'Typ')                # schlank
            .order_by('id')
    )

    if not objs:
        return Response({"detail": "Keine Objekte für den angegebenen type_id gefunden."}, status=404)

    ids = [o.id for o in objs]

    try:
        idx = ids.index(int(current_id))
    except ValueError:                        # falls Karte nicht (mehr) in der Liste
        idx = -1

    nxt = (idx + 1) % len(objs) if direction == 'next' else (idx - 1) % len(objs)
    next_obj = objs[nxt]

    html = render_to_string(
        "slg/partials/coin_preview_card.html",
        {"obj": next_obj, "light": True}
    )
    return Response({"next_obj_id": next_obj.id, "card_html": html})

def ereignisse_api(request):
    """
    REST API-Endpunkt für Ereignisse (slginformation).

    Parameter werden über die GET-Parameter übergeben.
    """
    # Jahre müssen ganzzahlig sein (?von=abc war ein ValueError/HTTP 500)
    invalid = [name for name in ('von', 'bis')
               if request.GET.get(name) not in (None, '') and not is_int_qparam(request.GET.get(name))]
    if invalid:
        return JsonResponse({'error': f"Ungültiger Jahreswert für: {', '.join(invalid)}"}, status=400)
    # Cache-Schlüssel nur aus den ausgewerteten Parametern bilden: mit der
    # vollen URL ließe sich der LocMemCache über beliebige Query-Strings fluten.
    params = tuple((name, (request.GET.get(name) or '').strip()[:200])
                   for name in ('von', 'bis', 'sammlung', 'person', 'thema'))
    values = dict(params)
    # Nur endliche, typische Abfragen cachen; Freitext (thema, Personenname)
    # und beliebige Jahreszahlen würden sonst je Anfrage einen Eintrag erzeugen.
    cacheable = (
        not values['thema']
        and (not values['person'] or is_int_qparam(values['person']))
        and (not values['sammlung'] or is_int_qparam(values['sammlung']))
        and all(not values[name] or (is_int_qparam(values[name]) and -1000 <= int(values[name]) <= 3000)
                for name in ('von', 'bis'))
    )
    if not cacheable:
        return JsonResponse(get_timeline_data(request))
    cache_key = 'timeline_api:' + hashlib.sha256(repr(params).encode()).hexdigest()
    data = cache.get(cache_key)
    if data is None:
        data = get_timeline_data(request)
        cache.set(cache_key, data, 300)  # 5 Minuten
    return JsonResponse(data)
