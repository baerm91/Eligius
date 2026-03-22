# Archived legacy view code moved out of active runtime paths.

def objekt_list_view(request):
    filters = []
    context_key = 'unbestimmt' if request.GET.get('unbestimmt') else 'default'
    parameters = FILTER_PARAMETERS.get(context_key, {})

    invnr = request.GET.get('invnr')
    if invnr:
        obj = Obj.objects.only('id').filter(invnr=invnr).first()
        if obj:
            return redirect('Objekt', id=obj.id)
    
    # Alles außer Personen
    general_filters = []
    for param, cfg in parameters.items():
        if param in ['Praegeherren', 'Dargestellte_AV', 'Dargestellte_RV', 'Person']:
            continue
            
        values = [v for v in request.GET.getlist(param) if is_valid_qparam(v)]
        if not values:
            continue

        if cfg['filter'] == 'exact' and len(values) > 1:
            general_filters.append(Q(**{f"{cfg['fields'][0]}__in": values}))
        else:
            per_value = [
                Q(**{f"{field}__{cfg['filter']}": val})
                for val in values
                for field in cfg['fields']
            ]
            general_filters.append(reduce(or_, per_value))
    
    mztyp_person_prefetch = Prefetch(
        'Typ__mztyp_person_set',
        queryset=Mztyp_Person.objects.select_related(
            'idfk_Person', 
            'idfk_PersonFunktion'
        ).order_by('idfk_PersonFunktion__name')
    )
    
    av_schlagwort_prefetch = Prefetch(
        'Typ__av_bildtyp__avbildtyp_schlagwort_set',
        queryset=AvBildtyp_Schlagwort.objects.select_related('schlagwort')
    )
    
    rv_schlagwort_prefetch = Prefetch(
        'Typ__rv_bildtyp__rvbildtyp_schlagwort_set',
        queryset=RvBildtyp_Schlagwort.objects.select_related('schlagwort')
    )

    # Erstellen des Basis-Querysets
    if context_key == 'unbestimmt':
        qs = Obj.objects.filter(Typ__isnull=True).select_related(
            'SlgTeil', 'Slg', 'idfk_Nominal', 'Metall', 'idfk_Mzstaette', 'idfk_Muenzstand', 'region'
        ).prefetch_related(
            'Ppl', 'idfk_Ref','Herstellungsmerkmale', 'sekundaere_Merkmale'
        ).order_by('dat_von')
    else:
        qs = Obj.objects.filter(Typ__isnull=False).select_related(
            'Typ', 'Typ__Nominal', 'Typ__Metall',
            'SlgTeil', 'Slg', 'Typ__Mzstaette', 'Typ__region',
            'Typ__av_bildtyp', 'Typ__rv_bildtyp'
        ).prefetch_related(                                  
            'Typ__Ref', 'Typ__wappen',
            'Herstellungsmerkmale', 'sekundaere_Merkmale', 'Ppl', 'idfk_Ref',
            mztyp_person_prefetch,
            av_schlagwort_prefetch,
            rv_schlagwort_prefetch,
        ).order_by('Typ__dat_von', 'Typ__dat_bis')

    # Kombiniere die allgemeinen Filter
    if general_filters:
        qs = qs.filter(reduce(and_, general_filters))

    # Anwenden der Person-Filter über apply_filters
    qs = apply_filters(request, qs, exclude_field=None)
    
    # Anwenden der anderen Filter
    if filters:
        qs = qs.filter(reduce(and_, filters))

    qs = qs.distinct()

    context_is_unb = bool(request.GET.get('unbestimmt'))
    mint_path = 'idfk_Mzstaette' if context_is_unb else 'Typ__Mzstaette'

    # ✅ Database-agnostic Gruppierung nach Münzstätte (MySQL/SQLite/PostgreSQL kompatibel)
    mints_qs = (
        qs.exclude(**{f'{mint_path}__isnull': True})
        .values(
            f'{mint_path}__id',           # Gruppiere nach Münzstätten-ID
            f'{mint_path}__name',         # Gruppiere auch nach Name
            f'{mint_path}__region__name', # und Region
            f'{mint_path}__lat',          # und Koordinaten
            f'{mint_path}__long',
        )
        .annotate(
            mint_id     = F(f'{mint_path}__id'),
            mint_name   = F(f'{mint_path}__name'),
            mint_region = F(f'{mint_path}__region__name'),
            mint_lat    = F(f'{mint_path}__lat'),
            mint_lon    = F(f'{mint_path}__long'),
            obj_count   = Count('pk', distinct=True),
        )
        .order_by(f'{mint_path}__id')
    )

    # -------- Marker-Liste für JS --------
    mints_for_js = [
        {
            'id'        : m['mint_id'],
            'name'      : m['mint_name'],
            'region'    : m['mint_region'],
            'longitude' : float(m['mint_lon']) if m['mint_lon'] is not None else None,
            'latitude'  : float(m['mint_lat']) if m['mint_lat'] is not None else None,
            'count'     : m['obj_count'],
        }
        for m in mints_qs
        if m['mint_lon'] and m['mint_lat']
    ]

    # -------- optionales Dict (wenn gebraucht) --------
    mints_map = {
        (m['name'], m['region']): {
            'id'        : m['id'],
            'name'      : m['name'],
            'region'    : m['region'],
            'longitude' : m['longitude'],
            'latitude'  : m['latitude'],
        }
        for m in mints_for_js
    }

    page = request.GET.get('page', 1)
    paginator = Paginator(qs, 30)
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
    
    context = {
        'Objekte': qs,
        'Mints': mints_map,
        'mints_map': json.dumps(mints_for_js),
        'Anzahl': anzahl,
        'getvars': '&{0}'.format(variables.urlencode()),
        'filter_config': parameters,
    }

    return render(request, 'slg/Objektliste.html', context)
