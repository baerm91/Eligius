from django import template
from django.conf import settings
from django.utils.translation import get_language, gettext as _

from djangoproject.middleware import ROBOTS_NOINDEX
from slg.seo import absolute_url, canonical_url as _canonical_url, clean_text, default_share_image

register = template.Library()


@register.simple_tag(takes_context=True)
def canonical_url(context):
    """Absolute kanonische URL der aktuellen Seite (ohne Query-Parameter)."""
    request = context.get('request')
    if request is None:
        return ''
    return _canonical_url(request)


@register.simple_tag
def robots_directive():
    return '' if settings.ELIGIUS_SEO_INDEXING else ROBOTS_NOINDEX


def default_description():
    return _('Eligius ist das digitale Münzkabinett für klösterliche und öffentliche Sammlungen in '
             'Österreich: Münzen, Münztypen, Prägeherren und Münzstätten frei recherchieren.')


@register.inclusion_tag('slg/partials/html/seo_meta.html', takes_context=True)
def seo_meta(context, title='', description='', image='', type='website'):
    """Meta-Description, Open-Graph- und Twitter-Card-Tags einer Seite.

    ``image`` darf relativ sein; ohne eigenes Bild wird das Eligius-Motiv
    verwendet und als kleine ``summary``-Karte ausgespielt.
    """
    request = context.get('request')
    own_image = absolute_url(image, request)
    return {
        'title': clean_text(title, limit=0) or 'Eligius',
        'description': clean_text(description) or default_description(),
        'image': own_image or default_share_image(request),
        'card': 'summary_large_image' if own_image else 'summary',
        'type': type,
        'url': _canonical_url(request) if request is not None else '',
        'locale': 'en_GB' if (get_language() or '').startswith('en') else 'de_AT',
    }
