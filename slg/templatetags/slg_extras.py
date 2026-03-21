from django import template
from django.http import QueryDict
# EDIT: Use urllib.parse for Python 3
from urllib.parse import quote_plus, unquote_plus

register = template.Library()

@register.filter
def cutppl(value, arg):
    
    arg = "&Ppl" + arg
    return value.replace(arg, '')

@register.filter
def get_list(dictionary, key):
    return dictionary.getlist(key)

@register.filter
def addstr(value, arg):
    return value.add(arg)

@register.filter
def strsplit(value):
    if value:
        if isinstance(value, str):
            return [v.strip() for v in value.split(',') if v.strip()]
        elif isinstance(value, list) or isinstance(value, tuple) or hasattr(value, '__iter__'):
            return [str(v).strip() for v in value if str(v).strip()]
    return []

@register.filter
def geviert(value):
    return value.replace('-', '–')

@register.simple_tag(takes_context=True)
def add_filter_param(context, **new_params_kwargs):
    """
    Adds or updates one or more parameter values in the current request's GET query string.
    For each parameter provided:
      - If the parameter name is 'dat_von' or 'dat_bis', it sets/replaces the current value.
      - Otherwise (for other filters), it appends the new value if not already present for that parameter.
    Excludes the 'page' parameter to reset pagination when filters change.
    """
    # Get a mutable copy of the current GET parameters
    query_dict = context['request'].GET.copy()
    
    # Remove the 'page' parameter to reset pagination when adding/changing a filter
    if 'page' in query_dict:
        del query_dict['page']
    
    # Define parameters that should always set/replace their value (single-value logic)
    single_value_params = ['dat_von', 'dat_bis']

    for param_name, param_value in new_params_kwargs.items():
        new_value_str = str(param_value)
        
        if param_name in single_value_params:
            # For 'dat_von' and 'dat_bis', set the value, replacing any existing one(s)
            query_dict[param_name] = new_value_str
        else:
            # For other parameters, maintain original logic:
            # append the new value if it's not already in the list for this parameter.
            current_values = query_dict.getlist(param_name)
            if new_value_str not in current_values:
                query_dict.appendlist(param_name, new_value_str)
            # If the value is already present for this multi-value param, do nothing.

    # Return the encoded query string (without the leading '?')
    return query_dict.urlencode()

# @register.filter
# def strdel(value, arg):
#     qs = arg
#     print(qs)
#     stri = ", " + value
#     print(stri)
#     stri2 = value + ", "
#     print(stri2)
#     if stri in qs:
#         print("stri")
#         # stri = "q-=" + stri
#         return stri
#     elif stri2 in qs:
#         print("stri2")
#         #stri2 = "q-=" + stri2
#         return stri2
#     # else:
#     #     test = "q-="
#     #     stri3 = test + "&q=" + value
#     #     return stri3

# Optional: Add a tag to remove a specific filter value (useful for filter tags)
@register.simple_tag(takes_context=True)
def remove_filter_param_value(context, param_name, param_value_to_remove):
    """
    Removes a specific value from a multi-valued parameter in the query string.
    """
    query_dict = context['request'].GET.copy()
    values = query_dict.getlist(param_name)
    value_to_remove_str = str(param_value_to_remove)

    # Create a new list excluding the value to remove
    new_values = [v for v in values if v != value_to_remove_str]

    if not new_values:
        # If the list is empty, remove the parameter entirely
        if param_name in query_dict:
            del query_dict[param_name]
    else:
        # Otherwise, update the parameter with the new list
        query_dict.setlist(param_name, new_values)

    return query_dict.urlencode()