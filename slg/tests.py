from datetime import datetime, timezone as datetime_timezone

from django.test import SimpleTestCase, TestCase

from .models import Metall, Muenztyp, Nominal, Obj
from .signals import disable_mtoa_sync, enable_mtoa_sync
from .views import _clean_export_invnrs, _export_datetime


class ExportCoinStateHelperTests(SimpleTestCase):
    def test_clean_export_invnrs_strips_empty_values_and_deduplicates(self):
        self.assertEqual(
            _clean_export_invnrs([" 1 ", "", None, "2", "1", " 2 "]),
            ["1", "2"],
        )

    def test_export_datetime_uses_isoformat_and_empty_string_for_none(self):
        value = datetime(2026, 5, 7, 5, 1, tzinfo=datetime_timezone.utc)

        self.assertEqual(_export_datetime(value), "2026-05-07T05:01:00+00:00")
        self.assertEqual(_export_datetime(None), "")


class ObjSaveTests(TestCase):
    def test_save_uses_nominal_material_when_object_material_is_empty(self):
        material = Metall.objects.create(name="Kupfer")
        nominal = Nominal.objects.create(name="Nummus", material=material)
        disable_mtoa_sync()
        try:
            obj = Obj.objects.create(invnr="1", idfk_Nominal=nominal)
        finally:
            enable_mtoa_sync()

        self.assertEqual(obj.Metall, material)

    def test_save_keeps_existing_object_material(self):
        nominal_material = Metall.objects.create(name="Kupfer")
        object_material = Metall.objects.create(name="Silber")
        nominal = Nominal.objects.create(name="Nummus", material=nominal_material)
        disable_mtoa_sync()
        try:
            obj = Obj.objects.create(
                invnr="2",
                idfk_Nominal=nominal,
                Metall=object_material,
            )
        finally:
            enable_mtoa_sync()

        self.assertEqual(obj.Metall, object_material)

    def test_save_does_not_use_nominal_material_when_object_has_type(self):
        material = Metall.objects.create(name="Kupfer")
        nominal = Nominal.objects.create(name="Nummus", material=material)
        typ = Muenztyp.objects.create(
            muenztyptitel="Typ",
            Objekttyp=None,
            Herstellung=None,
            workflow=None,
        )
        disable_mtoa_sync()
        try:
            obj = Obj.objects.create(invnr="3", Typ=typ, idfk_Nominal=nominal)
        finally:
            enable_mtoa_sync()

        self.assertIsNone(obj.Metall)

    def test_save_includes_nominal_material_when_update_fields_are_used(self):
        material = Metall.objects.create(name="Kupfer")
        nominal = Nominal.objects.create(name="Nummus", material=material)
        disable_mtoa_sync()
        try:
            obj = Obj.objects.create(invnr="4")
            obj.idfk_Nominal = nominal
            obj.save(update_fields=['idfk_Nominal'])
        finally:
            enable_mtoa_sync()

        obj.refresh_from_db()
        self.assertEqual(obj.Metall, material)
