"""Bounded public representations of the shared Browse query services."""
from types import SimpleNamespace

from django.conf import settings
from django.db.models import Count, F, Min, Max
from django.http import QueryDict
from django.utils.html import strip_tags

from slg.filter_config import FILTER_PARAMETERS
from slg.models import MtoaPerson, Obj
from slg.serializers import HerstellungsmerkmaleSerializer, Sek_MerkmaleSerializer
from .search import _get_filtered_mtoa_queryset, MTOA_FACETS, public_objects


def allowed_filter_names():
    """The same public filter whitelist for transports and page context."""
    return set().union(*(set(c) for c in FILTER_PARAMETERS.values())) | {'unbestimmt'}


def filter_request(filters=None):
    """Accept only documented filter names and scalar/list values, never ORM paths."""
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        raise ValueError('filters must be an object.')
    allowed = allowed_filter_names()
    unknown = set(filters) - allowed
    if unknown:
        raise ValueError('Unknown filters: ' + ', '.join(sorted(unknown)))
    query = QueryDict('', mutable=True)
    for key, value in filters.items():
        values = value if isinstance(value, list) else [value]
        if len(values) > 100:
            raise ValueError('At most 100 values per filter.')
        if any(type(v) not in (str, int, bool) for v in values):
            raise ValueError('Filter values must be strings, integers or booleans.')
        if any(len(str(v)) > 500 for v in values):
            raise ValueError('Filter values must be at most 500 characters.')
        if key == 'unbestimmt':
            if len(values) != 1 or str(values[0]) not in ('True', 'False', 'Alle', ''):
                raise ValueError('unbestimmt must be True, False or Alle.')
        if key in ('dat_von', 'dat_bis'):
            if len(values) != 1:
                raise ValueError('Date bounds take one integer each.')
            try:
                int(values[0])
            except (ValueError, TypeError):
                raise ValueError('Date bounds must be integers.') from None
        query.setlist(key, [str(v) for v in values])
    if query.get('dat_von') and query.get('dat_bis'):
        if int(query['dat_von']) > int(query['dat_bis']):
            raise ValueError('dat_von must not exceed dat_bis.')
    return SimpleNamespace(GET=query)


def page_bounds(page, page_size):
    if type(page) is not int or page < 1:
        raise ValueError('page must be a positive integer.')
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError('page_size must be between 1 and 100.')
    return (page - 1) * page_size, page * page_size


def envelope(total, page, page_size, results):
    return dict(total=total, page=page, page_size=page_size,
                has_more=page * page_size < total, results=results)


def object_queryset(request):
    rows, _, _ = _get_filtered_mtoa_queryset(request)
    return public_objects().filter(pk__in=rows.order_by().values('obj_id'))


def text(value):
    return strip_tags(str(value)).strip() if value is not None else None


