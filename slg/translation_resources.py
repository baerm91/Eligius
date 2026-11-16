"""Translation-only round trips: immutable IDs and original text, atomic imports."""
import hashlib
import json

from django.contrib import admin
from django import forms
from django.db import transaction
from import_export import fields, resources
from import_export.forms import ExportForm
from import_export.instance_loaders import CachedInstanceLoader

from slg.models import AvBildtyp, Herstellung, Objekttyp, PersonFunktion, RvBildtyp, Schlagwort
from slg.services.authority_display import clear_display_cache
from slg.templatetags.authority_labels import nomisma_url


class TranslationAdminMixin:
    import_export_change_list_template = 'admin/import_export/change_list_import_export.html'
    export_form_class = ExportForm

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'name_en':
            short_label = db_field.max_length <= 200
            attrs = {
                'rows': 3,
                'cols': 24 if short_label else 45,
                'lang': 'en',
                'style': 'width:100%;box-sizing:border-box',
            }
            attrs['style'] += ';min-width:8em' if short_label else ';min-width:16em'
            kwargs['widget'] = forms.Textarea(attrs=attrs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if change and form.changed_data == ['name_en']:
            obj.save(update_fields=['name_en'])
        else:
            super().save_model(request, obj, form, change)

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


class LockedTranslationLoader(CachedInstanceLoader):
    def get_queryset(self):
        return super().get_queryset().using(
            self.resource.get_db_connection_name(),
        ).order_by('pk').select_for_update()


class BildtypTranslationResource(resources.ModelResource):
    optional_import_columns = frozenset()
    name = fields.Field(attribute='name', column_name='name', readonly=True)
    revision = fields.Field(column_name='revision', readonly=True)

    def dehydrate_revision(self, instance):
        return translation_revision(instance)

    def before_import(self, dataset, **kwargs):
        headers = dataset.headers or []
        required = {'id', 'name', 'name_en', 'revision'}
        if len(headers) != len(set(headers)) or set(headers) - self.optional_import_columns != required:
            raise ValueError('Erforderliche Spalten: id, name, name_en, revision. Bitte Übersetzungsexport verwenden.')
        id_column = dataset.headers.index('id')
        id_field = self.fields['id']
        ids = [id_field.clean({'id': row[id_column]}) for row in dataset]
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
        else:
            limit = instance._meta.get_field('name_en').max_length
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(f'Englische Übersetzung darf maximal {limit} Zeichen enthalten.')

    def get_bulk_update_fields(self):
        return ['name_en']

    def bulk_update(self, using_transactions, dry_run, raise_errors, batch_size=None, result=None):
        if dry_run:
            self.update_instances.clear()
            return
        super().bulk_update(using_transactions, dry_run, raise_errors, batch_size, result)

    def after_import(self, dataset, result, **kwargs):
        super().after_import(dataset, result, **kwargs)
        if result.totals['update']:
            transaction.on_commit(clear_display_cache, using=self.get_db_connection_name())

    def import_data(self, dataset, dry_run=False, raise_errors=False, **kwargs):
        kwargs.update(use_transactions=True, rollback_on_validation_errors=True)
        return super().import_data(dataset, dry_run=dry_run, raise_errors=raise_errors, **kwargs)

    class Meta:
        fields = ('id', 'name', 'name_en', 'revision')
        export_order = fields
        import_id_fields = ('id',)
        # Only name_en is editable and after_init_instance validates it.
        instance_loader_class = LockedTranslationLoader
        use_bulk = True
        batch_size = 250
        skip_unchanged = True
        report_skipped = False
        use_transactions = True


class AvBildtypTranslationResource(BildtypTranslationResource):
    class Meta(BildtypTranslationResource.Meta):
        model = AvBildtyp


class RvBildtypTranslationResource(BildtypTranslationResource):
    class Meta(BildtypTranslationResource.Meta):
        model = RvBildtyp


def translation_resource(model_class):
    """Translation-only resource for any model with name and name_en."""
    meta = type('Meta', (BildtypTranslationResource.Meta,), {
        'model': model_class,
        'name': 'Englische Übersetzungen',
    })
    return type(f'{model_class.__name__}TranslationResource', (BildtypTranslationResource,), {'Meta': meta})


ObjekttypTranslationResource = translation_resource(Objekttyp)
HerstellungTranslationResource = translation_resource(Herstellung)
PersonFunktionTranslationResource = translation_resource(PersonFunktion)


class SchlagwortTranslationResource(BildtypTranslationResource):
    nomisma_url = fields.Field(column_name='nomisma_url', readonly=True)
    optional_import_columns = frozenset({'nomisma_url'})

    def dehydrate_nomisma_url(self, instance):
        return nomisma_url(instance.name_nom_id)

    class Meta(BildtypTranslationResource.Meta):
        model = Schlagwort
        name = 'Englische Übersetzungen'
        fields = (*BildtypTranslationResource.Meta.fields, 'nomisma_url')
        export_order = fields
