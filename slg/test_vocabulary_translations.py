from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override
from tablib import Dataset

from slg.models import Herstellung, Nominal, Person
from slg.services.authority_display import display_label
from slg.services.vocabulary_translations import (
    VOCABULARIES,
    draft_vocabulary_translations,
    get_translation_status,
    get_vocabulary_translation_batch,
)
from slg.templatetags.authority_labels import nomisma_url


class VocabularyTranslationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('vocabulary-editor')
        self.client.force_login(self.user)

    def test_draft_and_admin_import_preview_for_each_vocabulary(self):
        for key, model in VOCABULARIES.items():
            with self.subTest(vocabulary=key):
                entry = model.objects.create(name='Original')
                batch = get_vocabulary_translation_batch(self.user.pk, key)
                batch['rows'][0]['name_en'] = 'English label'
                draft = draft_vocabulary_translations(self.user.pk, key, batch['rows'])
                self.assertFalse(draft['persisted'])
                self.assertEqual(Dataset().load(draft['import_json'], format='json').headers,
                                 ['id', 'name', 'name_en', 'revision'])

                url_name = f'admin:slg_{key}'
                import_url = reverse(f'{url_name}_import')
                form = self.client.get(import_url).context['form']
                json_format = next(value for value, label in form.fields['format'].choices if label == 'json')
                resource = {'resource': '0'} if form.fields['resource'].choices else {}
                preview = self.client.post(import_url, {
                    **resource,
                    'format': json_format,
                    'import_file': SimpleUploadedFile('translations.json', draft['import_json'].encode()),
                })
                self.assertIsNotNone(preview.context['confirm_form'], preview.context['form'].errors)
                self.assertContains(preview, 'English label')
                entry.refresh_from_db()
                self.assertEqual(entry.name_en, '')
                with override('en'):
                    self.assertEqual(display_label(entry), 'Original')

                response = self.client.post(reverse(f'{url_name}_process_import'),
                                            preview.context['confirm_form'].initial)
                self.assertRedirects(response, reverse(f'{url_name}_changelist'))
                entry.refresh_from_db()
                self.assertEqual(entry.name, 'Original')
                self.assertEqual(entry.name_en, 'English label')
                self.assertEqual(get_vocabulary_translation_batch(self.user.pk, key)['rows'], [])
                with override('en'):
                    self.assertEqual(display_label(entry), 'English label')
                with override('de'):
                    self.assertEqual(display_label(entry), 'Original')
                with self.assertRaisesMessage(ValueError, 'inzwischen geändert'):
                    draft_vocabulary_translations(self.user.pk, key, batch['rows'])

    def test_inline_translation_saves_only_english_without_object_sync(self):
        entries = [Herstellung.objects.create(name=name) for name in ('Prägung', 'Guss', 'Druck')]
        labels = ['Struck', 'Cast', 'Printed']
        data = {'form-TOTAL_FORMS': '3', 'form-INITIAL_FORMS': '3', '_save': 'Save'}
        for index, (entry, label) in enumerate(zip(entries, labels)):
            data.update({f'form-{index}-id': entry.pk, f'form-{index}-name_en': label})

        url = reverse('admin:slg_herstellung_changelist')
        with patch('slg.signals._sync_queryset') as sync_objects:
            response = self.client.post(url, data)
        self.assertRedirects(response, url)
        sync_objects.assert_not_called()
        saved = Herstellung.objects.in_bulk(entry.pk for entry in entries)
        for entry, label in zip(entries, labels):
            self.assertEqual(saved[entry.pk].name, entry.name)
            self.assertEqual(saved[entry.pk].name_en, label)
        self.assertEqual(LogEntry.objects.filter(user=self.user, action_flag=2).count(), 3)

    def test_detail_form_synchronizes_objects_when_original_label_changes(self):
        entry = Herstellung.objects.create(name='Prägung')
        url = reverse('admin:slg_herstellung_change', args=[entry.pk])
        data = {'name': entry.name, 'name_en': 'Struck', 'name_nom_id': '', '_save': 'Save'}
        with patch('slg.signals._sync_queryset') as sync_objects:
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 302)
            sync_objects.assert_not_called()

            response = self.client.post(url, {**data, 'name': 'Handprägung', 'name_en': 'Hand-struck'})
            self.assertEqual(response.status_code, 302)
            sync_objects.assert_called_once()
        entry.refresh_from_db()
        self.assertEqual((entry.name, entry.name_en), ('Handprägung', 'Hand-struck'))

    def test_permissions_and_pagination(self):
        user = get_user_model().objects.create_user('limited-editor')
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='slg', codename__in=['change_obj', 'change_herstellung']))
        model = VOCABULARIES['herstellung']
        model.objects.bulk_create([model(name=f'Original {i}') for i in range(51)])
        model.objects.create(name='Übersetzt', name_en='Translated')
        status = get_translation_status(user.pk)['vocabularies']
        self.assertEqual(status, {'herstellung': {'total': 52, 'missing': 51}})
        with self.assertRaises(ValueError):
            get_vocabulary_translation_batch(user.pk, 'personfunktion')

        first = get_vocabulary_translation_batch(user.pk, 'herstellung')
        self.assertEqual(len(first['rows']), 50)
        second = get_vocabulary_translation_batch(user.pk, 'herstellung', first['next_after_id'], False)
        self.assertEqual(len(second['rows']), 2)
        self.assertIsNone(second['next_after_id'])
        second['rows'][0]['name_en'] = 'x' * 201
        with self.assertRaisesMessage(ValueError, '1–200'):
            draft_vocabulary_translations(user.pk, 'herstellung', second['rows'])


class DetailModalTests(TestCase):
    def test_empty_nomisma_reference_has_no_link(self):
        denomination = Nominal.objects.create(name='Unbestimmt')
        response = self.client.get(reverse('NominalModal', args=[denomination.pk]))
        self.assertContains(response, 'Unbestimmt')
        self.assertNotContains(response, 'href=""')
        self.assertEqual(nomisma_url('https://example.org/id/prague'), '')
        self.assertEqual(nomisma_url('http://nomisma.org/id/prague'), 'https://nomisma.org/id/prague')

    @patch('slg.views.public._wikipedia_summary')
    def test_person_modal_links_to_the_article_it_displays(self, summary):
        person = Person.objects.create(
            name='Maria Theresia', beschreibung='Lokale Beschreibung',
            WikiDe='https://de.wikipedia.org/wiki/Maria_Theresia',
            WikiEn='https://en.wikipedia.org/wiki/Maria_Theresa',
        )
        url = reverse('PersonModal', args=[person.pk])
        summary.return_value = 'English summary', ''
        response = self.client.get(url, headers={'Accept-Language': 'en'})
        summary.assert_called_once_with(person.WikiEn)
        self.assertContains(response, 'English summary')
        self.assertContains(response, f'href="{person.WikiEn}"', count=1)

        summary.return_value = '', ''
        response = self.client.get(url, headers={'Accept-Language': 'en'})
        self.assertContains(response, 'Lokale Beschreibung')
