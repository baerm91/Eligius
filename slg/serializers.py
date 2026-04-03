from django.shortcuts import render
from rest_framework import serializers
from .models import *
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _


class MzstaettenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mzstaette
        fields = ['id', 'name', 'name_nom_id']

class SchlagwortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schlagwort
        fields = ['id', 'name']

class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name', 'name_nom_id']

# 1. Basis-Serializer ohne Abhängigkeiten
class SlgKategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlgKategorie
        fields = ['id', 'name']

# 2. Serializer mit einfachen Abhängigkeiten
class SlgSerializer(serializers.ModelSerializer):
    kategorie = SlgKategorieSerializer(read_only=True)
    absolute_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Slg
        fields = ['id', 'name', 'beschreibung', 'cover', 'kategorie', 'absolute_url']

    def get_absolute_url(self, obj):
        return obj.get_absolute_url()

class SlgTeilSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlgTeil
        fields = ['id', 'name',]

class AvBildtypSerializer(serializers.ModelSerializer):
    schlagworte = SchlagwortSerializer(many=True, read_only=True)

    class Meta:
        model = AvBildtyp
        fields = ['id', 'name', 'abk', 'schlagworte']

class RvBildtypSerializer(serializers.ModelSerializer):
    class Meta:
        model = RvBildtyp
        fields = ['id', 'name']

class MuenzstandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Muenzstand
        fields = ['id', 'name']

class AvBeizeichenSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvBeizeichen
        fields = ['id', 'name']

class AvOffizinSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvOffizin
        fields = ['id', 'name']

class RvBeizeichenSerializer(serializers.ModelSerializer):
    class Meta:
        model = RvBeizeichen
        fields = ['id', 'name']

class RvOffizinSerializer(serializers.ModelSerializer):
    class Meta:
        model = RvOffizin
        fields = ['id', 'name']

# 3. Komplexere Serializer
class ObjSerializer(serializers.ModelSerializer):
    idfk_Mzstaette = MzstaettenSerializer(read_only=True)
    Slg = SlgSerializer(read_only=True)
    SlgTeil = SlgTeilSerializer(read_only=True)

    class Meta:
        model = Obj
        fields = '__all__'

class MetallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Metall
        fields = ['id', 'name']

class NominalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Nominal
        fields = ['id', 'name', 'name_nom_id']

class WorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workflow
        fields = ['id', 'name', 'reihenfolge']

class TypSerializer(serializers.ModelSerializer):
    Metall = MetallSerializer(read_only=True)
    Nominal = NominalSerializer(read_only=True)
    workflow = WorkflowSerializer(read_only=True)
    
    class Meta:
        model = Muenztyp
        fields = ['id', 'muenztyptitel', 'titel', 'dat_verb', 'dat_von', 'dat_bis', 'Metall', 'Nominal', 'workflow']

class ObjInventorySerializer(serializers.ModelSerializer):
    Typ = TypSerializer(read_only=True)
    workflow = WorkflowSerializer(read_only=True)

    class Meta:
        model = Obj
        fields = ['id', 'invnr', 'Typ', 'TempTyp', 'durchmesser', 'gewicht', 'stempelstellung', 'workflow']

class ObjInventoryUpdateSerializer(serializers.ModelSerializer):
    Typ = serializers.PrimaryKeyRelatedField(
        queryset=Muenztyp.objects.all(),
        allow_null=True,
        required=False
    )

    class Meta:
        model = Obj
        fields = ['Typ']

class HerstellungsmerkmaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Herstellungsmerkmale
        fields = ['id', 'name']

class Sek_MerkmaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sek_Merkmale
        fields = ['id', 'name']

