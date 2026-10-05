import re
from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse


def absolute_uri(request, path):
    base = settings.ELIGIUS_PUBLIC_BASE_URL
    return urljoin(base.rstrip('/') + '/', path.lstrip('/')) if base else request.build_absolute_uri(path)


def base_url(request):
    return absolute_uri(request, reverse('oai_endpoint'))


def object_uri(request, obj_id):
    return absolute_uri(request, reverse('Objekt', kwargs={'id': obj_id}))


def identifier(obj_id):
    return f'oai:{settings.ELIGIUS_OAI_IDENTIFIER_NAMESPACE}:object:{obj_id}'


def parse_identifier(value):
    prefix = f'oai:{settings.ELIGIUS_OAI_IDENTIFIER_NAMESPACE}:object:'
    suffix = value[len(prefix):] if value.startswith(prefix) else ''
    return int(suffix) if re.fullmatch(r'[1-9][0-9]{0,9}', suffix) else None


def set_spec(slg_id):
    """The immutable collection PK avoids name-dependent slugs or extra state."""
    return f'eligius:collection-{slg_id}'
