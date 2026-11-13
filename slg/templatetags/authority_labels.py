from django import template
from slg.services.authority_display import display_label, display_text, FACET_MODELS

register = template.Library()
register.filter('display_label', display_label)
register.filter('authority_text', display_text)


@register.filter
def facet_label(value, facet):
    return display_text(value, FACET_MODELS.get(facet))
