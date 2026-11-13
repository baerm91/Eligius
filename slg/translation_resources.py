"""Translation-only round trips: immutable IDs and original text, atomic imports."""
import hashlib
import json

from django.contrib import admin
from django import forms
from import_export import fields, resources

from slg.models import AvBildtyp, RvBildtyp


class TranslationAdminMixin:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'name_en':
            kwargs['widget'] = forms.Textarea(attrs={'rows': 3, 'cols': 45,
                'style': 'width:100%;min-width:16em;box-sizing:border-box', 'lang': 'en'})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_import_permission(self, request):
        return self.has_change_permission(request)

    def has_export_permission(self, request):
        return self.has_view_or_change_permission(request)

    def is_skip_import_confirm_enabled(self):
        return False


def translation_revision(instance):
    value = [instance._meta.label, instance.pk, instance.name, instance.name_en]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


class TranslationStatusFilter(admin.SimpleListFilter):
    title = 'Englische Übersetzung'
    parameter_name = 'english'

    def lookups(self, request, model_admin):
        return [('missing', 'Fehlt'), ('translated', 'Vorhanden')]

    def queryset(self, request, queryset):
        if self.value() == 'missing':
            return queryset.filter(name_en='')
        if self.value() == 'translated':
            return queryset.exclude(name_en='')
        return queryset


class BildtypTranslationResource(resources.ModelResource):
    name = fields.Field(attribute='name', column_name='name', readonly=True)
    revision = fields.Field(column_name='revision', readonly=True)

    def dehydrate_revision(self, instance):
        return translation_revision(instance)

    def before_import(self, dataset, **kwargs):
        if set(dataset.headers or []) != {'id', 'name', 'name_en', 'revision'}:
            raise ValueError('Erforderliche Spalten: id, name, name_en, revision. Bitte Übersetzungsexport verwenden.')
        ids = [str(row['id']) for row in dataset.dict]
        if len(ids) != len(set(ids)):
            raise ValueError('Doppelte IDs sind nicht zulässig.')

    def after_init_instance(self, instance, new, row, **kwargs):
        if new:
            raise ValueError('Übersetzungsimport darf keine Datensätze anlegen.')
        if row.get('name') != instance.name or row.get('revision') != translation_revision(instance):
            raise ValueError('Datensatz wurde seit dem Export geändert. Bitte neu exportieren.')
        value = row.get('name_en')
        if value is None or value == '' or (isinstance(value, str) and not value.strip()):
            row['name_en'] = instance.name_en
        elif not isinstance(value, str) or len(value) > 500:
            raise ValueError('Englische Übersetzung darf maximal 500 Zeichen enthalten.')

    def get_instance(self, instance_loader, row):
        instance = super().get_instance(instance_loader, row)
        if instance is not None:
            return self._meta.model.objects.select_for_update().get(pk=instance.pk)
        return instance

    def import_data(self, dataset, dry_run=False, raise_errors=False, **kwargs):
        kwargs.update(use_transactions=True, rollback_on_validation_errors=True)
        return super().import_data(dataset, dry_run=dry_run, raise_errors=raise_errors, **kwargs)

    class Meta:
        fields = ('id', 'name', 'name_en', 'revision')
        export_order = fields
        import_id_fields = ('id',)
        clean_model_instances = True
        skip_unchanged = True
        use_transactions = True


class AvBildtypTranslationResource(BildtypTranslationResource):
    class Meta(BildtypTranslationResource.Meta):
        model = AvBildtyp


class RvBildtypTranslationResource(BildtypTranslationResource):
    class Meta(BildtypTranslationResource.Meta):
        model = RvBildtyp
