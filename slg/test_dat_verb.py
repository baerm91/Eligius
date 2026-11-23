"""Verbale Datierung, insbesondere Zeiträume über die Zeitenwende."""
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from .models import Herstellung, Muenztyp, Objekttyp, Workflow, format_dat_verb


class FormatDatVerbTests(SimpleTestCase):
    def test_across_the_era(self):
        self.assertEqual(format_dat_verb(-44, 14), '44 v. Chr. – 14 n. Chr.')
        self.assertEqual(format_dat_verb(-25, 291, ad_suffix_below=492), '25 v. Chr. – 291 n. Chr.')

    def test_unchanged_cases(self):
        self.assertEqual(format_dat_verb(222, 235), '222-235 n. Chr.')
        self.assertEqual(format_dat_verb(222, 222), '222 n. Chr.')
        self.assertEqual(format_dat_verb(-44, -30), '44-30 v. Chr.')
        self.assertEqual(format_dat_verb(-44, -44), '44 v. Chr.')
        self.assertEqual(format_dat_verb(1500, 1510, ad_suffix_below=492), '1500-1510')
        self.assertEqual(format_dat_verb(300, 310, ad_suffix_below=492), '300-310 n. Chr.')
        self.assertIsNone(format_dat_verb(20, 10))
        self.assertIsNone(format_dat_verb(None, 10))


class RepairDatVerbTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workflow = Workflow.objects.create(name='Entwurf', reihenfolge=1)
        cls.fk = dict(workflow=cls.workflow, Objekttyp=Objekttyp.objects.create(name='Münze'),
                      Herstellung=Herstellung.objects.create(name='Geprägt'))

    def test_repairs_only_generated_legacy_text(self):
        broken = Muenztyp.objects.create(titel='A', muenztyptitel='A', **self.fk, dat_von=-25, dat_bis=270, dat_verb='-25-270 n. Chr.')
        manual = Muenztyp.objects.create(titel='B', muenztyptitel='B', **self.fk, dat_von=-25, dat_bis=270, dat_verb='augusteisch')
        out = StringIO()
        call_command('repair_dat_verb', stdout=out)
        broken.refresh_from_db()
        self.assertEqual(broken.dat_verb, '-25-270 n. Chr.')
        self.assertIn('1 Datierung', out.getvalue())
        call_command('repair_dat_verb', '--apply', stdout=StringIO())
        broken.refresh_from_db(); manual.refresh_from_db()
        self.assertEqual(broken.dat_verb, '25 v. Chr. – 270 n. Chr.')
        self.assertEqual(manual.dat_verb, 'augusteisch')

    def test_new_records_get_correct_text(self):
        typ = Muenztyp.objects.create(titel='C', muenztyptitel='C', **self.fk, dat_von=-44, dat_bis=14)
        self.assertEqual(typ.dat_verb, '44 v. Chr. – 14 n. Chr.')
