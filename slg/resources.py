# resources.py

from import_export import resources
from .models import *
from django.db.models import Q


from import_export.admin import ImportExportModelAdmin, ExportActionMixin, ImportExportActionModelAdmin
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

class ObjLSNOResource(resources.ModelResource):
    ObjWorklow = Field(attribute='workflow__name', column_name='ObjWorkflow')
    TypWorklow = Field(attribute='Typ__workflow__name', column_name='TypWorkflow')
    Slg__name = Field(attribute='Slg__name', column_name='Sammlung')
    SlgTeil__name = Field(attribute='SlgTeil__name', column_name='ObjAccession.Source')
    durchmesser = Field(attribute='durchmesser', column_name='Durchmesser in mm')
    gewicht = Field(attribute='gewicht', column_name='Gewicht in g')
    stempelstellung = Field(attribute='stempelstellung', column_name='Stempelstellung in h')
    faelschung = Field(attribute='faelschung', column_name='Fälschung?')
    Typ_unsicher = Field(attribute='Typ_unsicher', column_name='Typ_unsicher?')
    #Typ__muenztyptitel = Field(attribute='Typ__muenztyptitel', column_name='Zitat')
    #Typ__titel = Field(attribute='Typ__titel', column_name='Titel des Objektes')
    Typ__Herstellung__name = Field(attribute='Typ__Herstellung__name', column_name='Herstellung')
    Typ__Reichskreis__name = Field(attribute='Typ__Reichskreis__name', column_name='Reichskreis')
    Typ__Muenzstand__name = Field(attribute='Typ__Muenzstand__name', column_name='Münzstand')
    Typ__Nominal__name = Field(attribute='Typ__Nominal__name', column_name='Nominal')
    #Typ__Metall__name = Field(attribute='Typ__Metall__name', column_name='Metall')
    Typ__Mzstaette__name = Field(attribute='Typ__Mzstaette__name', column_name='Münzstätte')
    Typ__region__name = Field(attribute='Typ__region__name', column_name='Region')
    Typ__dat_von = Field(attribute='Typ__dat_von', column_name='Datierung von')
    Typ__dat_bis = Field(attribute='Typ__dat_bis', column_name='Datierung bis')
    Typ__dat_verb = Field(attribute='Typ__dat_verb', column_name='Datierung')
    Typ__avleg = Field(attribute='Typ__avleg', column_name='Av.-Leg.')
    Typ__av_bildtyp__name = Field(attribute='Typ__av_bildtyp__name', column_name='Av.-Beschreibung')
    Typ__av_beizeichen__name = Field(attribute='Typ__av_beizeichen__name', column_name='Av.-Beizeichen')
    #Typ__av_offizin__name = Field(attribute='Typ__av_offizin__name', column_name='Av.-Offizin')
    Typ__rvleg = Field(attribute='Typ__rvleg', column_name='Rv.-Leg.')
    Typ__rv_bildtyp__name = Field(attribute='Typ__rv_bildtyp__name', column_name='Rv.-Beschreibung')
    Typ__rv_beizeichen__name = Field(attribute='Typ__rv_beizeichen__name', column_name='Rv.-Beizeichen')
    #Typ__rv_offizin__name = Field(attribute='Typ__rv_offizin__name', column_name='Rv.-Offizin')
    #Konkordanzen = Field(column_name='Konkordanzen', attribute=None)  # Attribut ist None, da dies ein benutzerdefiniertes Feld ist
    Zitate = Field(column_name='Obj.Notes', attribute=None)  # Attribut ist None, da dies ein benutzerdefiniertes Feld ist
    Titel = Field(column_name='Titel', attribute=None)
    Bereich = Field(column_name='Bereich', attribute=None)
    Vorderseite = Field(column_name='Vorderseite', attribute=None)
    Rückseite = Field(column_name='Rückseite', attribute=None)

    maßnahmennr = Field(attribute='fund__maßnahmennr', column_name='Maßnahmen-Nr.')
    fundnummer = Field(attribute='fund__fundnummer', column_name='Fundnummer')
    fundnummerzusatz = Field(attribute='fund__fundnummerzusatz', column_name='Fundnummerzusatz')
    kistennr = Field(attribute='fund__kistennr', column_name='Kisten-Nr.')
    fundort = Field(attribute='fund__fundort', column_name='Fundort')
    parzelle = Field(attribute='fund__parzelle', column_name='Parzelle')
    fundstelle = Field(attribute='fund__fundstelle', column_name='Fundstelle')
    lm_von = Field(attribute='fund__lm_von', column_name='Laufmeter von')
    lm_bis = Field(attribute='fund__lm_bis', column_name='Laufmeter bis')
    niveautiefe_in_m_von = Field(attribute='fund__niveautiefe_in_m_von', column_name='Niveautiefe in m von')
    niveautiefe_in_m_bis = Field(attribute='fund__niveautiefe_in_m_bis', column_name='Niveautiefe in m bis')
    niveau = Field(attribute='fund__niveau', column_name='Niveau')
    vn = Field(attribute='fund__vn', column_name='von Norden',)
    vno = Field(attribute='fund__vno', column_name='von Nordosten',)
    vo = Field(attribute='fund__vo', column_name='von Osten',)
    vso = Field(attribute='fund__vso', column_name='von Südosten',)
    vs = Field(attribute='fund__vs', column_name='von Süden',)
    vsw = Field(attribute='fund__vsw', column_name='von Südwesten',)
    vw = Field(attribute='fund__vw', column_name='von Westen',)
    vnw = Field(attribute='fund__vnw', column_name='von Nordwesten',)
    schnitt = Field(attribute='fund__schnitt', column_name='Schnitt')
    bereichsbezeichnung = Field(attribute='fund__bereichsbezeichnung', column_name='Bereichsbezeichnung')
    sondage = Field(attribute='fund__sondage', column_name='Sondage')
    quadrant = Field(attribute='fund__quadrant', column_name='Quadrant')
    quadrantzusatz = Field(attribute='fund__quadrantzusatz', column_name='Quadrant-Zusatz')
    flaeche = Field(attribute='fund__flaeche', column_name='Fläche')
    se = Field(attribute='fund__se', column_name='Stratigraphische Einheit')
    stratum = Field(attribute='fund__stratum', column_name='Stratum')
    funddatum = Field(attribute='fund__funddatum', column_name='Funddatum')
    fundjahr = Field(attribute='fund__fundjahr', column_name='Fundjahr')
    # zusammen_gefundene_muenzen = models.ManyToManyField(attribute='fund__anmerkung', column_name='Zusammen gefundene Münzen')
    andere_materialien = Field(attribute='fund__andere_materialien', column_name='Sonstiges Fundmaterial')
    fundposition = Field(attribute='fund__fundposition', column_name='Fundposition')
    fundkontext = Field(attribute='fund__fundkontext', column_name='Fundkontext')
    anmerkung = Field(attribute='fund__anmerkung', column_name='Anmerkung')
    bearbeiter = Field(attribute='fund__bearbeiter', column_name='Fundzettel erfasst von')

    praegenherr = Field(column_name='Praegenherr', attribute=None)
    dargestellte_av = Field(column_name='Dargestellte (Avers)', attribute=None)
    dargestellte_rv = Field(column_name='Dargestellte (Revers)', attribute=None)
    muenzmeister = Field(column_name='Muenzmeister', attribute=None)

    

    def dehydrate_praegenherr(self, obj):
        return self.get_persons(obj, personfunktion=1)

    def dehydrate_dargestellte_av(self, obj):
        return self.get_persons(obj, personfunktion=2, appears_on_rev=False)

    def dehydrate_dargestellte_rv(self, obj):
        return self.get_persons(obj, personfunktion=2, appears_on_rev=True)

    def dehydrate_muenzmeister(self, obj):
        return self.get_persons(obj, personfunktion=3)

    def get_persons(self, obj, personfunktion, appears_on_rev=None):
        persons = set()
        
        mztyp_persons = Mztyp_Person.objects.filter(Mztyp=obj.Typ, idfk_PersonFunktion=personfunktion)
        obj_persons = Obj_Person.objects.filter(idfk_Obj=obj, idfk_PersonFunktion=personfunktion)

        if appears_on_rev is not None:
            mztyp_persons = mztyp_persons.filter(appears_on_rev=appears_on_rev)
            obj_persons = obj_persons.filter(appears_on_rev=appears_on_rev)

        for person in mztyp_persons:
            persons.add(person.idfk_Person.name)

        for person in obj_persons:
            persons.add(person.idfk_Person.name)

        return ', '.join(persons)
    
    class Meta:
        model = Obj
        fields = ('id', 'Bereich', 'invnr', 'Slg__name', 'SlgTeil__name', 'durchmesser', 'gewicht', 'stempelstellung',
                  'faelschung', 'Typ_unsicher', 'Zitate', 'ObjWorklow', 'TypWorklow', 'Typ__Herstellung__name',
                  'Typ__Reichskreis__name', 'Typ__Muenzstand__name', 'Typ__Nominal__name', 'Typ__Metall__name',
                  'Typ__Mzstaette__name', 'Typ__region__name', 'Typ__dat_von', 'Typ__dat_bis', 'Typ__dat_verb',
                  'praegenherr', 'dargestellte_av', 'dargestellte_rv', 'muenzmeister', 
                  'Titel', 'Vorderseite', 'Typ__avleg', 'Typ__av_bildtyp__name', 'Typ__av_beizeichen__name', 'Rückseite',
                  'Typ__rvleg', 'Typ__rv_bildtyp__name', 'Typ__rv_beizeichen__name', 'rv_offizin__name', 'maßnahmennr',
                  'fundnummer', 'fundnummerzusatz', 'kistennr', 'fundort', 'parzelle', 'fundstelle', 'lm_von', 'lm_bis',
                  'niveautiefe_in_m_von', 'niveautiefe_in_m_bis', 'niveau', 'vn', 'vno', 'vo', 'vso', 'vs', 'vsw', 'vw',
                  'vnw', 'schnitt', 'bereichsbezeichnung', 'sondage', 'quadrant', 'quadrantzusatz', 'flaeche', 'se',
                  'stratum', 'funddatum', 'fundjahr', 'andere_materialien', 'fundposition', 'fundkontext', 'anmerkung',
                  'bearbeiter', )
        export_order = fields
        name = "Export der Objekte"

    def get_queryset(self):
        return Obj.objects.filter(Q(Slg=6) | Q(Slg__name="Landessammlungen Niederösterreich"))
        # return Obj.objects.filter(Q(Slg=4) | Q(Slg__name="Landessammlungen Niederösterreich"))
    
    def dehydrate_Zitate(self, obj):
        if obj.Typ:
            konkordanz_list = [str(konkordanz) for konkordanz in obj.Typ.Konkordanz.all()]
            muenztyptitel = obj.Typ.muenztyptitel if obj.Typ.muenztyptitel else ''

            if konkordanz_list:
                konkordanz_str = '; '.join(konkordanz_list)
                return f"{muenztyptitel}; {konkordanz_str}"
            else:
                return muenztyptitel
        return ''
    # Titel für LSNÖ
    # def dehydrate_Titel(self, obj):
    #     if obj.Typ:
    #         nominal = obj.Typ.Nominal.name if obj.Typ.Nominal else 'Münze'
    #         typ_titel = obj.Typ.titel if obj.Typ.titel else ''
    #         if nominal and typ_titel:
    #             return f"{nominal} des {typ_titel}"
    #         elif typ_titel:
    #             return typ_titel
    #         else:
    #             return "Münze"
    #     else:
    #         nominal = obj.idfk_Nominal.name if obj.idfk_Nominal else 'Münze'
    #         titel = obj.titel if obj.titel else ''
    #         if nominal and titel:
    #             return f"{nominal} des {titel}"
    #         elif titel:
    #             return titel
    #         else:
    #             return "Münze"
    #     return ''

    # Titel ohne Nominal
    def dehydrate_Titel(self, obj):
        if obj.Typ:
            typ_titel = obj.Typ.titel if obj.Typ.titel else ''
            if typ_titel:
                return typ_titel
            else:
                return "Münze"
        else:
            titel = obj.titel if obj.titel else ''
            if titel:
                return titel
            else:
                return "Münze"
        return ''

    def dehydrate_Muenzstand(self, obj):
        if obj.Typ and hasattr(obj.Typ, 'Muenzstand__name'):
            return obj.Typ.Muenzstand__name
        else:
            # Wenn das obj selbst ein Attribut 'Muenzstand' hat
            return obj.idfk_Muenzstand.name if obj.idfk_Muenzstand else ''


    def dehydrate_Bereich(self, obj):
        metall = ''
        if obj.Typ:
            if obj.Typ.Metall:
                metall = obj.Typ.Metall.name
        else:
            metall = obj.Beschreibung if hasattr(obj, 'Beschreibung') else ''

        if metall == 'Gold':
            return 'RA-Münzen-Gold'
        elif metall == 'Silber':
            return 'RA-Münzen-Silber'
        else:
            return 'RA-Münzen-Buntmetall und Eisen'

    def dehydrate_Vorderseite(self, obj):
        if obj.Typ:
            avleg = obj.Typ.avleg if obj.Typ.avleg else ''
            bildtyp = obj.Typ.av_bildtyp.name if obj.Typ.av_bildtyp and hasattr(obj.Typ.av_bildtyp, 'name') else ''
            beizeichen = obj.Typ.av_beizeichen.name if obj.Typ.av_beizeichen and hasattr(obj.Typ.av_beizeichen, 'name') else ''
        else:
            avleg = obj.avleg if hasattr(obj, 'avleg') and obj.avleg else ''
            bildtyp = obj.av_bildtyp.name if hasattr(obj, 'av_bildtyp') and obj.av_bildtyp and hasattr(obj.av_bildtyp, 'name') else ''
            beizeichen = obj.av_beizeichen.name if hasattr(obj, 'av_beizeichen') and obj.av_beizeichen and hasattr(obj.av_beizeichen, 'name') else ''

        vorderseite_parts = []
        if avleg:
            vorderseite_parts.append(avleg)
        if bildtyp:
            vorderseite_parts.append(bildtyp)
        if beizeichen:
            vorderseite_parts.append(beizeichen)

        vorderseite = ". ".join(vorderseite_parts)
        return vorderseite.strip()


    def dehydrate_Rückseite(self, obj):
        if obj.Typ:
            rvleg = obj.Typ.rvleg if obj.Typ.rvleg else ''
            bildtyp = obj.Typ.rv_bildtyp.name if obj.Typ.rv_bildtyp and hasattr(obj.Typ.rv_bildtyp, 'name') else ''
            beizeichen = self.dehydrate_Typ__rv_beizeichen__name(obj)
        else:
            rvleg = obj.rvleg if hasattr(obj, 'rvleg') and obj.rvleg else ''
            bildtyp = obj.rv_bildtyp.name if hasattr(obj, 'rv_bildtyp') and obj.rv_bildtyp and hasattr(obj.rv_bildtyp, 'name') else ''
            beizeichen = obj.rv_beizeichen.name if hasattr(obj, 'rv_beizeichen') and obj.rv_beizeichen and hasattr(obj.rv_beizeichen, 'name') else ''

        rückseite_parts = []
        if rvleg:
            rückseite_parts.append(rvleg)
        if bildtyp:
            rückseite_parts.append(bildtyp)
        if beizeichen:
            rückseite_parts.append(beizeichen)

        rückseite = ". ".join(rückseite_parts)
        return rückseite.strip()

    def dehydrate_Typ__rv_beizeichen__name(self, obj):
        base_value = obj.Typ.rv_beizeichen.name if hasattr(obj.Typ, 'rv_beizeichen') and obj.Typ.rv_beizeichen else ''
        if hasattr(obj, 'rv_offizin') and obj.rv_offizin:
            return base_value.replace('?', obj.rv_offizin.name)
        return base_value


    def dehydrate_Typ__Herstellung__name(self, obj):
        if hasattr(obj, 'idfk_Herstellung') and obj.idfk_Herstellung:
            return obj.idfk_Herstellung
        elif hasattr(obj.Typ, 'Herstellung') and obj.Typ.Herstellung:
            return obj.Typ.Herstellung.name
        return ''
    
    def dehydrate_Typ__dat_von(self, obj):
        return obj.dat_von if hasattr(obj, 'dat_von') and obj.dat_von else (obj.Typ.dat_von if hasattr(obj.Typ, 'dat_von') else '')
    def dehydrate_Typ__dat_bis(self, obj):
        return obj.dat_bis if hasattr(obj, 'dat_bis') and obj.dat_bis else (obj.Typ.dat_bis if hasattr(obj.Typ, 'dat_bis') else '')
    def dehydrate_Typ__dat_verb(self, obj):
        return obj.dat_verb if hasattr(obj, 'dat_verb') and obj.dat_verb else (obj.Typ.dat_verb if hasattr(obj.Typ, 'dat_verb') else '')

    def dehydrate_Typ__Nominal__name(self, obj):
        if hasattr(obj, 'idfk_Nominal') and obj.idfk_Nominal:
            return obj.idfk_Nominal.name
        elif hasattr(obj.Typ, 'Nominal') and obj.Typ.Nominal:
            return obj.Typ.Nominal.name
        return ''
 