"""Optional browser bridge to the existing public MCP tools. No search logic."""
import json
import logging
from functools import wraps
from urllib.parse import urlsplit

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import JsonResponse, QueryDict
from django.urls import resolve, reverse, Resolver404
from django.views.decorators.csrf import csrf_exempt
from jsonschema import validate, ValidationError

from slg.services.public_api import filter_request, allowed_filter_names
from slg.services.search import public_objects
from slg.models import Muenztyp, Slg

logger = logging.getLogger(__name__)
DATA_TOOLS = ('search_objects', 'get_object', 'get_facets', 'get_distribution', 'get_statistics')
NAVIGATION = {
    'navigate_to_object': ('object_id', 'Objekt', 'Open a public object detail page in this tab. Changes the page, never catalogue data.'),
    'navigate_to_coin_type': ('type_id', 'Typ', 'Open a public coin type page in this tab. Changes the page, never catalogue data.'),
    'open_collection': ('collection_id', 'Sammlung', 'Open a public collection in this tab. Use get_facets with Slg to discover IDs. Changes the page only.'),
}


def webmcp_enabled(request):
    """Template context, independent of whether Remote MCP is enabled."""
    return {'webmcp_enabled': settings.ELIGIUS_WEBMCP_ENABLED}


def _endpoint(method):
    def decorate(function):
        @wraps(function)
        async def wrapped(request, *args, **kwargs):
            if not settings.ELIGIUS_WEBMCP_ENABLED:
                return JsonResponse({'error': 'WebMCP is disabled.'}, status=404)
            if request.method != method:
                response = JsonResponse({'error': 'Method not allowed.'}, status=405)
                response['Allow'] = method
                return response
            try:
                result = await function(request, *args, **kwargs)
                response = JsonResponse(result)
            except (ValueError, TypeError, ValidationError):
                response = JsonResponse({'error': 'Invalid arguments or unavailable public record.'}, status=400)
            except Exception:
                logger.exception('WebMCP bridge failed')
                response = JsonResponse({'error': 'Query could not be completed.'}, status=503)
            response['Cache-Control'] = 'no-store'
            return response
        # These POSTs only read public data or return a URL. They never perform
        # navigation, mutate data, or use the caller's session/privileges.
        return csrf_exempt(wrapped)
    return decorate


def _arguments(request):
    if request.content_type != 'application/json' or len(request.body) > 65536:
        raise ValueError('Expected bounded JSON arguments.')
    arguments = json.loads(request.body)
    if not isinstance(arguments, dict):
        raise ValueError('Arguments must be an object.')
    return arguments


async def _definitions():
    from slg.mcp_server import mcp
    return {tool.name: tool.model_dump(by_alias=True, exclude_none=True)
            for tool in await mcp.list_tools() if tool.name in DATA_TOOLS}


def _ui_definitions(filters_schema):
    tools = []
    for name, (parameter, _, description) in NAVIGATION.items():
        tools.append({'name': name, 'description': description, 'inputSchema': {
            'type': 'object', 'properties': {parameter: {'type': 'integer', 'minimum': 1}},
            'required': [parameter], 'additionalProperties': False},
            'annotations': {'readOnlyHint': False}})
    tools += [
        {'name': 'set_browse_filters',
         'description': 'Replace the current selection by opening normal Browse with these filters. Same filters as search_objects; resets pagination. Changes this tab only.',
         'inputSchema': {'type': 'object', 'properties': {'filters': filters_schema},
                         'required': ['filters'], 'additionalProperties': False},
         'annotations': {'readOnlyHint': False}},
        {'name': 'clear_browse_filters',
         'description': 'Open normal Browse without filters or pagination. Changes this tab only.',
         'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
         'annotations': {'readOnlyHint': False}},
        {'name': 'get_current_context',
         'description': 'Read the current page type, public object/type/collection IDs and active Browse filters. Use its filters explicitly in data tools for questions about this selection. Does not navigate.',
         'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
         'annotations': {'readOnlyHint': True}},
    ]
    return tools


