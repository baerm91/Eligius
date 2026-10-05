"""OAI-PMH validation and pagination, independent of Django HTTP handling."""
import re
from datetime import datetime, timedelta, timezone as utc_timezone
from xml.etree import ElementTree as ET

from django.conf import settings
from django.core import signing
from django.db.models import Max, Min
from django.utils import timezone

from slg.models import Slg
from .dc import serialize_dc
from .edm import EDM_SCHEMA, serialize_edm
from .identifiers import base_url, identifier, parse_identifier, set_spec
from .querysets import export_rows, objects_for_rows, with_metadata_relations
from .xml import INVALID_XML, NS, element, qname

FORMATS = {
    'edm': (EDM_SCHEMA, NS['rdf']),
    'oai_dc': ('http://www.openarchives.org/OAI/2.0/oai_dc.xsd', NS['oai_dc']),
}
ARGUMENTS = {
    'Identify': (set(), set()),
    'ListMetadataFormats': (set(), {'identifier'}),
    'ListSets': (set(), {'resumptionToken'}),
    'GetRecord': ({'identifier', 'metadataPrefix'}, set()),
    'ListIdentifiers': ({'metadataPrefix'}, {'set', 'from', 'until', 'resumptionToken'}),
    'ListRecords': ({'metadataPrefix'}, {'set', 'from', 'until', 'resumptionToken'}),
}
TOKEN_SALT = 'slg.oai.pagination.v1'
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)?')
SET = re.compile(r'[A-Za-z0-9_!~*\x27().-]+(?::[A-Za-z0-9_!~*\x27().-]+)*')


