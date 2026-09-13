"""Shared query services for Browse, REST and public MCP.

The MTOA query below is extracted from the existing Browse implementation.
No transport is responsible for implementing its own object search.
"""
from functools import reduce
from operator import and_, or_

from django.db.models import Q, Case, When, Value, IntegerField, Count, F
from slg.models import MuenztypObjektAnzeige, Obj, Paket
from slg.filters import is_valid_qparam
from slg.filter_config import FILTER_PARAMETERS


def public_objects():
    """Existing public-site policy: object freigabe is historically unused.

    Confirmed by the project owner for this MVP. Keep the policy here so a
    future release rule can be applied to every public transport together.
    Internal fields and unpublished packages are never serialized by MCP.
    """
    return Obj.objects.all()

MTOA_FILTERS = {
    'q': {'fields': ['invnr', 'objekttitel', 'rv_legende', 'av_legende', 'typ'], 'lookup': 'icontains'},
    'avleg': {'fields': ['av_legende'], 'lookup': 'icontains'},
    'rvleg': {'fields': ['rv_legende'], 'lookup': 'icontains'},
    'Muenzstaette': {'fields': ['mzstaette'], 'lookup': 'exact'},
    'Muenzstand': {'fields': ['muenzstand'], 'lookup': 'exact'},
    'Reichskreis': {'fields': ['reichskreis'], 'lookup': 'exact'},
    'region': {'fields': ['region'], 'lookup': 'exact'},
    'Nominal': {'fields': ['nominal'], 'lookup': 'exact'},
    'Nominal_id': {'fields': ['nominal_fk_id'], 'lookup': 'in'},
    'material': {'fields': ['metall'], 'lookup': 'icontains'},
    'Slg': {'fields': ['slg_fk_id'], 'lookup': 'exact'},
    'SlgTeil': {'fields': ['slgteil_fk_id'], 'lookup': 'exact'},
    'av_bildtyp': {'fields': ['av_bildtyp_fk_id'], 'lookup': 'exact'},
    'av_beizeichen': {'fields': ['av_beizeichen'], 'lookup': 'exact'},
    'rv_bildtyp': {'fields': ['rv_bildtyp_fk_id'], 'lookup': 'exact'},
    'rv_beizeichen': {'fields': ['rv_beizeichen'], 'lookup': 'exact'},
    'rv_schlagwort': {'fields': ['rv_schlagworte'], 'lookup': 'icontains'},
    'av_schlagwort': {'fields': ['av_schlagworte'], 'lookup': 'icontains'},
    'obj_type': {'fields': ['objekttyp'], 'lookup': 'exact'},
    'objekttyp': {'fields': ['objekttyp_fk_id'], 'lookup': 'exact'},
    'coin_type': {'fields': ['typ_fk_id'], 'lookup': 'in'},
}

MTOA_FACETS = {
    'Muenzstaette': {'field': 'mzstaette', 'id_field': 'mzstaette_fk_id'},
    'Muenzstand': {'field': 'muenzstand', 'id_field': 'muenzstand_fk_id'},
    'Reichskreis': {'field': 'reichskreis'},
    'region': {'field': 'region', 'id_field': 'region_fk_id'},
    'Nominal': {'field': 'nominal', 'id_field': 'nominal_fk_id'},
    'material': {'field': 'metall', 'id_field': 'metall_fk_id'},
    'Slg': {'field': 'Slg', 'id_field': 'slg_fk_id'},
    'SlgTeil': {'field': 'SlgTeil', 'id_field': 'slgteil_fk_id'},
    'av_bildtyp': {'field': 'av_bildtyp', 'id_field': 'av_bildtyp_fk_id'},
    'rv_bildtyp': {'field': 'rv_bildtyp', 'id_field': 'rv_bildtyp_fk_id'},
    'av_beizeichen': {'field': 'av_beizeichen'},
    'rv_beizeichen': {'field': 'rv_beizeichen'},
    'obj_type': {'field': 'objekttyp', 'id_field': 'objekttyp_fk_id'},
    'coin_type': {'field': 'typ', 'id_field': 'typ_fk_id'},
}


