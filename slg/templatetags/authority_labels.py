from django import template
from slg.services.authority_display import display_label, display_text, FACET_MODELS

register = template.Library()
register.filter('display_label', display_label)
register.filter('authority_text', display_text)


@register.filter
def facet_label(value, facet):
    return display_text(value, FACET_MODELS.get(facet))


@register.filter
def nomisma_url(value):
    """Absolute Nomisma URL or '' — an empty href would link back to the current page."""
    from slg.services.authority_inventory import identify_authority
    ref = identify_authority(value, allow_nomisma_id=True)
    if not ref or ref[0] != 'nomisma':
        return ''
    return f'https://nomisma.org/id/{ref[1]}'
