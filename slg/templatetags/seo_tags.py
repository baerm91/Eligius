from django import template

from slg.seo import canonical_url as _canonical_url

register = template.Library()


@register.simple_tag(takes_context=True)
def canonical_url(context):
    """Absolute kanonische URL der aktuellen Seite (ohne Query-Parameter)."""
    request = context.get('request')
    if request is None:
        return ''
    return _canonical_url(request)
