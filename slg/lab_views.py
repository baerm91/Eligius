from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def lab(request):
    base = settings.ELIGIUS_PUBLIC_BASE_URL or request.build_absolute_uri('/').rstrip('/')
    return render(request, 'slg/lab.html', {
        'mcp_endpoint': base + '/mcp',
        'mcp_enabled': settings.ELIGIUS_MCP_ENABLED,
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
