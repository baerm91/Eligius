from .models import *

FILTER_PARAMETERS = {
    'default': {  # Standardfilter, wenn 'unbestimmt' nicht gesetzt ist
        'q': {
            'fields': ['invnr', 'Typ__titel', 'Typ__muenztyptitel', 'Typ__rvleg', 'Typ__avleg'],
            'filter': 'icontains',
            'display_name': 'Suche',
            'model': None,
            'display_field': None,
        },
        'avleg': {
            'fields': ['Typ__avleg'],
            'filter': 'icontains',
            'display_name': 'Av.-Legende',
            'model': None,
            'display_field': None,
        },
        'rvleg': {
            'fields': ['Typ__rvleg'],
            'filter': 'icontains',
            'display_name': 'Rv.-Legende',
            'model': None,
            'display_field': None,
        },
        # 'Muenzstaette': {
        #     'fields': ['Typ__Mzstaette__name'],
        #     'filter': 'exact',
        #     'display_name': 'Münzstätte',
        #     'model': Mzstaette,
        #     'display_field': 'name',
        # },
        'Muenzstaette': {
            'fields': ['Typ__Mzstaette__name'],      #  ←  weiter per ID filtern
            'filter': 'exact',
            'display_name': 'Münzstätte',
            'model': Mzstaette,
            'display_field': 'name',

            # NEU für Facet-API
            'facet_field': 'Typ__Mzstaette__name',   # Klartext für Gruppierung
            'id_field':    'Typ__Mzstaette_id',      # ID in der Antwort
        },
        'Muenzstand': {
            'fields': ['Typ__Muenzstand__name'],
            'filter': 'exact',
            'display_name': 'Münzstand',
            'model': Muenzstand,
            'display_field': 'name',
        },
        'Reichskreis': {
            'fields': ['Typ__Reichskreis__name'],
            'filter': 'exact',
            'display_name': 'Reichskreis',
            'model': Reichskreis,
            'display_field': 'name',
        },
        'region': {
            'fields': ['Typ__Mzstaette__region__name'],
            'filter': 'exact',
            'display_name': 'Region',
            'model': Region,
            'display_field': 'name',
        },
        'num': {
            'fields': ['Typ__Ref__mztyp_ref__nummer'],
            'filter': 'in',
            'display_name': 'Nummer',
            'model': None,
            'display_field': None,
        },
        # 'Nominal': {
        #     'fields': ['Typ__Nominal__name'],
        #     'filter': 'icontains',
        #     'display_name': 'Nominal',
        #     'model': Nominal,
        #     'display_field': 'name',
        # },
        # -----------------------------  DEFAULT ------------------------------
        'Nominal': {                            # ❶  Name-Suche bleibt
            'fields':        ['Typ__Nominal__name'],
            'filter':        'exact',
            'display_name':  'Nominal',
            'model':         Nominal,
            'display_field': 'name',
        },
        'Nominal_id': {                         # ❷  ID-Filter für Dropdown
            'fields':        ['Typ__Nominal_id'],
            'filter':        'in',
            # display-Infos braucht das Backend hier nicht
            'facet_field':   'Typ__Nominal__name',
            'id_field':      'Typ__Nominal_id',
        },
        'material': {
            'fields': ['Typ__Metall__name'],
            'filter': 'icontains',
            'display_name': 'Material',
            'model': Metall,
            'display_field': 'name',
        },
        'sek_merk': {                                  #  Sekundäre Merkmale
            'fields': ['sekundaere_Merkmale__name'],
            'filter': 'icontains',
            'display_name': 'Sekundäre Merkmale',
            'model': Sek_Merkmale,
            'display_field': 'name',

            'facet_field': 'sekundaere_Merkmale__name',
        },
        # 'sek_merk': {
        #     'fields': ['sekundaere_Merkmale__name'],
        #     'filter': 'icontains',
        #     'display_name': 'Sekundäre Merkmale',
        #     'model': Sek_Merkmale,
        #     'display_field': 'name',
        # },
        # 'her_merk': {
        #     'fields': ['Herstellungsmerkmale__name'],
        #     'filter': 'icontains',
        #     'display_name': 'Herstellungsmerkmale',
        #     'model': Herstellungsmerkmale,
        #     'display_field': 'name',
        # },
        'her_merk': {                                 #  Herstellungsmerkmale
            # zum Filtern weiterhin der Name  (wenn dir das reicht)
            'fields': ['Herstellungsmerkmale__name'],
            'filter': 'icontains',
            'display_name': 'Herstellungsmerkmale',
            'model': Herstellungsmerkmale,
            'display_field': 'name',

            # Facet-spezifisch  (damit facet_api weiß, was sie zählen muss)
            'facet_field': 'Herstellungsmerkmale__name',   # gruppieren nach Namen
            # kein id_field nötig → Name wird zurückgeliefert
        },
        'Slg': {
            # bleibt bei der ID – das Browser-Filtering braucht das
            'fields': ['Slg_id'],
            'filter': 'exact',
            'display_name': 'Sammlung',
            'model': Slg,
            'display_field': 'name',

            # zusätzlich NUR für Facets
            'facet_field': 'Slg__name',   # <-- Klartext für Gruppierung
            'id_field':    'Slg_id',      # <-- ID für Rückgabe
        },
        'SlgTeil': {
            'fields': ['SlgTeil_id'],
            'filter': 'exact',
            'display_name': 'Sammlungsteil',
            'model': SlgTeil,
            'display_field': 'name',

            'facet_field': 'SlgTeil__name',
            'id_field':    'SlgTeil_id',
        },
        'Paket': {
            'fields': ['pakete__id'],
            'filter': 'exact',
            'display_name': 'Paket',
            'model': Paket,
            'display_field': 'oeffentlicher_titel',
        },
        'Ref': {
            'fields': ['Typ__Ref__abk'],
            'filter': 'exact',
            'display_name': 'Referenz',
            'model': Ref,
            'display_field': 'abk',
        },
        'coin_type': {
            'fields': ['Typ_id'],
            'filter': 'in',
            'display_name': 'Münztyp',
            'facet_field': 'Typ__nummer',
            'id_field': 'Typ_id',
        },
        'av_bildtyp': {
            'fields': ['Typ__av_bildtyp_id'],
            'filter': 'exact',
            'display_name': 'Av.-Bildtyp',
            'model': AvBildtyp,
            'display_field': 'name',
            'facet_field': 'Typ__av_bildtyp__name',
            'id_field':    'Typ__av_bildtyp_id',
        },
        'av_beizeichen': {
            'fields': ['Typ__av_beizeichen_id'],
            'filter': 'exact',
            'display_name': 'Av.-Beizeichen',
            'model': AvBeizeichen,
            'display_field': 'name',
        },
        'av_schlagwort': {
            'fields': ['Typ__av_bildtyp__schlagworte__name'],
            'filter': 'exact',
            'display_name': 'Av.-Schlagwort',
            'model': Schlagwort,
            'display_field': 'name',
        },
        'rv_bildtyp': {
            'fields': ['Typ__rv_bildtyp_id'],
            'filter': 'exact',
            'display_name': 'Rv.-Bildtyp',
            'model': RvBildtyp,
            'display_field': 'name',
            'facet_field': 'Typ__rv_bildtyp__name',
            'id_field':    'Typ__rv_bildtyp_id',
        },
        'rv_beizeichen': {
            'fields': ['Typ__rv_beizeichen_id'],
            'filter': 'exact',
            'display_name': 'Rv.-Beizeichen',
            'model': RvBeizeichen,
            'display_field': 'name',
        },
        'rv_schlagwort': {
            'fields': ['Typ__rv_bildtyp__schlagworte__name'],
            'filter': 'exact',
            'display_name': 'Rv.-Schlagwort',
            'model': Schlagwort,
            'display_field': 'name',
        },
        'obj_type': {
            'fields': ['Objekttyp_id', 'Typ__Objekttyp_id'],
            'filter': 'exact',
            'display_name': 'Objekttyp',
            'model': Objekttyp,
            'display_field': 'name',
        },
        'dat_von': {
            'fields': ['Typ__dat_von'],
            'filter': 'gte',
            'display_name': 'Datierung von',
            'model': None,
            'display_field': None,
        },
        'dat_bis': {
            'fields': ['Typ__dat_bis'],
            'filter': 'lte',
            'display_name': 'Datierung bis',
            'model': None,
            'display_field': None,
        },
        'Praegeherren': {
            'facet_field': 'Typ__mztyp_person__idfk_Person__name',
            'id_field': 'Typ__mztyp_person__idfk_Person_id',
            'fields': ['Typ__mztyp_person__idfk_Person__name'],
            'filter': 'exact',
            'display_name': 'Prägeherr/-in',
            'person_function_ids': [1, 6, 7],  # Spezifische Funktionen für Prägeherren
            'appears_on_rev': None  # Keine Einschränkung auf Vorder- oder Rückseite
        },
        'Person': {
            'facet_field': 'Typ__mztyp_person__idfk_Person__name',
            'id_field': 'Typ__mztyp_person__idfk_Person_id',
            'fields': ['Typ__mztyp_person__idfk_Person__name'],
            'filter': 'exact',
            'display_name': 'Weitere Personen',
            'person_function_ids': None,  # Keine spezifischen IDs, sondern Ausschluss
            'exclude_function_ids': [1, 2, 6, 7],  # Ausschluss der IDs für Prägeherren und Dargestellte
            'appears_on_rev': None  # Keine Einschränkung auf Vorder- oder Rückseite
        },
        'Dargestellte_AV': {
            'facet_field': 'Typ__mztyp_person__idfk_Person__name',
            'id_field': 'Typ__mztyp_person__idfk_Person_id',
            'fields': ['Typ__mztyp_person__idfk_Person__name'],
            'filter': 'exact',
            'display_name': 'Av.-Dargestellte/r',
            'model': Person,
            'display_field': 'name',
            'person_function_ids': [2],  # Spezifische Funktion für Dargestellte
            'appears_on_rev': False  # Nur Vorderseite (Avers)
        },
        'Dargestellte_RV': {
            'facet_field': 'Typ__mztyp_person__idfk_Person__name',
            'id_field': 'Typ__mztyp_person__idfk_Person_id',
            'fields': ['Typ__mztyp_person__idfk_Person__name'],
            'filter': 'exact',
            'display_name': 'Rv.-Dargestellte/r',
            'model': Person,
            'display_field': 'name',
            'person_function_ids': [2],  # Spezifische Funktion für Dargestellte
            'appears_on_rev': True  # Nur Rückseite (Revers)
        },
        'Wappen': {
            # bei bestimmten Objekten läuft es über den Typ
            'fields'      : ['Typ__wappen__name'],
            'facet_field' : 'Typ__wappen__name',     # <-- wichtig für facet_api
            'id_field'    : 'Typ__wappen__id',
            'filter'      : 'exact',
            'display_name': 'Wappen',
            'model'       : Wappen,
            'display_field': 'name',
        },
    },
    'unbestimmt': {  # Filterparameter bei unbestimmten Münzen
        'avleg': {
            'fields': ['avleg'],
            'filter': 'icontains',
            'display_name': 'Av.-Legende',
            'model': None,
            'display_field': None,
        },
        'rvleg': {
            'fields': ['rvleg'],
            'filter': 'icontains',
            'display_name': 'Rv.-Legende',
            'model': None,
            'display_field': None,
        },
        'invnr': {
            'fields': ['invnr'],
            'filter': 'icontains',
            'display_name': 'Inventarnummer',
            'model': None,
            'display_field': None,
        },
        'Muenzstaette': {
            # --------- filtern ---------
            'fields':        ['idfk_Mzstaette__name'],     # direkt am Objekt
            'filter':        'exact',
            'display_name':  'Münzstätte',
            'model':         Mzstaette,
            'display_field': 'name',

            # --------- facetten ---------
            'facet_field': 'idfk_Mzstaette__name',
            'id_field':    'idfk_Mzstaette_id',
        },
        'Muenzstand': {
            'fields': ['Typ__Muenzstand__name'],
            'filter': 'exact',
            'display_name': 'Münzstand',
            'model': Muenzstand,
            'display_field': 'name',
        },
        'region': {
            'fields': ['Typ__Mzstaette__region__name'],
            'filter': 'exact',
            'display_name': 'Region',
            'model': Region,
            'display_field': 'name',
        },
        'q': {
            'fields': ['invnr', 'rvleg', 'avleg', 'titel'],
            'filter': 'icontains',
            'display_name': 'Suche',
            'model': None,
            'display_field': None,
        },
        'num': {
            'fields': ['idfk_Ref__obj_ref__nummer'],
            'filter': 'in',
            'display_name': 'Nummer',
            'model': None,
            'display_field': None,
        },
        # -----------------------------  DEFAULT ------------------------------
        'Nominal': {                            # ❶  Name-Suche bleibt
            'fields':        ['idfk_Nominal__name'],
            'filter':        'icontains',
            'display_name':  'Nominal',
            'model':         Nominal,
            'display_field': 'name',
        },
        'Nominal_id': {                         # ❷  ID-Filter für Dropdown
            'fields':        ['idfk_Nominal_id'],
            'filter':        'in',
            # display-Infos braucht das Backend hier nicht
            'facet_field':   'idfk_Nominal__name',
            'id_field':      'idfk_Nominal_id',
        },
        'material': {
            'fields': ['Metall__name'],
            'filter': 'icontains',
            'display_name': 'Material',
            'model': Metall,
            'display_field': 'name',
        },
        'sek_merk': {
            'fields': ['sekundaere_Merkmale__name'],
            'filter': 'icontains',
            'display_name': 'Sekundäre Merkmale',
            'model': Sek_Merkmale,
            'display_field': 'name',
            'facet_field': 'sekundaere_Merkmale__name',
        },
        'her_merk': {
            'fields': ['Herstellungsmerkmale__name'],      # liegt auch direkt am Obj
            'filter': 'icontains',
            'display_name': 'Herstellungsmerkmale',
            'model': Herstellungsmerkmale,
            'display_field': 'name',
            'facet_field': 'Herstellungsmerkmale__name',
        },
        'Slg': {
            # bleibt bei der ID – das Browser-Filtering braucht das
            'fields': ['Slg_id'],
            'filter': 'exact',
            'display_name': 'Sammlung',
            'model': Slg,
            'display_field': 'name',

            # zusätzlich NUR für Facets
            'facet_field': 'Slg__name',   # <-- Klartext für Gruppierung
            'id_field':    'Slg_id',      # <-- ID für Rückgabe
        },
        'SlgTeil': {
            'fields': ['SlgTeil_id'],
            'filter': 'exact',
            'display_name': 'Sammlungsteil',
            'model': SlgTeil,
            'display_field': 'name',

            'facet_field': 'SlgTeil__name',
            'id_field':    'SlgTeil_id',
        },
        'Paket': {
            'fields': ['pakete__id'],
            'filter': 'exact',
            'display_name': 'Paket',
            'model': Paket,
            'display_field': 'oeffentlicher_titel',
        },
        'Ref': {
            'fields': ['idfk_Ref__abk'],
            'filter': 'exact',
            'display_name': 'Referenz',
            'model': Ref,
            'display_field': 'abk',
        },
        'coin_type': {
            'fields': ['Typ_id'],
            'filter': 'in',
            'display_name': 'Münztyp',
            'facet_field': 'Typ__nummer',
            'id_field': 'Typ_id',
        },
        # 'av_bildtyp': {
        #     'fields': ['Typ__av_bildtyp_id'],
        #     'filter': 'exact',
        #     'display_name': 'Av.-Bildtyp',
        #     'model': AvBildtyp,
        #     'display_field': 'name',
        #     'facet_field': 'Typ__av_bildtyp__name',
        #     'id_field':    'Typ__av_bildtyp_id',
        # },
        'av_bildtyp': {
            'fields': ['av_bildtyp_id'],
            'filter': 'exact',
            'display_name': 'Av.-Bildtyp',
            'model': AvBildtyp,
            'display_field': 'name',
            'facet_field': 'av_bildtyp__name',
            'id_field':    'av_bildtyp_id',
        },
        'av_beizeichen': {
            'fields': ['av_beizeichen_id'],
            'filter': 'exact',
            'display_name': 'Av.-Beizeichen',
            'model': AvBeizeichen,
            'display_field': 'name',
        },
        'av_schlagwort': {
            'fields': ['av_bildtyp__schlagworte__name'],
            'filter': 'exact',
            'display_name': 'Av.-Schlagwort',
            'model': Schlagwort,
            'display_field': 'name',
        },
        'rv_bildtyp': {
            'fields': ['rv_bildtyp_id'],
            'filter': 'exact',
            'display_name': 'Rv.-Bildtyp',
            'model': RvBildtyp,
            'display_field': 'name',
            'facet_field': 'rv_bildtyp__name',
            'id_field':    'rv_bildtyp_id',
        },
        'rv_beizeichen': {
            'fields': ['rv_beizeichen_id'],
            'filter': 'exact',
            'display_name': 'Rv.-Beizeichen',
            'model': RvBeizeichen,
            'display_field': 'name',
        },
        'rv_schlagwort': {
            'fields': ['rv_bildtyp__schlagworte__name'],
            'filter': 'exact',
            'display_name': 'Rv.-Schlagwort',
            'model': Schlagwort,
            'display_field': 'name',
        },
        'obj_type': {
            'fields': ['Objekttyp_id'],
            'filter': 'in',
            'display_name': 'Objekttyp',
            'model': Objekttyp,
            'display_field': 'name',
        },
        'dat_von': {
            'fields': ['dat_von'],
            'filter': 'gte',
            'display_name': 'Datierung von',
            'model': None,
            'display_field': None,
        },
        'dat_bis': {
            'fields': ['dat_bis'],
            'filter': 'lte',
            'display_name': 'Datierung bis',
            'model': None,
            'display_field': None,
        },
        'Praegeherren': {
            'facet_field'        : 'obj_person__idfk_Person__name',
            'id_field'           : 'obj_person__idfk_Person_id',
            'fields'             : ['obj_person__idfk_Person__name'],
            'filter'             : 'exact',
            'display_name'       : 'Prägeherr/-in',
            'person_function_ids': [1, 6, 7],        #  <-- NEU
            'appears_on_rev'     : None,             #  <-- NEU
        },
        'Person': {
            'facet_field'        : 'obj_person__idfk_Person__name',
            'id_field'           : 'obj_person__idfk_Person_id',
            'fields'             : ['obj_person__idfk_Person__name'],
            'filter'             : 'exact',
            'display_name'       : 'Weitere Personen',
            'exclude_function_ids': [1, 2, 6, 7],    #  <-- NEU
            'appears_on_rev'      : None,            #  <-- NEU
        },
        'Dargestellte_AV': {
            'facet_field'        : 'obj_person__idfk_Person__name',
            'id_field'           : 'obj_person__idfk_Person_id',
            'fields'             : ['obj_person__idfk_Person__name'],
            'filter'             : 'exact',
            'display_name'       : 'Av.-Dargestellte/r',
            'person_function_ids': [2],              #  <-- NEU
            'appears_on_rev'     : False,            #  <-- NEU  (Avers)
        },
        'Dargestellte_RV': {
            'facet_field'        : 'obj_person__idfk_Person__name',
            'id_field'           : 'obj_person__idfk_Person_id',
            'fields'             : ['obj_person__idfk_Person__name'],
            'filter'             : 'exact',
            'display_name'       : 'Rv.-Dargestellte/r',
            'person_function_ids': [2],              #  <-- NEU
            'appears_on_rev'     : True,             #  <-- NEU  (Revers)
        },
    },
    # Optional: Weitere Kontexte hinzufügen...
}