def _object_data(obj, detail=False):
    typ = obj.Typ
    def resolved(own, inherited=None):
        return getattr(obj, own) or (getattr(typ, inherited or own) if typ else None)
    def named(value):
        return {'id': value.pk, 'name': text(value.name)} if value else None
    people = []
    relations = list(obj.obj_person_set.all())
    if typ:
        relations += list(typ.mztyp_person_set.all())
    for rel in relations:
        people.append({'id': rel.idfk_Person_id, 'name': text(rel.idfk_Person.name),
                       'role': text(rel.idfk_PersonFunktion.name),
                       'role_id': rel.idfk_PersonFunktion_id,
                       'reverse': rel.appears_on_rev})
    data = {
        'id': obj.pk, 'inventory_number': obj.invnr,
        'collection': named(obj.Slg), 'collection_part': named(obj.SlgTeil),
        'coin_type_id': obj.Typ_id,
        'coin_type': text((typ.muenztyptitel or typ.titel) if typ else None),
        'title': text(resolved('titel')), 'persons': people,
        'mint': named(resolved('idfk_Mzstaette', 'Mzstaette')),
        'denomination': named(resolved('idfk_Nominal', 'Nominal')),
        'material': named(resolved('Metall')),
        'date': {'from': obj.dat_von if obj.dat_von is not None else (typ.dat_von if typ else None),
                 'to': obj.dat_bis if obj.dat_bis is not None else (typ.dat_bis if typ else None),
                 'label': text(resolved('dat_verb'))},
        'obverse': {'legend': text(resolved('avleg')),
                    'description': text(resolved('avbeschr') or resolved('av_bildtyp'))},
        'reverse': {'legend': text(resolved('rvleg')),
                    'description': text(resolved('rvbeschr') or resolved('rv_bildtyp'))},
        'url': settings.ELIGIUS_PUBLIC_BASE_URL.rstrip('/') + obj.get_absolute_url(),
    }
    if detail:
        data.update(weight=str(obj.gewicht) if obj.gewicht is not None else None,
                    diameter=str(obj.durchmesser) if obj.durchmesser is not None else None,
                    die_axis=obj.stempelstellung,
                    manufacturing_features=HerstellungsmerkmaleSerializer(obj.Herstellungsmerkmale.all(), many=True).data,
                    secondary_features=Sek_MerkmaleSerializer(obj.sekundaere_Merkmale.all(), many=True).data)
    return data


def _with_relations(qs):
    return qs.select_related('Typ', 'Slg', 'SlgTeil', 'idfk_Mzstaette',
                             'idfk_Nominal', 'Metall', 'av_bildtyp', 'rv_bildtyp',
                             'Typ__Mzstaette', 'Typ__Nominal', 'Typ__Metall',
                             'Typ__av_bildtyp', 'Typ__rv_bildtyp').prefetch_related(
        'obj_person_set__idfk_Person', 'obj_person_set__idfk_PersonFunktion',
        'Typ__mztyp_person_set__idfk_Person', 'Typ__mztyp_person_set__idfk_PersonFunktion')


def search_objects(filters=None, page=1, page_size=25):
    start, end = page_bounds(page, page_size)
    qs = object_queryset(filter_request(filters)).order_by('pk')
    total = qs.count()
    return envelope(total, page, page_size,
                    [_object_data(obj) for obj in _with_relations(qs)[start:end]])


def get_object(object_id):
    if type(object_id) is not int or object_id < 1:
        raise ValueError('object_id must be a positive integer.')
    obj = _with_relations(public_objects()).filter(pk=object_id).first()
    if obj is None:
        raise ValueError('Public object not found.')
    return _object_data(obj, detail=True)


PERSON_FACETS = ('Praegeherren', 'Dargestellte_AV', 'Dargestellte_RV', 'Person')


