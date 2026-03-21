from django import template
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from slg.filter_config import FILTER_PARAMETERS
from django.apps import apps
from django.shortcuts import get_object_or_404

register = template.Library()

@register.simple_tag
def remove_query_value(url, key, value):
    scheme, netloc, path, query_string, fragment = urlsplit(url)
    params = parse_qs(query_string)

    if key in params and value in params[key]:
        params[key].remove(value)
        if not params[key]:
            params.pop(key)

    new_query_string = urlencode(params, doseq=True)
    return urlunsplit((scheme, netloc, path, new_query_string, fragment))

@register.filter
def get_display_name(key, value):
    """
    Wandelt eine ID in einen lesbaren Namen um, basierend auf dem Parameterkontext.
    Nutzt die FILTER_PARAMETERS-Konfiguration, um die Beziehung zu ermitteln.
    """
    config = FILTER_PARAMETERS.get('default', {}).get(key) or FILTER_PARAMETERS.get('unbestimmt', {}).get(key)
    if not config:
        return value  # Kein spezieller Display-Name definiert
    
    if config['model'] is None:
        return value  # Für Suchparameter wie 'q' den Wert direkt zurückgeben

    # Überprüfen, ob der Wert eine Ganzzahl ist
    try:
        int_value = int(value)
    except ValueError:
        return value  # Wert ist keine ID, also geben wir ihn direkt zurück

    try:
        model = config['model']
        # Annahme: 'value' ist die ID des Objekts
        related_obj = get_object_or_404(model, pk=value)
        return getattr(related_obj, config['display_field'], value)
    except (model.DoesNotExist, AttributeError):
        return value

@register.filter
def getlist(dictionary, key):
    return dictionary.getlist(key)

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def split(value, arg):
    return value.split(arg)