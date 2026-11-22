import tablib
from django.test import TestCase

from .admin import ObjPaketZuweisungResource
from .models import Obj, Objekttyp, Paket, Slg, SlgTeil, Workflow


class PaketImportTests(TestCase):
	def setUp(self):
		Workflow.objects.create(pk=1, name='neu', reihenfolge=1)
		Objekttyp.objects.create(pk=1, name='Münze')
		self.slg = Slg.objects.create(name='Landessammlungen Niederösterreich')
		self.teil = SlgTeil.objects.create(name='Römische Archäologie', idfk_Slg_SlgTeil=self.slg)
		# gleichnamiger Sammlungsteil (früher Ursache für 0 Treffer)
		SlgTeil.objects.create(name='Römische Archäologie')
		self.o1 = Obj.objects.create(invnr='CAR-N-1', Slg=self.slg, SlgTeil=self.teil)
		self.o2 = Obj.objects.create(invnr='CAR-N-2', Slg=self.slg, SlgTeil=self.teil)

	def _ds(self, rows, headers=('invnr', 'Sammlung', 'Sammlungsteil', 'Paket')):
		ds = tablib.Dataset(headers=list(headers))
		for r in rows:
			ds.append(r)
		return ds

	def test_dry_run_rolls_back_and_real_import_assigns(self):
		ds = self._ds([
			['CAR-N-1', 'Landessammlungen Niederösterreich', 'Römische Archäologie', 'Carnuntum, Parkplatz'],
			['CAR-N-2', 'Landessammlungen Niederösterreich', 'Römische Archäologie', 'Carnuntum, Parkplatz'],
		])
		res = ObjPaketZuweisungResource().import_data(ds, dry_run=True)
		self.assertFalse(res.has_errors())
		self.assertFalse(Paket.objects.exists())

		res = ObjPaketZuweisungResource().import_data(ds, dry_run=False)
		self.assertFalse(res.has_errors())
		self.assertEqual(res.totals['new'], 2)
		paket = Paket.objects.get(name='Carnuntum, Parkplatz')
		self.assertEqual(set(paket.obj_set.values_list('invnr', flat=True)), {'CAR-N-1', 'CAR-N-2'})

		res = ObjPaketZuweisungResource().import_data(ds, dry_run=False)
		self.assertEqual(res.totals['skip'], 2)

	def test_wrong_slgteil_is_reported_in_preview(self):
		ds = self._ds([['CAR-N-1', 'Landessammlungen Niederösterreich', 'Carnuntum', 'P']])
		res = ObjPaketZuweisungResource().import_data(ds, dry_run=True)
		self.assertTrue(res.has_errors())
		self.assertIn('Römische Archäologie', str(res.base_errors[0].error))

	def test_match_by_object_id(self):
		ds = self._ds([[self.o1.pk, 'P']], headers=('Objekt-ID', 'Paket'))
		res = ObjPaketZuweisungResource().import_data(ds, dry_run=False)
		self.assertFalse(res.has_errors())
		self.assertTrue(self.o1.pakete.filter(name='P').exists())
