from django.shortcuts import render
from rest_framework import serializers
from .models import *
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.urls import reverse


class DisplayLabelSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        from slg.services.authority_display import display_label
        data = super().to_representation(instance)
        data['display_name'] = display_label(instance)
        return data


class MzstaettenSerializer(DisplayLabelSerializer):
    class Meta:
        model = Mzstaette
        fields = ['id', 'name', 'name_nom_id']

class SchlagwortSerializer(DisplayLabelSerializer):
    class Meta:
        model = Schlagwort
        fields = ['id', 'name']

class PersonSerializer(DisplayLabelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'name', 'name_nom_id']

# 1. Basis-Serializer ohne Abhängigkeiten
class SlgKategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlgKategorie
        fields = ['id', 'name']

# 2. Serializer mit einfachen Abhängigkeiten
class SlgSerializer(DisplayLabelSerializer):
    kategorie = SlgKategorieSerializer(read_only=True)
    absolute_url = serializers.SerializerMethodField()
    nomisma_rdf_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Slg
        fields = [
            'id', 'name', 'beschreibung', 'bildrechte_lizenz', 'cover',
            'kategorie', 'absolute_url', 'nomisma_export_erlaubt',
            'nomisma_rdf_url'
        ]

    def get_absolute_url(self, obj):
        return obj.get_absolute_url()

    def get_nomisma_rdf_url(self, obj):
        if not obj.nomisma_export_erlaubt:
            return None
        return reverse('collection_nomisma_rdf', kwargs={'id': obj.id})

class SlgTeilSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlgTeil
        fields = ['id', 'name',]

class AvBildtypSerializer(DisplayLabelSerializer):
    schlagworte = SchlagwortSerializer(many=True, read_only=True)

    class Meta:
        model = AvBildtyp
        fields = ['id', 'name', 'abk', 'schlagworte']

class RvBildtypSerializer(DisplayLabelSerializer):
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

class MetallSerializer(DisplayLabelSerializer):
    class Meta:
        model = Metall
        fields = ['id', 'name']

class NominalSerializer(DisplayLabelSerializer):
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
    rv_offizin = RvOffizinSerializer(read_only=True)

    class Meta:
        model = Obj
        fields = ['id', 'invnr', 'Typ', 'TempTyp', 'Typ_unsicher', 'durchmesser', 'gewicht', 'stempelstellung', 'workflow', 'rv_offizin']

class ObjInventoryUpdateSerializer(serializers.ModelSerializer):
    Typ = serializers.PrimaryKeyRelatedField(
        queryset=Muenztyp.objects.all(),
        allow_null=True,
        required=False
    )

    class Meta:
        model = Obj
        fields = ['Typ']

class HerstellungsmerkmaleSerializer(DisplayLabelSerializer):
    class Meta:
        model = Herstellungsmerkmale
        fields = ['id', 'name']

class Sek_MerkmaleSerializer(DisplayLabelSerializer):
    class Meta:
        model = Sek_Merkmale
        fields = ['id', 'name']

def _typ_personen(obj):
    """Personen des Münztyps; typ_personen_mit_funktion ist eine Property (Liste).

    Früher als Methode aufgerufen: der TypeError wurde von einem bare except
    verschluckt und die API lieferte immer [].
    """
    result = []
    for person, funktion, appears_on_rev in (getattr(obj, 'typ_personen_mit_funktion', None) or []):
        result.append({
            'person': {'id': getattr(person, 'id', None), 'name': person.name},
            'funktion': {'id': funktion.id, 'name': funktion.name},
            'appears_on_rev': appears_on_rev,
        })
    return result


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
        return _typ_personen(obj)