class OAIError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def datestamp(value):
    if timezone.is_naive(value):
        value = timezone.make_aware(value, utc_timezone.utc)
    return value.astimezone(utc_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def date_bounds(params):
    bounds = []
    for key in ('from', 'until'):
        value = params.get(key)
        if value is None:
            bounds.append(None)
            continue
        if not DATE.fullmatch(value):
            raise OAIError('badArgument', 'Dates must be YYYY-MM-DD or YYYY-MM-DDThh:mm:ssZ.')
        try:
            parsed = datetime.strptime(value, '%Y-%m-%d' if len(value) == 10 else '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=utc_timezone.utc)
            if key == 'until':
                # Exclusive next instant implements inclusive OAI granularity,
                # including DB microseconds in the last requested second/day.
                parsed += timedelta(days=1) if len(value) == 10 else timedelta(seconds=1)
        except (ValueError, OverflowError):
            raise OAIError('badArgument', 'Invalid date.') from None
        bounds.append(parsed)
    if params.get('from') and params.get('until'):
        if len(params['from']) != len(params['until']):
            raise OAIError('badArgument', 'from and until must use the same granularity.')
        if params['from'] > params['until']:
            raise OAIError('badArgument', 'from must not exceed until.')
    return bounds


def validate_parameters(query):
    if len(query.getlist('verb')) != 1 or query.get('verb') not in ARGUMENTS:
        raise OAIError('badVerb', 'A single supported verb is required.')
    verb = query['verb']
    if any(len(values) != 1 for _, values in query.lists()):
        raise OAIError('badArgument', 'Arguments must not be repeated.')
    params = query.dict()
    if any(INVALID_XML.search(value) for value in params.values()):
        raise OAIError('badArgument', 'Arguments contain characters invalid in XML 1.0.')
    required, optional = ARGUMENTS[verb]
    if set(params) - {'verb'} - required - optional:
        raise OAIError('badArgument', 'Unexpected argument for this verb.')
    if 'resumptionToken' in params:
        if set(params) != {'verb', 'resumptionToken'}:
            raise OAIError('badArgument', 'resumptionToken is exclusive.')
        if not params['resumptionToken'] or len(params['resumptionToken']) > 4096:
            raise OAIError('badResumptionToken', 'Invalid resumption token.')
        return params
    if any(not value or len(value) > 4096 for value in params.values()):
        raise OAIError('badArgument', 'Arguments must be nonempty and at most 4096 characters.')
    if required - set(params):
        raise OAIError('badArgument', 'Missing required argument.')
    if 'metadataPrefix' in params and params['metadataPrefix'] not in FORMATS:
        raise OAIError('cannotDisseminateFormat', 'Supported formats are edm and oai_dc.')
    if 'set' in params and not SET.fullmatch(params['set']):
        raise OAIError('badArgument', 'Invalid set specification.')
    date_bounds(params)
    return params


def decode_token(token, verb):
    try:
        state = signing.loads(token, salt=TOKEN_SALT, max_age=settings.ELIGIUS_OAI_TOKEN_MAX_AGE)
        if not isinstance(state, dict) or set(state) != {'v', 'verb', 'prefix', 'set', 'from', 'until', 'after', 'upper', 'cursor', 'size'}:
            raise ValueError()
        if type(state['v']) is not int or state['v'] != 1 or state['verb'] != verb:
            raise ValueError()
        for key in ('after', 'upper', 'cursor', 'size'):
            if type(state[key]) is not int or not 0 <= state[key] <= 2**63 - 1:
                raise ValueError()
        if not 1 <= state['size'] <= 500 or state['after'] > state['upper']:
            raise ValueError()
        for key in ('prefix', 'set', 'from', 'until'):
            if state[key] is not None and (not isinstance(state[key], str) or len(state[key]) > 500):
                raise ValueError()
        if verb == 'ListSets':
            if any(state[key] is not None for key in ('prefix', 'set', 'from', 'until')):
                raise ValueError()
        else:
            if state['prefix'] not in FORMATS:
                raise ValueError()
            if state['set'] is not None and not SET.fullmatch(state['set']):
                raise ValueError()
            date_bounds({key: state[key] for key in ('from', 'until') if state[key] is not None})
        return state
    except (signing.BadSignature, ValueError, TypeError, KeyError, OAIError):
        raise OAIError('badResumptionToken', 'Invalid, expired or incompatible resumption token.') from None


def initial_state(params):
    return dict(v=1, verb=params['verb'], prefix=params.get('metadataPrefix'),
                set=params.get('set'), **{'from': params.get('from'), 'until': params.get('until')},
                after=0, upper=0, cursor=0, size=max(1, min(settings.ELIGIUS_OAI_PAGE_SIZE, 500)))


def header(parent, row):
    node = element(parent, 'oai', 'header')
    element(node, 'oai', 'identifier', identifier(row.obj_id))
    element(node, 'oai', 'datestamp', datestamp(row.last_modified))
    element(node, 'oai', 'setSpec', set_spec(row.slg_fk_id))


def add_record(parent, row, obj, request, prefix):
    node = element(parent, 'oai', 'record')
    header(node, row)
    metadata = element(node, 'oai', 'metadata')
    metadata.append((serialize_edm if prefix == 'edm' else serialize_dc)(row, obj, request))


def add_token(node, state, page, more, resumed, key):
    if more:
        next_state = dict(state, after=key(page[-1]), cursor=state['cursor'] + len(page))
        token = signing.dumps(next_state, salt=TOKEN_SALT)
        element(node, 'oai', 'resumptionToken', token, cursor=str(state['cursor']))
    elif resumed:
        # Empty token terminates an incomplete-list sequence.
        element(node, 'oai', 'resumptionToken', '', cursor=str(state['cursor']))


def list_response(root, params, request):
    verb = params['verb']
    resumed = 'resumptionToken' in params
    state = decode_token(params['resumptionToken'], verb) if resumed else initial_state(params)
    if verb == 'ListSets':
        rows = Slg.objects.filter(kulturpool_export_erlaubt=True).only('pk', 'name').order_by('pk')
        key = lambda row: row.pk
    else:
        rows = export_rows()
        if state['set']:
            if not Slg.objects.filter(kulturpool_export_erlaubt=True).exists():
                raise OAIError('noSetHierarchy', 'No export collections are configured.')
            if state['set'] != 'eligius':
                match = re.fullmatch(r'eligius:collection-([1-9][0-9]{0,9})', state['set'])
                rows = rows.filter(slg_fk_id=int(match[1])) if match else rows.none()
        lower, upper = date_bounds({key: state[key] for key in ('from', 'until') if state[key] is not None})
        if lower:
            rows = rows.filter(last_modified__gte=lower)
        if upper:
            rows = rows.filter(last_modified__lt=upper)
        key = lambda row: row.obj_id
    field = 'pk' if verb == 'ListSets' else 'obj_id'
    if not resumed:
        state['upper'] = rows.aggregate(last=Max(field))['last'] or 0
    rows = rows.filter(**{field + '__gt': state['after'], field + '__lte': state['upper']})
    if verb == 'ListRecords':
        rows = with_metadata_relations(rows)
    elif verb == 'ListIdentifiers':
        rows = rows.only('obj_id', 'last_modified', 'slg_fk_id')
    page = list(rows[:state['size'] + 1])
    if not page:
        code = 'badResumptionToken' if resumed else ('noSetHierarchy' if verb == 'ListSets' else 'noRecordsMatch')
        raise OAIError(code, 'No matching records or sets.')
    more = len(page) > state['size']
    page = page[:state['size']]
    objects = objects_for_rows(page) if verb == 'ListRecords' else {}
    if verb == 'ListRecords' and any(row.obj_id not in objects or
                                    objects[row.obj_id].Slg_id != row.slg_fk_id or
                                    objects[row.obj_id].Typ_id != row.typ_fk_id for row in page):
        # A concurrent withdrawal must never accidentally release stale metadata.
        raise OAIError('badResumptionToken' if resumed else 'noRecordsMatch', 'Records changed during this request; retry harvesting.')
    node = element(root, 'oai', verb)
    for row in page:
        if verb == 'ListSets':
            item = element(node, 'oai', 'set')
            element(item, 'oai', 'setSpec', set_spec(row.pk))
            element(item, 'oai', 'setName', row.name)
        elif verb == 'ListIdentifiers':
            header(node, row)
        else:
            add_record(node, row, objects[row.obj_id], request, state['prefix'])
    add_token(node, state, page, more, resumed, key)


def respond(query, request):
    root = ET.Element(qname('oai', 'OAI-PMH'), {
        qname('xsi', 'schemaLocation'): NS['oai'] + ' http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd',
    })
    element(root, 'oai', 'responseDate', datestamp(timezone.now()))
    echo = element(root, 'oai', 'request', base_url(request))
    try:
        params = validate_parameters(query)
        echo.attrib.update(params)
        verb = params['verb']
        if verb == 'Identify':
            node = element(root, 'oai', verb)
            earliest = export_rows().aggregate(first=Min('last_modified'))['first']
            for name, value in (
                ('repositoryName', settings.ELIGIUS_OAI_REPOSITORY_NAME),
                ('baseURL', base_url(request)), ('protocolVersion', '2.0'),
                ('adminEmail', settings.ELIGIUS_OAI_ADMIN_EMAIL),
                ('earliestDatestamp', datestamp(earliest) if earliest else '1970-01-01T00:00:00Z'),
                ('deletedRecord', 'no'), ('granularity', 'YYYY-MM-DDThh:mm:ssZ'),
            ):
                element(node, 'oai', name, value)
        elif verb in ('GetRecord', 'ListMetadataFormats'):
            row = None
            if 'identifier' in params:
                obj_id = parse_identifier(params['identifier'])
                row = with_metadata_relations(export_rows()).filter(obj_id=obj_id).first() if obj_id else None
                if row is None:
                    raise OAIError('idDoesNotExist', 'No exportable record exists for this identifier.')
            if verb == 'ListMetadataFormats':
                node = element(root, 'oai', verb)
                for prefix, (schema, namespace) in FORMATS.items():
                    item = element(node, 'oai', 'metadataFormat')
                    for name, value in (('metadataPrefix', prefix), ('schema', schema), ('metadataNamespace', namespace)):
                        element(item, 'oai', name, value)
            else:
                obj = objects_for_rows([row]).get(row.obj_id)
                if obj is None or obj.Slg_id != row.slg_fk_id or obj.Typ_id != row.typ_fk_id:
                    raise OAIError('idDoesNotExist', 'No exportable record exists for this identifier.')
                node = element(root, 'oai', verb)
                add_record(node, row, obj, request, params['metadataPrefix'])
        else:
            list_response(root, params, request)
    except OAIError as error:
        for child in list(root)[2:]:
            root.remove(child)
        if error.code in ('badVerb', 'badArgument'):
            echo.attrib.clear()
        element(root, 'oai', 'error', error.message, code=error.code)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
