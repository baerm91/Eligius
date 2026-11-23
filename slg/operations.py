"""Privacy-preserving operation summaries and optional throttled HTTP 5xx alerts."""
import json
import logging
from contextlib import contextmanager
from time import perf_counter

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

logger = logging.getLogger('slg.operations')


@contextmanager
def operation(service, action, **metadata):
    start = perf_counter()
    event = {'service': service, 'action': action, 'outcome': 'ok', **metadata}
    try:
        yield event
    except Exception as error:
        if event['outcome'] == 'ok':
            event['outcome'] = 'error'
        event['error_type'] = type(error).__name__
        raise
    finally:
        event['duration_ms'] = round((perf_counter() - start) * 1000, 1)
        logger.info(json.dumps(event, ensure_ascii=False))


class ServerErrorEmailHandler(logging.Handler):
    """Send only the route name and status, without request or exception details."""

    def emit(self, record):
        status = getattr(record, 'status_code', 0)
        recipients = settings.ELIGIUS_ERROR_ALERT_RECIPIENTS
        if settings.DEBUG or status < 500 or not recipients:
            return
        request = getattr(record, 'request', None)
        match = getattr(request, 'resolver_match', None)
        route = getattr(match, 'view_name', None) or 'unresolved'
        key = f'eligius:http-error-alert:{status}:{route}'
        try:
            if not cache.add(key, True, timeout=300):
                return
            send_mail(f'Eligius HTTP {status}', f'Route: {route}\nStatus: {status}',
                      settings.SERVER_EMAIL, recipients)
        except Exception:
            logger.warning('{"service":"http","action":"send_alert","outcome":"error"}')