def _get_filtered_mtoa_queryset(request, exclude_field=None):
    """
    Zentrale Browse-Filterlogik für MTOA, damit Liste, Chart und andere
    Auswertungen dieselbe Treffermenge verwenden.
    """
    unbestimmt_param = request.GET.get('unbestimmt', '')
    if unbestimmt_param == 'True':
        is_unbestimmt = True
        qs = MuenztypObjektAnzeige.objects.filter(typ_fk__isnull=True)
    elif unbestimmt_param == 'False':
        is_unbestimmt = False
        qs = MuenztypObjektAnzeige.objects.filter(typ_fk__isnull=False)
    else:
        is_unbestimmt = False
        qs = MuenztypObjektAnzeige.objects.all()

    qs = qs.filter(obj_id__in=public_objects().values('pk'))
    general_filters = []
    needs_distinct = False

    for param, config in MTOA_FILTERS.items():
        if param == exclude_field:
            continue
        values = [v for v in request.GET.getlist(param) if is_valid_qparam(v)]
        if not values:
            continue

        if config['lookup'] == 'in':
            general_filters.append(Q(**{f"{config['fields'][0]}__in": values}))
        else:
            per_value = [
                Q(**{f"{field}__{config['lookup']}": val})
                for val in values
                for field in config['fields']
            ]
            general_filters.append(reduce(or_, per_value))

    date_from = request.GET.get('dat_von')
    date_to = request.GET.get('dat_bis')
    if exclude_field not in ('date', 'dat_von', 'dat_bis'):
        if is_valid_qparam(date_to):
            general_filters.append(Q(datierung_von__lte=date_to))
        if is_valid_qparam(date_from):
            general_filters.append(Q(datierung_bis__gte=date_from))

    if general_filters:
        qs = qs.filter(reduce(and_, general_filters))

    # These declared filters were previously silently ignored by MTOA.
    # Resolve through the existing configuration, on the same Browse set.
    for param in ('invnr', 'num'):
        values = [v for v in request.GET.getlist(param) if is_valid_qparam(v)]
        if not values or param == exclude_field:
            continue
        if param == 'invnr':
            qs = qs.filter(reduce(or_, [Q(invnr__icontains=v) for v in values]))
        else:
            ref_q = Q()
            for context, type_condition in (
                ('default', Q(Typ__isnull=False)),
                ('unbestimmt', Q(Typ__isnull=True)),
            ):
                config = FILTER_PARAMETERS[context][param]
                ref_q |= type_condition & Q(**{config['fields'][0] + '__in': values})
            qs = qs.filter(obj_id__in=public_objects().filter(ref_q).values('pk'))

    person_params = {
        'Praegeherren': {'funktion_ids': [1, 6, 7], 'appears_on_rev': None},
        'Dargestellte_AV': {'funktion_ids': [2], 'appears_on_rev': False},
        'Dargestellte_RV': {'funktion_ids': [2], 'appears_on_rev': True},
        'Person': {'exclude_funktion_ids': [1, 2, 6, 7], 'appears_on_rev': None},
    }

    for param_name, config in person_params.items():
        if param_name == exclude_field:
            continue
        if param_name in request.GET:
            names = [name for name in request.GET.getlist(param_name) if is_valid_qparam(name)]
            if names:
                needs_distinct = True
                name_q = Q(mtoaperson__person__name__in=names)

                if config.get('funktion_ids'):
                    name_q &= Q(mtoaperson__funktion_id__in=config['funktion_ids'])
                elif config.get('exclude_funktion_ids'):
                    name_q &= ~Q(mtoaperson__funktion_id__in=config['exclude_funktion_ids'])

                if config.get('appears_on_rev') is not None:
                    name_q &= Q(mtoaperson__appears_on_rev=config['appears_on_rev'])

                qs = qs.filter(name_q)

    wappen_names = [name for name in request.GET.getlist('Wappen') if is_valid_qparam(name)]
    if exclude_field != 'Wappen' and wappen_names:
        needs_distinct = True
        qs = qs.filter(typ_fk__wappen__name__in=wappen_names)

    ref_values = [name for name in request.GET.getlist('Ref') if is_valid_qparam(name)]
    if exclude_field != 'Ref' and ref_values:
        ref_query = Q()
        if unbestimmt_param != 'True':
            ref_query |= Q(Typ__Ref__abk__in=ref_values)
        if unbestimmt_param != 'False':
            ref_query |= Q(idfk_Ref__abk__in=ref_values)

        ref_obj_ids = (
            Obj.objects.filter(ref_query)
            .values_list('id', flat=True)
            .distinct()
        )
        qs = qs.filter(obj_id__in=ref_obj_ids)

    her_merk_values = [name for name in request.GET.getlist('her_merk') if is_valid_qparam(name)]
    if exclude_field != 'her_merk' and her_merk_values:
        obj_ids = (
            Obj.objects.filter(Herstellungsmerkmale__name__in=her_merk_values)
            .values_list('id', flat=True)
        )
        qs = qs.filter(obj_id__in=obj_ids)

    sek_merk_values = [name for name in request.GET.getlist('sek_merk') if is_valid_qparam(name)]
    if exclude_field != 'sek_merk' and sek_merk_values:
        obj_ids = (
            Obj.objects.filter(sekundaere_Merkmale__name__in=sek_merk_values)
            .values_list('id', flat=True)
        )
        qs = qs.filter(obj_id__in=obj_ids)

    paket_values = [
        value
        for key in ('Paket', 'pakete')
        for value in request.GET.getlist(key)
        if is_valid_qparam(value)
    ]
    if exclude_field not in ('Paket', 'pakete') and paket_values:
        paket_ids = []
        paket_names = []
        for value in paket_values:
            try:
                paket_ids.append(int(value))
            except (TypeError, ValueError):
                paket_names.append(value)

        paket_query = Q()
        if paket_ids:
            paket_query |= Q(id__in=paket_ids)
        if paket_names:
            paket_query |= Q(name__in=paket_names) | Q(slug__in=paket_names) | Q(titel_oeffentlich__in=paket_names)

        public_paket_ids = Paket.objects.filter(
            paket_query,
            online_freigegeben=True,
        ).values_list('id', flat=True)
        obj_ids = Obj.objects.filter(pakete__id__in=public_paket_ids).values_list('id', flat=True).distinct()
        qs = qs.filter(obj_id__in=obj_ids)

    if needs_distinct:
        qs = qs.distinct()

    qs = qs.annotate(
        _unbestimmt_sort=Case(
            When(typ_fk__isnull=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    )
    return qs.order_by('_unbestimmt_sort', 'datierung_von', 'datierung_bis', 'pk'), is_unbestimmt, needs_distinct