class ObjDetailSerializer(serializers.ModelSerializer):
    """Erweiterter Serializer für Objekt-Details mit allen gewünschten Feldern"""
    idfk_Muenzstand = MuenzstandSerializer(read_only=True)
    idfk_Nominal = NominalSerializer(read_only=True)
    idfk_Mzstaette = MzstaettenSerializer(read_only=True)
    av_bildtyp = AvBildtypSerializer(read_only=True)
    av_beizeichen = AvBeizeichenSerializer(read_only=True)
    av_offizin = AvOffizinSerializer(read_only=True)
    rv_bildtyp = RvBildtypSerializer(read_only=True)
    rv_beizeichen = RvBeizeichenSerializer(read_only=True)
    rv_offizin = RvOffizinSerializer(read_only=True)
    Herstellungsmerkmale = HerstellungsmerkmaleSerializer(many=True, read_only=True)
    sekundaere_Merkmale = Sek_MerkmaleSerializer(many=True, read_only=True)
    Typ = TypSerializer(read_only=True)
    workflow = WorkflowSerializer(read_only=True)
    typ_personen_mit_funktion = serializers.SerializerMethodField()

    class Meta:
        model = Obj
        fields = [
            'id', 'invnr', 'titel', 'idfk_Muenzstand', 'idfk_Nominal', 'idfk_Mzstaette',
            'dat_von', 'dat_bis', 'dat_verb', 'avleg', 'av_bildtyp', 'av_beizeichen', 'av_offizin',
            'rvleg', 'rv_bildtyp', 'rv_beizeichen', 'rv_offizin',
            'TempTyp', 'gewicht', 'durchmesser', 'stempelstellung',
            'anmerkung', 'Herstellungsmerkmale', 'sekundaere_Merkmale', 'Typ', 'workflow', 'typ_personen_mit_funktion'
        ]

    def get_typ_personen_mit_funktion(self, obj):
        result = []
        if hasattr(obj, 'typ_personen_mit_funktion'):
            try:
                for person, funktion, appears_on_rev in obj.typ_personen_mit_funktion():
                    result.append({
                        'person': {'id': person.id, 'name': person.name},
                        'funktion': {'id': funktion.id, 'name': funktion.name},
                        'appears_on_rev': appears_on_rev
                    })
            except:
                pass
        return result

class ObjDetailUpdateSerializer(serializers.ModelSerializer):
    """Update-Serializer für Objekt-Bearbeitung - akzeptiert alle Felder"""
    
    class Meta:
        model = Obj
        fields = '__all__'
        read_only_fields = ['id', 'invnr', 'created_at', 'modified_at']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Alle Felder optional machen (außer read_only)
        for field_name, field in self.fields.items():
            if field_name not in self.Meta.read_only_fields:
                field.required = False
                field.allow_null = True
                if hasattr(field, 'allow_blank'):
                    field.allow_blank = True

class PersonFunktionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonFunktion
        fields = ['id', 'name']

class LatestObjSerializer(serializers.ModelSerializer):
    absolute_url = serializers.SerializerMethodField()
    Slg = SlgSerializer(read_only=True)
    get_bild_urls = serializers.SerializerMethodField()
    Typ = TypSerializer(read_only=True)
    typ_personen_mit_funktion = serializers.SerializerMethodField()
    av_schlagworte = serializers.SerializerMethodField()
    rv_schlagworte = serializers.SerializerMethodField()
    invnr = serializers.CharField()

    class Meta:
        model = Obj
        fields = [
            'id', 'absolute_url', 'Slg', 'get_bild_urls', 'Typ',
            'typ_personen_mit_funktion', 'av_schlagworte', 'rv_schlagworte', 'invnr'
        ]

    def get_absolute_url(self, obj):
        return obj.get_absolute_url()

    def get_get_bild_urls(self, obj):
        if hasattr(obj, 'get_bild_urls'):
            try:
                return obj.get_bild_urls()
            except:
                return {'thumbnail_av': '', 'thumbnail_rv': ''}
        return {'thumbnail_av': '', 'thumbnail_rv': ''}

    def get_typ_personen_mit_funktion(self, obj):
        result = []
        if hasattr(obj, 'typ_personen_mit_funktion'):
            try:
                for person, funktion, appears_on_rev in obj.typ_personen_mit_funktion():
                    result.append({
                        'person': {'id': person.id, 'name': person.name},
                        'funktion': {'id': funktion.id, 'name': funktion.name},
                        'appears_on_rev': appears_on_rev
                    })
            except:
                pass
        return result

    def get_av_schlagworte(self, obj):
        if hasattr(obj, 'av_schlagworte'):
            try:
                return [{'id': s.id, 'name': s.name} for s in obj.av_schlagworte()]
            except:
                return []
        return []

    def get_rv_schlagworte(self, obj):
        if hasattr(obj, 'rv_schlagworte'):
            try:
                return [{'id': s.id, 'name': s.name} for s in obj.rv_schlagworte()]
            except:
                return []
        return []