def facet_values(request, facet, include_current=False, term=None):
    """Shared Browse/REST/MCP counts. Always count distinct objects, not joins.

    Browse excludes its own selected facet; distributions deliberately do not.
    Fallback dimensions use the configured Obj relations on the SAME MTOA IDs.
    """
    allowed = set().union(*(set(c) for c in FILTER_PARAMETERS.values()))
    if facet not in allowed or facet in ('q', 'invnr'):
        raise ValueError('Unknown or non-aggregatable facet: ' + str(facet))
    rows, _, _ = _get_filtered_mtoa_queryset(
        request, exclude_field=None if include_current else facet)
    # Subquery prevents active person joins from contaminating facet aliases.
    from slg.models import MuenztypObjektAnzeige
    rows = MuenztypObjektAnzeige.objects.filter(pk__in=rows.order_by().values('pk'))
    if facet in MTOA_FACETS or facet in ('Nominal_id', 'dat_von', 'dat_bis'):
        config = MTOA_FACETS.get(facet) or {
            'Nominal_id': {'field': 'nominal', 'id_field': 'nominal_fk_id'},
            'dat_von': {'field': 'datierung_von'},
            'dat_bis': {'field': 'datierung_bis'},
        }[facet]
        return _group(rows, config['field'], config.get('id_field'), 'obj_id', term)
    if facet in PERSON_FACETS:
        config = FILTER_PARAMETERS['default'][facet]
        people = MtoaPerson.objects.filter(mtoa__in=rows)
        if config.get('person_function_ids'):
            people = people.filter(funktion_id__in=config['person_function_ids'])
        if config.get('exclude_function_ids'):
            people = people.exclude(funktion_id__in=config['exclude_function_ids'])
        if config.get('appears_on_rev') is not None:
            people = people.filter(appears_on_rev=config['appears_on_rev'])
        return _group(people, 'person__name', 'person_id', 'mtoa__obj_id', term)
    objects = public_objects().filter(pk__in=rows.values('obj_id'))
    if facet == 'Paket':
        # Apply the public condition to the counted join, not a separate alias.
        return _group(objects.filter(pakete__online_freigegeben=True),
                      'pakete__titel_oeffentlich', 'pakete__id', 'pk', term)
    combined = {}
    for context, typed in (('default', True), ('unbestimmt', False)):
        config = FILTER_PARAMETERS[context].get(facet)
        if not config:
            continue
        field = config.get('facet_field', config['fields'][0])
        id_field = config.get('id_field')
        if not id_field and field.endswith('__name'):
            id_field = field[:-6] + '__id'
        for value in _group(objects.filter(Typ__isnull=not typed), field, id_field, 'pk', term):
            key = (value.get('id'), value['name'])
            if key in combined:
                combined[key]['count'] += value['count']
            else:
                combined[key] = value
    return _sort_values(combined.values(), term)


def _sort_values(values, term):
    return sorted(values, key=lambda v: ((str(v['name']).casefold(), str(v.get('id', '')))
                  if term else (-v['count'], str(v['name']).casefold(), str(v.get('id', '')))))


def _group(qs, field, id_field, count_field, term):
    if term:
        qs = qs.filter(**{field + '__icontains': term})
    fields = {'value': F(field)}
    if id_field:
        fields['facet_id'] = F(id_field)
    values = qs.exclude(**{field + '__isnull': True}).order_by().values(**fields).annotate(
        count=Count(count_field, distinct=True))
    result = []
    for row in values:
        if row['value'] == '':
            continue
        item = {'name': row['value'], 'count': row['count']}
        if id_field:
            item['id'] = row['facet_id']
        result.append(item)
    return _sort_values(result, term)


def get_facets(facet, filters=None, page=1, page_size=25, include_current=False):
    start, end = page_bounds(page, page_size)
    values = facet_values(filter_request(filters), facet, include_current)
    return envelope(len(values), page, page_size, values[start:end])


def get_distribution(dimension, filters=None, page=1, page_size=25):
    start, end = page_bounds(page, page_size)
    request = filter_request(filters)
    total = object_queryset(request).count()
    values = facet_values(request, dimension, include_current=True)
    result = envelope(len(values), page, page_size, [
        dict(v, percentage=round(100 * v['count'] / total, 4) if total else 0)
        for v in values[start:end]])
    result['total_values'] = result.pop('total')
    result['total'] = total
    result['dimension'] = dimension
    result['note'] = 'Percentages use all matching objects; multi-valued dimensions can sum above 100%. Missing values are omitted.'
    return result


def statistics_for_request(request):
    rows, _, _ = _get_filtered_mtoa_queryset(request)
    data = rows.order_by().aggregate(
        total=Count('obj_id', distinct=True), coin_types=Count('typ_fk', distinct=True),
        collections=Count('slg_fk', distinct=True), mints=Count('mzstaette_fk', distinct=True),
        date_from=Min('datierung_von'), date_to=Max('datierung_bis'),
        weight_min=Min('gewicht'), weight_max=Max('gewicht'))
    for key in ('weight_min', 'weight_max'):
        data[key] = str(data[key]) if data[key] is not None else None
    return data


def get_statistics(filters=None):
    return statistics_for_request(filter_request(filters))
