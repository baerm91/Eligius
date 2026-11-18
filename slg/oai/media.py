"""Image redirect service: stable, consumer-neutral Eligius image URIs.

Exports (OAI/EDM for Kulturpool, which forwards to Europeana, and any future
consumer) contain /bild/<obj>/<ansicht>/ instead of the file location. Each
request is answered with a temporary redirect to the image file as currently
resolved, so moving the images to another host only requires changing the
collection settings. GET requests are counted per day, object and view. The
origin is only the host name of the embedding page (from the Referer, which
browsers reduce to the origin for cross-site images); no IP address, user
agent or full referrer is stored.
"""
import logging
import re
from urllib.parse import urlsplit

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.http import Http404, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from slg.models import Bildabruf

from .edm import source_images
from .querysets import export_rows

logger = logging.getLogger(__name__)
VARIANTS = {choice for choice, _ in Bildabruf.ANSICHTEN}
# Harvesters, crawlers and image pipelines rather than people viewing a page.
AUTOMATED = re.compile(
    r'bot|crawl|spider|slurp|harvest|preview|fetch|python|java/|curl|wget|httpclient|okhttp|go-http|'
    r'axios|node-fetch|libwww|scrapy|headless|thumbnail|imagemagick|europeana|kulturpool', re.IGNORECASE)


def is_automated(request):
    agent = request.META.get('HTTP_USER_AGENT', '')
    return not agent or bool(AUTOMATED.search(agent))


def origin_host(request):
    """Host of the embedding page, e.g. 'kulturpool.at'; '' for direct or unknown requests."""
    try:
        host = (urlsplit(request.META.get('HTTP_REFERER', '')).hostname or '').lower()
    except ValueError:
        return ''
    host = host[4:] if host.startswith('www.') else host
    own = (request.get_host().split(':')[0] or '').lower()
    own = own[4:] if own.startswith('www.') else own
    if host and host == own:
        return 'eligius'
    return host[:100]


def count(obj_id, ansicht, herkunft, automated):
    key = dict(obj_id=obj_id, ansicht=ansicht, herkunft=herkunft,
               datum=timezone.localdate(), automatisiert=automated)
    try:
        if Bildabruf.objects.filter(**key).update(anzahl=F('anzahl') + 1):
            return
        try:
            with transaction.atomic():
                Bildabruf.objects.create(anzahl=1, **key)
        except IntegrityError:
            # A concurrent first request created today's row.
            Bildabruf.objects.filter(**key).update(anzahl=F('anzahl') + 1)
    except DatabaseError:
        # Statistics must never break image delivery.
        logger.exception('Bildabruf konnte nicht gezählt werden')


@require_http_methods(['GET', 'HEAD'])
def bild_weiterleitung(request, obj_id, ansicht):
    if ansicht not in VARIANTS:
        raise Http404
    # Same publication rules as OAI: withdrawn objects disappear here as well.
    row = export_rows().filter(obj_id=obj_id).select_related(
        'slg_fk', 'slgteil_fk', 'slgteil_fk__idfk_Slg_SlgTeil').first()
    target = source_images(row, request).get(ansicht) if row else None
    if not target:
        raise Http404
    if request.method == 'GET':
        count(obj_id, ansicht, origin_host(request), is_automated(request))
    response = HttpResponseRedirect(target)
    # Every request must reach Eligius to be counted and to follow future moves.
    response['Cache-Control'] = 'no-store'
    return response
