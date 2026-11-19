from datetime import date
from decimal import Decimal

import tablib
from django.test import TestCase

from .models import Fund, Fundort, Obj, Objekttyp, Workflow
from .resources import FundResource


class FundImportTests(TestCase):
	def setUp(self):
		Workflow.objects.create(pk=1, name='neu', reihenfolge=1)
		Objekttyp.objects.create(pk=1, name='Münze')
		self.ort = Fundort.objects.create(name='Parkplatz')
		self.obj_neu = Obj.objects.create(invnr='P1')
		self.obj_alt = Obj.objects.create(invnr='P2')
		Fund.objects.create(objekt=self.obj_alt, maßnahmennr='M-1', fundnummer=7, parzelle='alt')

	def _import(self, dataset, dry_run=False):
		return FundResource().import_data(dataset, dry_run=dry_run)

	def test_export_template_contains_objects_with_and_without_fund(self):
		ds = FundResource().export_template(Obj.objects.order_by('invnr'))
		self.assertEqual(ds.height, 2)
		self.assertIn('Objekt-ID', ds.headers)
		rows = {r['Inv.-Nr. (nur Info)']: r for r in ds.dict}
		self.assertEqual(rows['P2']['maßnahmennr'], 'M-1')
		self.assertIn(rows['P1']['maßnahmennr'], ('', None))
		# Vorlage selbst darf nichts anlegen
		self.assertEqual(Fund.objects.count(), 1)
		ds.export('xlsx')

	def test_roundtrip_creates_and_updates_without_blanking(self):
		ds = FundResource().export_template(Obj.objects.order_by('invnr'))
		data = list(ds.dict)
		for row in data:
			if row['Objekt-ID'] == self.obj_neu.pk:
				row['maßnahmennr'] = 'M-2'
				row['fundort'] = 'Parkplatz'
				row['funddatum'] = date(2024, 5, 3)
				row['lm_von'] = '12.5'
			else:
				row['parzelle'] = ''  # leer -> bleibt 'alt'
				row['stratum'] = 'Schicht 3'
		new = tablib.Dataset(headers=ds.headers)
		for row in data:
			new.append([row[h] for h in ds.headers])

		result = self._import(new, dry_run=True)
		self.assertFalse(result.has_errors() or result.has_validation_errors())
		self.assertEqual(Fund.objects.count(), 1)

		result = self._import(new)
		self.assertFalse(result.has_errors() or result.has_validation_errors())
		neu = Fund.objects.get(objekt=self.obj_neu)
		self.assertEqual(neu.fundort, self.ort)
		self.assertEqual(neu.fundjahr, 2024)
		self.assertEqual(neu.lm_bis, Decimal('12.5'))
		alt = Fund.objects.get(objekt=self.obj_alt)
		self.assertEqual(alt.parzelle, 'alt')
		self.assertEqual(alt.stratum, 'Schicht 3')
		self.assertEqual(alt.fundnummer, 7)

	def test_unknown_object_and_fundort_are_reported(self):
		ds = tablib.Dataset(headers=['Objekt-ID', 'fundort'])
		ds.append([999999, ''])
		ds.append([self.obj_neu.pk, 'Gibtsnicht'])
		result = self._import(ds, dry_run=True)
		self.assertTrue(result.has_errors() or result.has_validation_errors())
		self.assertEqual(Fund.objects.count(), 1)
