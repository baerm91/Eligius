import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from django.utils.translation import override

from .models import Bildabruf, Nominal, Obj
from .services.authority_display import display_label, display_text
from .services.authority_inventory import inventory
from .services.authority_proposals import build_proposals
from .test_bugfix_regressions import Fixtures


class AuthorityReviewImportTests(TestCase):
    def test_preview_apply_and_stale_original_and_reference(self):
        nominal = Nominal.objects.create(name='Prüfdenar', name_nom_id='denarius')
        references = inventory([{
            'model': 'slg.Nominal', 'id': nominal.pk, 'label': nominal.name,
            'field': 'name_nom_id', 'value': nominal.name_nom_id,
        }])['records']
        row, = build_proposals(references, {})
        review = {'schema': 'eligius-authority-review-v1', 'inventory_sha256': 'fixture', 'decisions': [{
            'status': 'approved', 'model': row['model'], 'id': row['id'], 'value': 'Reviewed denarius',
            'original_sha256': row['original_sha256'], 'updated_at': '2026-11-22T10:00:00Z',
        }]}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            proposals_path, review_path, output = (root / name for name in ('proposals', 'review', 'approved'))
            proposals_path.write_text(json.dumps({'inventory_sha256': 'fixture', 'proposals': [row]}), encoding='utf-8')
            review_path.write_text(json.dumps(review), encoding='utf-8')
            with self.settings(ELIGIUS_REVIEWED_AUTHORITY_LABELS_PATH=output), override('en'):
                call_command('import_authority_review', str(proposals_path), str(review_path), stdout=StringIO())
                self.assertFalse(output.exists())
                call_command('import_authority_review', str(proposals_path), str(review_path), apply=True, stdout=StringIO())
                self.assertEqual(display_label(nominal), 'Reviewed denarius')
                self.assertEqual(display_text(nominal.name, 'Nominal'), 'Reviewed denarius')
                with override('de'):
                    self.assertEqual(display_label(nominal), nominal.name)
                original_file = output.read_bytes()
                review['decisions'][0].update(value='Older review', updated_at='2026-11-21T10:00:00Z')
                review_path.write_text(json.dumps(review), encoding='utf-8')
                with self.assertRaisesMessage(CommandError, 'neuere Freigabe'):
                    call_command('import_authority_review', str(proposals_path), str(review_path), apply=True)
                self.assertEqual(output.read_bytes(), original_file)
                nominal.name_nom_id = 'different'
                nominal.save()
                self.assertEqual(display_label(nominal), nominal.name)
                with self.assertRaisesMessage(CommandError, 'inzwischen geändert'):
                    call_command('import_authority_review', str(proposals_path), str(review_path), apply=True)
                self.assertEqual(output.read_bytes(), original_file)


class ImageRequestAdminTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.user = User.objects.create_superuser('analytics')
        obj = Obj.objects.create(invnr='TEST-ABRUF', Typ=cls.typ, Slg=cls.slg, workflow=cls.controlled)
        today = timezone.localdate()
        for host, automated, requests, age in (
            ('cdn.kulturpool.at', False, 4, 0), ('europeana.eu', True, 12, 0),
            ('', False, 2, 1), ('kulturpool.at.example.test', False, 3, 0),
            ('eligius', False, 6, 70),
        ):
            Bildabruf.objects.create(obj=obj, ansicht='av', datum=today - timedelta(days=age),
                                     herkunft=host, automatisiert=automated, anzahl=requests)

    def test_summary_uses_collection_and_date_filters(self):
        self.client.force_login(self.user)
        url = '/admin/slg/bildabruf/'
        response = self.client.get(url, {'obj__Slg__id__exact': self.slg.pk})
        self.assertContains(response, 'Abrufe der Bildweiterleitung')
        stats = response.context['image_stats']
        self.assertEqual(stats['total'], 21)
        self.assertEqual(dict(stats['origins'])['Kulturpool'], [4, 0])
        self.assertEqual(dict(stats['origins'])['Europeana'], [0, 12])
        self.assertEqual(dict(stats['origins'])['Andere'], [3, 0])
        self.assertEqual(stats['top'][0]['total'], 9)
        self.assertEqual(len(stats['timeline']), 30)
        old_day = timezone.localdate() - timedelta(days=70)
        monthly = self.client.get(url, {'datum__year': old_day.year}).context['image_stats']
        self.assertTrue(monthly['monthly'])

    def test_anonymous_user_cannot_read_summary(self):
        self.assertEqual(self.client.get('/admin/slg/bildabruf/').status_code, 302)


class EditorialPageLanguageTests(TestCase):
    def test_public_pages_render_in_both_languages(self):
        for url, german, english in (
            ('/lab/', 'Gemeinsame Recherchewerkzeuge', 'Shared research tools'),
            ('/about/', 'Institutionelle Partner', 'Institutional partners'),
            ('/impressum/', 'Haftungsausschluss', 'Disclaimer'),
            ('/datenschutz/', 'Ihre Rechte', 'Your rights'),
        ):
            self.client.cookies['django_language'] = 'de'
            self.assertContains(self.client.get(url), german)
            self.client.cookies['django_language'] = 'en'
            self.assertContains(self.client.get(url), english)
