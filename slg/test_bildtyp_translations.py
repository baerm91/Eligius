from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils.translation import override
from tablib import Dataset

from slg.models import AvBildtyp, RvBildtyp, Obj, MuenztypObjektAnzeige
from slg.services.bildtyp_translations import get_translation_batch, draft_translations
from slg.translation_resources import AvBildtypTranslationResource, RvBildtypTranslationResource


class BildtypTranslationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('translator', password='test')
        self.client.force_login(self.user)

    def test_roundtrip_preview_original_preserved_and_blank_rows_skipped(self):
        for model, resource_class in [(AvBildtyp, AvBildtypTranslationResource),
                                      (RvBildtyp, RvBildtypTranslationResource)]:
            first = model.objects.create(name='Kopf nach rechts (?)')
            second = model.objects.create(name='Stehende Figur')
            resource = resource_class()
            data = resource.export(model.objects.order_by('pk'))
            data[0] = [data[0][0], data[0][1], 'Head right (?)', data[0][3]]
            result = resource.import_data(data, dry_run=True)
            self.assertFalse(result.has_errors(), result.row_errors())
            self.assertFalse(result.has_validation_errors())
            first.refresh_from_db()
            self.assertEqual(first.name_en, '')
            result = resource.import_data(data, dry_run=False)
            self.assertFalse(result.has_errors(), result.row_errors())
            first.refresh_from_db(); second.refresh_from_db()
            self.assertEqual(first.name, 'Kopf nach rechts (?)')
            self.assertEqual(first.name_en, 'Head right (?)')
            self.assertEqual(second.name_en, '')
            with override('en'):
                self.assertEqual(first.display_name, 'Head right (?)')
                self.assertEqual(second.display_name, second.name)
                self.assertEqual(str(first), first.name)
            with override('de'):
                self.assertEqual(first.display_name, first.name)
            # An older export cannot overwrite a newer translation.
            self.assertTrue(resource.import_data(data, dry_run=False).has_errors())

    def test_import_is_atomic_and_rejects_creation_wrong_model_and_duplicate_ids(self):
        first = AvBildtyp.objects.create(name='Original')
        resource = AvBildtypTranslationResource()
        data = resource.export()
        row = list(data[0]); row[2] = 'English'
        data[0] = row
        data.append([99999, 'Unknown', 'Unknown', 'bad'])
        self.assertTrue(resource.import_data(data, dry_run=False).has_errors())
        first.refresh_from_db()
        self.assertEqual(first.name_en, '')
        self.assertEqual(AvBildtyp.objects.count(), 1)
        reverse = RvBildtyp.objects.create(pk=first.pk, name=first.name)
        self.assertTrue(RvBildtypTranslationResource().import_data(data, dry_run=False).has_errors())
        duplicate = Dataset(*[row, row], headers=data.headers)
        self.assertTrue(resource.import_data(duplicate, dry_run=False).has_errors())

    def test_admin_two_columns_save_and_filter(self):
        row = AvBildtyp.objects.create(name='Büste nach links')
        url = reverse('admin:slg_avbildtyp_changelist')
        response = self.client.get(url)
        self.assertContains(response, 'Büste nach links')
        self.assertContains(response, 'name="form-0-name_en"')
        response = self.client.post(url, {'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000', 'form-0-id': row.pk,
            'form-0-name_en': 'Bust left', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.name_en, 'Bust left')
        self.assertNotContains(self.client.get(url, {'english': 'missing'}), 'Büste nach links')

    def test_mcp_drafts_roundtrip_without_writing_and_permissions(self):
        row = RvBildtyp.objects.create(name='Altar (?)')
        batch = get_translation_batch(self.user.pk, 'rv')
        batch['rows'][0]['name_en'] = 'Altar (?)'
        draft = draft_translations(self.user.pk, 'rv', batch['rows'])
        self.assertFalse(draft['persisted'])
        row.refresh_from_db()
        self.assertEqual(row.name_en, '')
        data = Dataset().load(draft['import_json'], format='json')
        result = RvBildtypTranslationResource().import_data(data, dry_run=False)
        self.assertFalse(result.has_errors(), result.row_errors())
        with self.assertRaises(ValueError):
            draft_translations(self.user.pk, 'rv', batch['rows'])
        visitor = get_user_model().objects.create_user('visitor')
        with self.assertRaises(ValueError):
            get_translation_batch(visitor.pk, 'rv')

    def test_english_facets_keep_ids_counts_and_fallback(self):
        from slg.services.public_api import facet_values
        first = AvBildtyp.objects.create(name='Kopf nach rechts', name_en='Head right')
        second = AvBildtyp.objects.create(name='Unübersetzt')
        for i, motif in enumerate([first, first, second]):
            obj = Obj.objects.bulk_create([Obj(invnr=str(i), Objekttyp=None, workflow=None)])[0]
            MuenztypObjektAnzeige.objects.create(obj_id=obj.pk, invnr=str(i),
                av_bildtyp=motif.name, av_bildtyp_fk=motif)
        request = RequestFactory().get('/api/facet/')
        with override('en'):
            result = facet_values(request, 'av_bildtyp')
            self.assertEqual(result, [dict(id=first.pk, name='Head right', count=2),
                                      dict(id=second.pk, name='Unübersetzt', count=1)])
            self.assertEqual(facet_values(request, 'av_bildtyp', term='Head'), result[:1])
        with override('de'):
            self.assertEqual(facet_values(request, 'av_bildtyp')[0]['name'], first.name)
