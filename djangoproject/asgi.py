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

if settings.ELIGIUS_MCP_ENABLED or settings.ELIGIUS_EDITOR_MCP_ENABLED:
    from contextlib import AsyncExitStack, asynccontextmanager
    from starlette.applications import Starlette

    django_application = application
    transports = {}
    sdk_apps = []
    if settings.ELIGIUS_MCP_ENABLED:
        from slg.mcp_server import http_app
        transports['/mcp'] = http_app
        sdk_apps.append(http_app)
    if settings.ELIGIUS_EDITOR_MCP_ENABLED:
        from slg.editor_mcp import http_app as editor_http_app, authenticated_app
        transports['/mcp/editor'] = authenticated_app
        sdk_apps.append(editor_http_app)

    @asynccontextmanager
    async def lifespan(app):
        async with AsyncExitStack() as stack:
            for sdk_app in sdk_apps:
                await stack.enter_async_context(sdk_app.router.lifespan_context(sdk_app))
            yield

    lifecycle = Starlette(lifespan=lifespan)

    async def application(scope, receive, send):
        if scope['type'] == 'lifespan':
            await lifecycle(scope, receive, send)
        else:
            await transports.get(scope.get('path'), django_application)(scope, receive, send)
