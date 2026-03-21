from django import forms
from django.forms import ModelForm, widgets
from .models import *
from django_select2.forms import Select2MultipleWidget, Select2Widget, ModelSelect2Widget
from crispy_forms.helper import FormHelper
from bootstrap_modal_forms.forms import BSModalForm


class ObjForm(BSModalForm):
    class Meta:
        model = Obj
        fields = ['invnr', 'titel', 'idfk_Muenzstand', 'idfk_Herstellung', 'Slg', 'idfk_Nominal', 'Metall', 'idfk_Mzstaette', 'region', 'dat_von', 'dat_bis', 'dat_verb', 'durchmesser', 'gewicht', 'stempelstellung', 'anmerkung']

class ObjUpdateForm(BSModalForm):
    class Meta:
        model = Obj
        fields = ['invnr', 'titel', 'idfk_Muenzstand', 'idfk_Herstellung', 'Slg', 'idfk_Nominal', 'Metall', 'idfk_Mzstaette', 'region', 'dat_von', 'dat_bis', 'dat_verb', 'durchmesser', 'gewicht', 'stempelstellung', 'anmerkung']

class SearchForm(ModelForm):
    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.fields['idfk_Nominal'].widget.attrs['placeholder'] = 'special'
    #     self.fields['idfk_Ref'].widget.attrs.update(size='40')

    class Meta:
        model = Obj
        fields = [
        'idfk_Nominal', 'idfk_Ref'
        ]
        widgets = {
            #'idfk_Mzstaette': Select2MultipleWidget,
            #'Ppl': Select2MultipleWidget,
            'idfk_Nominal': Select2MultipleWidget,
            'idfk_Ref': Select2MultipleWidget
        }

class PersonenUpdateForm(forms.ModelForm):
    class Meta:
        model = Obj_Person
        fields = '__all__'
        

class DetailUpdateForm(forms.ModelForm):
    class Meta:
        model = Obj
        fields = '__all__'
        exclude = ['Ppl']
        # fields = 'titel', 'dat_verb', 'anmerkung', 'freigabe'
        widgets = {
            # 'link': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # # 'idfk_Muenzstand': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # # 'idfk_Herstellung': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'nummer': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # # 'Slg': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # # 'idfk_Nominal': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Ref': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'variante': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Mzstaette': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'region': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'dat_verb': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'dat_von': forms.NumberInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'dat_bis': forms.NumberInput(attrs={'class':'form-control',}),
            # 'durchmesser': forms.NumberInput(attrs={'class':'form-control',}),
            # 'gewicht': forms.NumberInput(attrs={'class':'form-control',}),
            # 'stempelstellung': forms.NumberInput(attrs={'class':'form-control',}),
            # 'av_bildtyp': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            'avleg': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'rv_bildtyp': MyWidget,
            'rvleg': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'anmerkung': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Ref': forms.SelectMultiple(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
        }

class RefUpdateForm(forms.ModelForm):
    class Meta:
        model = Obj_Ref
        fields = '__all__'
        exclude = ()
                # fields = 'titel', 'dat_verb', 'anmerkung', 'freigabe'
        widgets = {
            'link': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Muenzstand': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Herstellung': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            'nummer': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'Slg': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Nominal': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            'idfk_Ref': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            'variante': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'invnr': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Muenzstand': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Herstellung': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'titel': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'Slg': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Nominal': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'Metall': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'faelschung': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Mzstaette': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'region': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'dat_verb': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'dat_von': forms.NumberInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'dat_bis': forms.NumberInput(attrs={'class':'form-control',}),
            # 'durchmesser': forms.NumberInput(attrs={'class':'form-control',}),
            # 'gewicht': forms.NumberInput(attrs={'class':'form-control',}),
            # 'stempelstellung': forms.NumberInput(attrs={'class':'form-control',}),
            # 'av_bildtyp': forms.Select(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            #'avleg': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'rv_bildtyp': MyWidget,
            #'rvleg': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'anmerkung': forms.TextInput(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
            # 'idfk_Ref': forms.SelectMultiple(attrs={'class':'form-control', 'cols': 80, 'rows': 10}),
        }
        
        
        #fields = '__all__'
    # invnr = forms.CharField(max_length=20, verbose_name='Inv.-Nr.')
    # freigabe = forms.BooleanField(verbose_name='Freigabe')
    # idfk_Muenzstand = forms.ForeignKey('Muenzstand', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Münzstand')
    # idfk_Herstellung = forms.ForeignKey('Herstellung', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Herstellung')
    # titel = forms.CharField(max_length=200, blank=True, null=True, verbose_name='Titel')
    # SlgTeil = forms.ForeignKey('SlgTeil', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Sammlungsteil')
    # Slg = forms.ForeignKey('Slg', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Sammlung')
    # idfk_Nominal = forms.ForeignKey('Nominal', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Nominal')
    # Metall = forms.ForeignKey('Metall', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Metall')
    # faelschung = forms.ForeignKey('Faelschung', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Fälschung')
    # idfk_Mzstaette = forms.ForeignKey('Mzstaette', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Münzstätte')
    # region = forms.ForeignKey('Region', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='Region')
    # Ppl = forms.ManyToManyField('Person', through='Obj_Person', verbose_name = ("Person"))
    # idfk_Ref = forms.ManyToManyField('Ref', through='Obj_Ref', verbose_name = ("Referenz"))
    # dat_von = forms.IntegerField(blank=True, null=True, verbose_name='Datierung von')
    # dat_bis = forms.IntegerField(blank=True, null=True, verbose_name='Datierung bis')
    # dat_verb = forms.CharField(max_length=100, blank=True, null=True, verbose_name='Datierung verbale')
    # durchmesser = forms.DecimalField(blank=True, null=True, verbose_name='Durchmesser', max_digits=5, decimal_places=1)
    # gewicht = forms.DecimalField(blank=True, null=True, verbose_name='Gewicht', max_digits=5, decimal_places=2)
    # stempelstellung = forms.IntegerField(choices=STPL, blank=True, null=True, verbose_name='Stempelstellung')
    # avleg = forms.TextField(blank=True, null=True, verbose_name='Av.-Legende')
    # avbeschr = forms.TextField(blank=True, null=True, verbose_name='Av.-Beschreibung')
    # av_bildtyp = forms.ForeignKey('AvBildtyp', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='AvBildtyp')
    # av_beizeichen = forms.ForeignKey('AvBeizeichen', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='AvBeizeichen')
    # av_bildrand = forms.ForeignKey('AvBildrand', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='AvBildrand')
    # rvleg = forms.TextField(blank=True, null=True, verbose_name='Rv.-Legende')
    # rvbeschr = forms.TextField(blank=True, null=True, verbose_name='Rv.-Beschreibung')
    # rv_bildtyp = forms.ForeignKey('RvBildtyp', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='RvBildtyp')
    # rv_beizeichen = forms.ForeignKey('RvBeizeichen', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='RvBeizeichen')
    # rv_bildrand = forms.ForeignKey('RvBildrand', on_delete=forms.CASCADE, blank=True, null=True, verbose_name='RvBildrand')
    # anmerkung = forms.TextField(blank=True, null=True, verbose_name='Anmerkungen')
    