class ObjDetailUpdateSerializer(serializers.ModelSerializer):
    """Update-Serializer für Objekt-Bearbeitung.

    Nur beschreibende Felder sind per API schreibbar (explizite Allowlist statt
    ``'__all__'``). Verwaltungsfelder (Workflow-Status, Sammlungszuordnung,
    Pakete, Fälschungs-Kennzeichnung, Freigabe) dürfen nur Superuser ändern,
    damit z. B. die OAI-/Nomisma-Freigabe nicht per API umgangen werden kann.
    """

    PRIVILEGED_FIELDS = ['workflow', 'Slg', 'SlgTeil', 'pakete', 'faelschung', 'freigabe', 'fmid']
    READ_ONLY_FIELDS = ['id', 'invnr', 'created_at', 'modified_at']

    class Meta:
        model = Obj
        fields = [
            'id', 'invnr', 'created_at', 'modified_at',
            'Typ', 'Typ_unsicher', 'Untertyp', 'Untertyp_unsicher', 'TempTyp',
            'titel', 'Objekttyp', 'idfk_Muenzstand', 'idfk_Herstellung',
            'Herstellungsmerkmale', 'sekundaere_Merkmale',
            'idfk_Nominal', 'Metall', 'idfk_Mzstaette', 'region',
            'dat_von', 'dat_bis', 'dat_verb',
            'durchmesser', 'gewicht', 'stempelstellung', 'abnutzung',
            'avleg', 'avbeschr', 'av_bildtyp', 'av_beizeichen', 'av_offizin',
            'av_offizin_symbol', 'av_bildrand',
            'rvleg', 'rvbeschr', 'rv_bildtyp', 'rv_beizeichen', 'rv_offizin',
            'rv_offizin_symbol', 'rv_bildrand',
            'rand', 'anmerkung',
            'workflow', 'Slg', 'SlgTeil', 'pakete', 'faelschung', 'freigabe', 'fmid',
        ]
        read_only_fields = ['id', 'invnr', 'created_at', 'modified_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        privileged = bool(user and getattr(user, 'is_superuser', False))

        for field_name, field in self.fields.items():
            if field_name in self.READ_ONLY_FIELDS:
                continue
            if field_name in self.PRIVILEGED_FIELDS and not privileged:
                field.read_only = True
                continue
            # Alle schreibbaren Felder optional machen
            field.required = False
            if isinstance(field, serializers.ManyRelatedField):
                # M2M: leere Liste statt null (null führte zu TypeError/HTTP 500)
                field.allow_empty = True
                continue
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
        return obj.get_bild_urls() or {'thumbnail_av': '', 'thumbnail_rv': ''}

    def get_typ_personen_mit_funktion(self, obj):
        return _typ_personen(obj)

    def get_av_schlagworte(self, obj):
        # Property, keine Methode (früher obj.av_schlagworte() -> TypeError -> stets [])
        return [{'id': s.id, 'name': s.name} for s in (obj.av_schlagworte or [])]

    def get_rv_schlagworte(self, obj):
        return [{'id': s.id, 'name': s.name} for s in (obj.rv_schlagworte or [])]

class MuenztypSerializer(serializers.ModelSerializer):
    av_bildtyp = AvBildtypSerializer(read_only=True)
    rv_bildtyp = RvBildtypSerializer(read_only=True)

    class Meta:
        model = Muenztyp
        fields = ['id', 'muenztyptitel', 'titel', 'link', 'av_bildtyp', 'rv_bildtyp', 'Ref', 'nummer']
        read_only_fields = ['id']


class MuenztypFilterSerializer(serializers.ModelSerializer):
    """Serializer that maps Eligius Muenztyp fields to Concordia type_filter format."""
    prefLabel = serializers.CharField(source='muenztyptitel', default='')
    subject_base = serializers.URLField(source='link', default='')
    obv_legend = serializers.CharField(source='avleg', default='')
    rev_legend = serializers.CharField(source='rvleg', default='')
    desc_obv = serializers.CharField(source='avbeschr', default='')
    desc_rev = serializers.CharField(source='rvbeschr', default='')
    av_bildtyp = AvBildtypSerializer(read_only=True)
    rv_bildtyp = RvBildtypSerializer(read_only=True)
    hasDenomination = serializers.SerializerMethodField()
    hasMint = serializers.SerializerMethodField()
    mintMark = serializers.SerializerMethodField()
    officinaMark = serializers.SerializerMethodField()
    dargestellt_av_eligius = serializers.SerializerMethodField()
    hasStartDate = serializers.IntegerField(source='dat_von', default=None)
    hasEndDate = serializers.IntegerField(source='dat_bis', default=None)

    class Meta:
        model = Muenztyp
        fields = [
            'id', 'prefLabel', 'subject_base',
            'obv_legend', 'rev_legend', 'desc_obv', 'desc_rev',
            'av_bildtyp', 'rv_bildtyp',
            'hasDenomination', 'hasMint', 'mintMark', 'officinaMark',
            'dargestellt_av_eligius', 'hasStartDate', 'hasEndDate',
        ]

    def get_hasDenomination(self, obj):
        return obj.Nominal.name if obj.Nominal_id else ''

    def get_hasMint(self, obj):
        return obj.Mzstaette.name if obj.Mzstaette_id else ''

    def get_mintMark(self, obj):
        if obj.rv_beizeichen_id:
            return obj.rv_beizeichen.name
        return ''

    def get_officinaMark(self, obj):
        if obj.rv_offizin_symbol_id:
            return obj.rv_offizin_symbol.name
        return ''

    def get_dargestellt_av_eligius(self, obj):
        if hasattr(obj, '_dargestellt_names'):
            return obj._dargestellt_names or ''
        return ''

class CoinImageSerializer(serializers.ModelSerializer):
    IMAGE_KEYS = ('av', 'rv', 'thumbnail_av', 'thumbnail_rv')
    images = serializers.SerializerMethodField()

    class Meta:
        model = Obj
        fields = ['id', 'images']

    def get_images(self, obj):
        request = self.context.get('request')
        params = getattr(request, 'query_params', {}) if request else {}
        # Ohne Auswahl (?av=true usw.) alle Varianten liefern.
        if not any(key in params for key in self.IMAGE_KEYS):
            av = rv = thumbnail_av = thumbnail_rv = True
        else:
            av, rv, thumbnail_av, thumbnail_rv = (
                str(params.get(key, 'false')).lower() == 'true' for key in self.IMAGE_KEYS)

        images = obj.get_bild_urls() or {}
        
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
        # Eine Abfrage pro Person; Slg/SlgTeil für get_bild_urls() gleich mitladen.
        objs = Obj.objects.filter(
            Typ__mztyp_person__idfk_Person=person,
            Typ__mztyp_person__idfk_PersonFunktion_id=2,
        ).select_related('Slg', 'SlgTeil').distinct().order_by('pk')
        return CoinImageSerializer(objs, many=True, context=self.context).data

class AvBildtypSerializer(DisplayLabelSerializer):
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
