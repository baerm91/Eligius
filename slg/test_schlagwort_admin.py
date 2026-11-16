from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from tablib import Dataset

from slg.models import (
    AvBildtyp, AvBildtyp_Schlagwort, Muenztyp, MuenztypObjektAnzeige,
    Mztyp_Schlagwort, Obj, RvBildtyp, RvBildtyp_Schlagwort, Schlagwort,
)
from slg.translation_resources import SchlagwortTranslationResource


class SchlagwortAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('keyword-editor')
        self.client.force_login(self.user)
        self.url = reverse('admin:slg_schlagwort_changelist')

    def preview(self, *keywords):
        data = {'action': 'merge_selected_keywords', ACTION_CHECKBOX_NAME: [row.pk for row in keywords]}
        response = self.client.post(self.url, {**data, 'index': '0'})
        self.assertTemplateUsed(response, 'admin/slg/schlagwort/merge.html')
        return {**data, 'confirm_merge': '1', 'revision': response.context['form'].initial['revision']}

    def test_existing_duplicates_are_listed_and_new_duplicates_are_rejected(self):
        first = Schlagwort.objects.create(name='Landschaft')
        second = Schlagwort.objects.create(name='LANDSCHAFT ')
        other = Schlagwort.objects.create(name='Ort')
        response = self.client.get(self.url, {'duplicates': 'yes'})
        self.assertEqual({row.pk for row in response.context['cl'].result_list}, {first.pk, second.pk})
        for url in (reverse('admin:slg_schlagwort_add'),
                    reverse('admin:slg_schlagwort_change', args=[other.pk])):
            response = self.client.post(url, {'name': ' landschaft ', '_save': 'Save'})
            self.assertFormError(response.context['adminform'].form, 'name',
                                 'Ein Schlagwort mit diesem Namen existiert bereits.')
        response = self.client.post(reverse('admin:slg_schlagwort_change', args=[first.pk]),
                                    {'name': first.name, 'name_en': 'Landscape', '_save': 'Save'})
        self.assertRedirects(response, self.url)

    def test_export_has_nomisma_link_and_remains_a_translation_import(self):
        keyword = Schlagwort.objects.create(name='Bogen', name_nom_id='arch')
        resource = SchlagwortTranslationResource()
        export = resource.export()
        self.assertEqual(export.headers, ['id', 'name', 'name_en', 'revision', 'nomisma_url'])
        self.assertEqual(export.dict[0]['nomisma_url'], 'https://nomisma.org/id/arch')
        row = export.dict[0]
        row.update(name_en='Arch', nomisma_url='https://nomisma.org/id/replaced')
        result = resource.import_data(Dataset(list(row.values()), headers=list(row)))
        self.assertFalse(result.has_errors(), result.row_errors())
        keyword.refresh_from_db()
        self.assertEqual((keyword.name_en, keyword.name_nom_id), ('Arch', 'arch'))

    def test_merge_keeps_target_and_all_links_and_refreshes_search(self):
        target = Schlagwort.objects.create(name='Baum')
        source = Schlagwort.objects.create(name='Gehölz', name_en='Tree', name_nom_id='tree')
        another = Schlagwort.objects.create(name='Flora')
        av = AvBildtyp.objects.create(name='Baum')
        rv = RvBildtyp.objects.create(name='Gehölz')
        typ = Muenztyp.objects.bulk_create([
            Muenztyp(av_bildtyp=av, rv_bildtyp=rv, Objekttyp=None, Herstellung=None, workflow=None),
        ])[0]
        for owner in (av, rv, typ):
            owner.schlagworte.add(source, another)
        overlap = AvBildtyp_Schlagwort.objects.create(avbildtyp=av, schlagwort=target)
        old_rv_link = RvBildtyp_Schlagwort.objects.get(rvbildtyp=rv, schlagwort=source)
        direct, inherited = Obj.objects.bulk_create([
            Obj(invnr='direct', av_bildtyp=av, Objekttyp=None, workflow=None),
            Obj(invnr='inherited', Typ=typ, Objekttyp=None, workflow=None),
        ])
        for obj in (direct, inherited):
            MuenztypObjektAnzeige.objects.create(obj_id=obj.pk, invnr=obj.invnr,
                                                av_schlagworte='Gehölz', rv_schlagworte='unberührt')

        data = self.preview(target, source, another)
        self.assertEqual(Schlagwort.objects.count(), 3)
        result = self.client.post(self.url, {**data, 'target': target.pk})
        self.assertRedirects(result, self.url)
        self.assertEqual(list(Schlagwort.objects.values_list('pk', 'name_en', 'name_nom_id')),
                         [(target.pk, 'Tree', 'tree')])
        self.assertEqual(list(AvBildtyp_Schlagwort.objects.values_list('pk', 'schlagwort_id')),
                         [(overlap.pk, target.pk)])
        self.assertEqual(list(RvBildtyp_Schlagwort.objects.values_list('pk', 'schlagwort_id')),
                         [(old_rv_link.pk, target.pk)])
        self.assertEqual(list(Mztyp_Schlagwort.objects.values_list('schlagwort_id', flat=True)), [target.pk])
        self.assertEqual(MuenztypObjektAnzeige.objects.get(obj_id=direct.pk).rv_schlagworte, 'unberührt')
        self.assertEqual(MuenztypObjektAnzeige.objects.get(obj_id=inherited.pk).rv_schlagworte, 'Baum')
        self.assertEqual(set(MuenztypObjektAnzeige.objects.values_list('av_schlagworte', flat=True)), {'Baum'})
        self.assertIn('Gehölz', LogEntry.objects.get(object_id=str(target.pk)).change_message)

    def test_conflicts_require_choices_and_changed_links_invalidate_preview(self):
        target = Schlagwort.objects.create(name='Baum', name_en='Tree', name_nom_id='tree')
        source = Schlagwort.objects.create(name='Bäume', name_en='Trees', name_nom_id='trees')
        data = self.preview(target, source)
        response = self.client.post(self.url, {**data, 'target': target.pk})
        self.assertEqual(set(response.context['form'].errors), {'name_en', 'name_nom_id'})

        av = AvBildtyp.objects.create(name='Baum')
        link = AvBildtyp_Schlagwort.objects.create(avbildtyp=av, schlagwort=source)
        choices = {'target': target.pk, 'name_en': 'Trees', 'name_nom_id': 'tree'}
        response = self.client.post(self.url, {**data, **choices})
        self.assertContains(response, 'Die Schlagworte oder Verknüpfungen wurden geändert.')
        self.assertEqual(Schlagwort.objects.count(), 2)

        renewed = self.preview(target, source)
        self.assertRedirects(self.client.post(self.url, {**renewed, **choices}), self.url)
        link.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual((link.schlagwort_id, target.name_en, target.name_nom_id), (target.pk, 'Trees', 'tree'))