class MuenztypSerializer(serializers.ModelSerializer):
    av_bildtyp = AvBildtypSerializer(read_only=True)
    rv_bildtyp = RvBildtypSerializer(read_only=True)

    class Meta:
        model = Muenztyp
        fields = ['id', 'muenztyptitel', 'titel', 'link', 'av_bildtyp', 'rv_bildtyp', 'Ref', 'nummer']
        read_only_fields = ['id']

class CoinImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Obj
        fields = ['id']

    def get_images(self, obj):
        request = self.context.get('request')
        if not request:
            return {}
        
        av = request.query_params.get('av', 'false').lower() == 'true'
        rv = request.query_params.get('rv', 'false').lower() == 'true'
        thumbnail_av = request.query_params.get('thumbnail_av', 'false').lower() == 'true'
        thumbnail_rv = request.query_params.get('thumbnail_rv', 'false').lower() == 'true'

        images = obj.get_bild_urls()
        
        result = {}
        if av and 'av' in images:
            result['av'] = images['av']
        if rv and 'rv' in images:
            result['rv'] = images['rv']
        if thumbnail_av and 'thumbnail_av' in images:
            result['thumbnail_av'] = images['thumbnail_av']
        if thumbnail_rv and 'thumbnail_rv' in images:
            result['thumbnail_rv'] = images['thumbnail_rv']
        
        return result

class PersonCoinImageSerializer(serializers.ModelSerializer):
    coins = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = ['name', 'coins']

    def get_coins(self, person):
        mztyps_with_funktion_2 = Mztyp_Person.objects.filter(
            idfk_Person=person,
            idfk_PersonFunktion=2
        ).values_list('Mztyp', flat=True)

        objs = Obj.objects.filter(Typ__in=mztyps_with_funktion_2).distinct()
        return CoinImageSerializer(objs, many=True, context=self.context).data

class AvBildtypSerializer(serializers.ModelSerializer):
    schlagworte = SchlagwortSerializer(many=True, read_only=True)

    class Meta:
        model = AvBildtyp
        fields = ['id', 'name', 'abk', 'schlagworte']

class AvSchlagwortSerializer(serializers.ModelSerializer):
    schlagwort = SchlagwortSerializer()

    class Meta:
        model = AvBildtyp_Schlagwort
        fields = ['id', 'schlagwort']
        
class RefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ref
        fields = ['id', 'abk']

class ContextCoinSerializer(serializers.Serializer):
    id        = serializers.IntegerField()
    type_id   = serializers.IntegerField(source="Typ_id")
    nominal   = serializers.SerializerMethodField()
    card_html = serializers.SerializerMethodField()

    def get_nominal(self, obj):
        if obj.Typ and obj.Typ.Nominal:
            return obj.Typ.Nominal.name
        return None

    def get_card_html(self, obj):
        inner = render_to_string(
            "slg/partials/coin_preview_card.html",
            {"obj": obj, "light": True}
        )
        #  ➜  li‑Rahmen mit Data‑Attributen
        return (
            f'<li class="coin-item mb-2" '
            f'    data-id="{obj.id}" '
            f'    data-type-id="{obj.Typ_id}">'
            f'{inner}</li>'
        )

class KontextObjSerializer(serializers.Serializer):
    id    = serializers.IntegerField()
    thumb = serializers.URLField(allow_null=True)
    url   = serializers.URLField(allow_null=True)

class KontextRowSerializer(serializers.Serializer):
    name  = serializers.CharField()
    cells = serializers.DictField(child=KontextObjSerializer(allow_null=True, required=False))

class KontextStaetteSerializer(serializers.Serializer):
    name = serializers.CharField()
    rows = serializers.DictField(child=KontextRowSerializer())

class KontextMatrixSerializer(serializers.Serializer):
    nominale = serializers.DictField(child=serializers.CharField())
    staetten = serializers.DictField(child=KontextStaetteSerializer())
