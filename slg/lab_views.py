import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from slg.services.search import public_objects

logger = logging.getLogger(__name__)

HADRIAN_SHOWCASE_IDS = (
    2, 29, 96, 110, 112, 475, 484, 493, 1554, 4747,
    4757, 9095, 9184, 43038, 46243, 46761, 47315, 47528, 47529, 76630,
)


def _showcase_media():
    """Resolve public obverse/reverse image URLs for the Hadrianus Lab matrix."""
    media = {}
    try:
        rows = (
            public_objects()
            .filter(id__in=HADRIAN_SHOWCASE_IDS)
            .select_related('Slg', 'SlgTeil')
        )
        for obj in rows:
            urls = obj.get_bild_urls() or {}
            media[str(obj.id)] = {
                'av': urls.get('thumbnail_av') or urls.get('av') or '',
                'av_fallback': urls.get('av') or urls.get('thumbnail_av_alt') or urls.get('av_alt') or '',
                'rv': urls.get('thumbnail_rv') or urls.get('rv') or '',
                'rv_fallback': urls.get('rv') or urls.get('thumbnail_rv_alt') or urls.get('rv_alt') or '',
                'collection': obj.Slg.name if obj.Slg else '',
                'invnr': obj.invnr or '',
            }
    except Exception:
        logger.warning('Could not load showcase media for Eligius Lab', exc_info=True)
    return media


@require_GET
def lab(request):
    base = settings.ELIGIUS_PUBLIC_BASE_URL or request.build_absolute_uri('/').rstrip('/')
    return render(request, 'slg/lab.html', {
        'mcp_endpoint': base + '/mcp',
        'mcp_enabled': settings.ELIGIUS_MCP_ENABLED,
        'showcase_media': _showcase_media(),
    })


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok', 'mcp_enabled': settings.ELIGIUS_MCP_ENABLED})
