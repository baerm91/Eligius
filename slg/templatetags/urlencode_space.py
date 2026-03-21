from django import template
from urllib.parse import quote

register = template.Library()

@register.simple_tag
def add_filter_param(key, value):
    # quote() kodiert Leerzeichen als %20, nicht als +
    return f"{key}={quote(str(value), safe='')}"