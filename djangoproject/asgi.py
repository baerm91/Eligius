"""
ASGI config for djangoproject project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoproject.settings')

application = get_asgi_application()

from django.conf import settings

if settings.ELIGIUS_MCP_ENABLED:
    from slg.mcp_server import http_app

    django_application = application

    async def application(scope, receive, send):
        # The SDK owns its lifespan at the root; no lost mounted lifespan.
        # Pass /mcp through unchanged to avoid redirecting JSON-RPC POSTs.
        if scope['type'] == 'lifespan' or scope.get('path') == '/mcp':
            await http_app(scope, receive, send)
        else:
            await django_application(scope, receive, send)