@_endpoint('GET')
async def manifest(request):
    from slg.mcp_server import mcp
    definitions = await _definitions()
    data_tools = []
    for name in DATA_TOOLS:
        tool = definitions[name]
        data_tools.append({'name': name, 'description': tool['description'],
                           'inputSchema': tool['inputSchema'],
                           'annotations': {'readOnlyHint': True, 'untrustedContentHint': True},
                           'endpoint': reverse('webmcp_data', kwargs={'tool_name': name})})
    ui_tools = _ui_definitions(definitions['search_objects']['inputSchema']['properties']['filters'])
    for tool in ui_tools:
        tool['endpoint'] = (reverse('webmcp_context') if tool['name'] == 'get_current_context'
                            else reverse('webmcp_navigation', kwargs={'tool_name': tool['name']}))
    return {'data_tools': data_tools, 'ui_tools': ui_tools, 'instructions': mcp.instructions,
            'filter_names': sorted(allowed_filter_names())}


@_endpoint('POST')
async def data(request, tool_name):
    if tool_name not in DATA_TOOLS:
        raise ValueError('Unknown public tool.')
    arguments = _arguments(request)
    from slg.mcp_server import mcp
    from mcp.server.mcpserver.exceptions import ToolError
    try:
        # Public SDK dispatch reuses the exact Remote MCP schemas, validation,
        # callbacks, output conversion, connection handling and query services.
        result = await mcp.call_tool(tool_name, arguments)
    except ToolError:
        raise ValueError('Invalid tool arguments.') from None
    if result.is_error:
        raise ValueError('Public query failed.')
    # SDK v2 encodes an untyped dict as JSON text unless structured_output was
    # explicitly requested. Preserve the existing Remote MCP registration.
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def _navigation_target(tool_name, arguments):
    if tool_name == 'clear_browse_filters':
        return {'url': reverse('Objektliste')}
    if tool_name == 'set_browse_filters':
        query = filter_request(arguments['filters']).GET.urlencode()
        return {'url': reverse('Objektliste') + ('?' + query if query else '')}
    parameter, route, _ = NAVIGATION[tool_name]
    record_id = arguments[parameter]
    queryset = {'Objekt': public_objects, 'Typ': lambda: Muenztyp.objects.all(),
                'Sammlung': lambda: Slg.objects.all()}[route]()
    if not queryset.filter(pk=record_id).exists():
        raise ValueError('Public record unavailable.')
    return {'url': reverse(route, kwargs={'id': record_id})}


@_endpoint('POST')
async def navigation(request, tool_name):
    arguments = _arguments(request)
    definitions = await _definitions()
    ui_tools = {t['name']: t for t in _ui_definitions(
        definitions['search_objects']['inputSchema']['properties']['filters'])}
    if tool_name not in ui_tools or tool_name == 'get_current_context':
        raise ValueError('Unknown navigation action.')
    validate(arguments, ui_tools[tool_name]['inputSchema'])
    return await sync_to_async(_navigation_target)(tool_name, arguments)


def _page_context(url):
    if len(url) > 16384:
        raise ValueError('Context URL too long.')
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path.startswith('/'):
        raise ValueError('Only local page context is permitted.')
    try:
        match = resolve(parts.path)
    except Resolver404:
        return {'page_type': 'other'}
    if match.url_name == 'Objektliste':
        query = QueryDict(parts.query)
        # Drop pagination, tokens and presentation controls, not arbitrary ORM
        # paths. Only the shared filter whitelist can enter returned context.
        allowed = allowed_filter_names()
        filters = {key: query.getlist(key) for key in query if key in allowed}
        filters = dict(filter_request(filters).GET.lists())
        return {'page_type': 'browse', 'filters': filters}
    if match.url_name == 'Objekt':
        obj = public_objects().filter(pk=match.kwargs['id']).values('pk', 'Typ_id', 'Slg_id').first()
        if not obj:
            raise ValueError('Public object unavailable.')
        return {'page_type': 'object', 'object_id': obj['pk'],
                'type_id': obj['Typ_id'], 'collection_id': obj['Slg_id']}
    if match.url_name in ('Typ', 'Sammlung'):
        key, route, _ = next(value for value in NAVIGATION.values() if value[1] == match.url_name)
        _navigation_target('navigate_to_coin_type' if route == 'Typ' else 'open_collection', {key: match.kwargs['id']})
        return {'page_type': 'coin_type' if route == 'Typ' else 'collection', key: match.kwargs['id']}
    return {'page_type': 'lab' if match.url_name == 'lab' else 'other'}


@_endpoint('GET')
async def context(request):
    return await sync_to_async(_page_context)(request.GET.get('url', '/'))
