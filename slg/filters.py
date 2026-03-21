from django.db.models import Q, F
from functools import reduce
from operator import or_, and_
from .filter_config import FILTER_PARAMETERS # Make sure this path is correct
# Add any other models or utilities these functions might need from .models
# from .models import Obj, Muenztyp, Person, Mztyp_Person, Obj_Person # Example

def is_valid_qparam(param):
   return param != '' and param is not None

# ... (Copy build_filters function here) ...
def build_filters(request, exclude_field=None):
    """
    Zentrale Funktion zum Aufbau der Filter-Logik.
    """
    context_key = 'unbestimmt' if request.GET.get('unbestimmt') else 'default'
    parameters = FILTER_PARAMETERS.get(context_key, {})

    general_filters = []
    praegeherren_filters = []
    dargestellte_av_filters = []
    dargestellte_rv_filters = []
    person_filters_list = [] # Renamed from person_filters to avoid confusion

    # Basis-Pfad für Personen-Beziehungen basierend auf context_key
    person_base = 'obj_person' if context_key == 'unbestimmt' else 'Typ__mztyp_person'

    for param, config_values in parameters.items(): # param is the key, config_values the dict
        if param == exclude_field or param == 'unbestimmt':
            continue

        # Personen-Filter mit spezifischen Bedingungen aus der Konfiguration
        if param in ['Praegeherren', 'Dargestellte_AV', 'Dargestellte_RV', 'Person']:
            for value in request.GET.getlist(param):
                if is_valid_qparam(value):
                    base_condition = Q(**{f'{person_base}__idfk_Person__name': value})
                    
                    condition_to_add = base_condition
                    # Apply specific conditions from config_values (which is parameters[param])
                    if config_values.get('person_function_ids'):
                        condition_to_add &= Q(**{f'{person_base}__idfk_PersonFunktion_id__in': config_values['person_function_ids']})
                    elif config_values.get('exclude_function_ids'):
                        condition_to_add &= ~Q(**{f'{person_base}__idfk_PersonFunktion_id__in': config_values['exclude_function_ids']})
                    
                    if config_values.get('appears_on_rev') is not None:
                        condition_to_add &= Q(**{f'{person_base}__appears_on_rev': config_values['appears_on_rev']})
                    
                    if param == 'Praegeherren':
                        praegeherren_filters.append(condition_to_add)
                    elif param == 'Dargestellte_AV':
                         # Special handling for Dargestellte_AV as per your original build_filters
                        av_specific_condition = (
                            base_condition &
                            Q(**{f'{person_base}__idfk_PersonFunktion_id': 2}) &
                            Q(**{f'{person_base}__appears_on_rev': False})
                        )
                        dargestellte_av_filters.append(av_specific_condition)
                    elif param == 'Dargestellte_RV':
                        dargestellte_rv_filters.append(condition_to_add)
                    elif param == 'Person':
                        person_filters_list.append(condition_to_add)
        else:
            # General filters (non-person filters)
            param_values_from_request = request.GET.getlist(param)
            if param_values_from_request: # Check if there are values for this param in request
                current_param_filters = []
                for value in param_values_from_request:
                    if is_valid_qparam(value):
                        # config_values here is the dictionary for the current param from FILTER_PARAMETERS
                        # e.g., {'fields': ['Typ__Nominal__name', 'idfk_Nominal__name'], 'filter': 'exact', ...}
                        field_q_objects = [
                            Q(**{f'{field}__{config_values["filter"]}': value})
                            for field in config_values['fields']
                        ]
                        if field_q_objects:
                            current_param_filters.append(reduce(or_, field_q_objects))
                if current_param_filters:
                     general_filters.append(reduce(or_, current_param_filters))


    # Datums-Filter ergänzen
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if exclude_field != 'date' and is_valid_qparam(date_from) and is_valid_qparam(date_to):
        if context_key == 'default': # Assuming 'default' means Typ is not null
            general_filters.append(
                Q(Typ__dat_von__lte=date_to) &
                Q(Typ__dat_bis__gte=date_from)
            )
        else: # 'unbestimmt', Typ is null
            general_filters.append(
                Q(dat_von__lte=date_to) &
                Q(dat_bis__gte=date_from)
            )

    person_filters_dict = {
        'praegeherren': praegeherren_filters,
        'dargestellte_av': dargestellte_av_filters,
        'dargestellte_rv': dargestellte_rv_filters,
        'person': person_filters_list, # Use the renamed list
    }

    return general_filters, person_filters_dict

# ... (Copy apply_filters function here) ...
def apply_filters(request, queryset, exclude_field=None, facet_context=False):
    general_filters, _ = build_filters(request, exclude_field) # person_filters_dict not directly used here

    for f in general_filters:
        queryset = queryset.filter(f)

    context_key = 'unbestimmt' if request.GET.get('unbestimmt') else 'default'
    person_base_path = 'obj_person' if context_key == 'unbestimmt' else 'Typ__mztyp_person'
    
    # This mapping should align with FILTER_PARAMETERS keys and logic in build_filters
    person_params_config = { 
        'Praegeherren': FILTER_PARAMETERS.get(context_key, {}).get('Praegeherren', {}),
        'Dargestellte_AV': FILTER_PARAMETERS.get(context_key, {}).get('Dargestellte_AV', {}),
        'Dargestellte_RV': FILTER_PARAMETERS.get(context_key, {}).get('Dargestellte_RV', {}),
        'Person': FILTER_PARAMETERS.get(context_key, {}).get('Person', {}),
    }

    for param_name, config in person_params_config.items():
        if param_name in request.GET and param_name != exclude_field:
            names_from_request = [name for name in request.GET.getlist(param_name) if is_valid_qparam(name)]
            if names_from_request:
                # Base filter always by name for the selected persons in this facet
                name_q = Q(**{f'{person_base_path}__idfk_Person__name__in': names_from_request})
                
                if facet_context: 
                    # In facet context for *other* facets, filter only by name for simplicity to get counts
                    queryset = queryset.filter(name_q)
                else:
                    # In normal list/API context, apply full specific conditions for this person facet
                    person_specific_q = name_q
                    
                    # Use conditions from FILTER_PARAMETERS for the current person_param_name
                    function_ids = config.get('person_function_ids')
                    exclude_ids = config.get('exclude_function_ids')
                    appears_on_rev = config.get('appears_on_rev')

                    if function_ids:
                        person_specific_q &= Q(**{f'{person_base_path}__idfk_PersonFunktion_id__in': function_ids})
                    elif exclude_ids:
                        person_specific_q &= ~Q(**{f'{person_base_path}__idfk_PersonFunktion_id__in': exclude_ids})

                    if appears_on_rev is not None:
                        person_specific_q &= Q(**{f'{person_base_path}__appears_on_rev': appears_on_rev})
                    
                    queryset = queryset.filter(person_specific_q)
    
    # distinct() should ideally be called at the very end by the caller of apply_filters if needed
    return queryset
