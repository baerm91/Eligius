from datetime import datetime, timezone as datetime_timezone

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rdflib import Graph, Namespace, URIRef

from .models import Metall, Muenztyp, MuenztypObjektAnzeige, Nominal, Obj, Obj_Ref, Ref, Slg, Workflow
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


class FacetApiTests(TestCase):
    def test_nominal_selected_count_uses_current_filtered_result_set(self):
        nominal = Nominal.objects.create(name="Groschen, 2")
        other_nominal = Nominal.objects.create(name="Pfennig")
        slg = Slg.objects.create(name="Testsammlung")
        other_slg = Slg.objects.create(name="Andere Sammlung")

        MuenztypObjektAnzeige.objects.create(
            obj_id=1,
            invnr="1",
            nominal="Groschen, 2",
            nominal_fk=nominal,
            slg_fk=slg,
        )
        MuenztypObjektAnzeige.objects.create(
            obj_id=2,
            invnr="2",
            nominal="Groschen, 2",
            nominal_fk=nominal,
            slg_fk=slg,
        )
        MuenztypObjektAnzeige.objects.create(
            obj_id=3,
            invnr="3",
            nominal="Pfennig",
            nominal_fk=other_nominal,
            slg_fk=slg,
        )
        MuenztypObjektAnzeige.objects.create(
            obj_id=4,
            invnr="4",
            nominal="Groschen, 2",
            nominal_fk=nominal,
            slg_fk=other_slg,
        )

        response = self.client.get(
            reverse("facet_api"),
            {
                "facet": "Nominal",
                "Slg": str(slg.id),
                "Nominal": "Groschen, 2",
                "include_current_facet": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"name": "Groschen, 2", "count": 2, "id": nominal.id}])


class NomismaRdfExportTests(TestCase):
    def setUp(self):
        self.controlled = Workflow.objects.create(name="kontrolliert", reihenfolge=1)
        self.draft = Workflow.objects.create(name="Entwurf", reihenfolge=2)
        self.slg = Slg.objects.create(
            name="Testsammlung",
            bildurl="https://example.org/images/",
            bild_endung_av="_av",
            bild_endung_rv="_rv",
            nomisma_export_erlaubt=True,
            nomisma_collection_uri="http://nomisma.org/id/test_collection",
        )
        self.typ = Muenztyp.objects.create(
            muenztyptitel="Typ 1",
            titel="Kontrollierter Typ",
            link="http://numismatics.org/pco/id/cpe.1_1.518",
            Objekttyp=None,
            Herstellung=None,
            workflow=self.controlled,
        )

    def _create_obj(self, invnr, workflow=None, typ=None):
        disable_mtoa_sync()
        try:
            return Obj.objects.create(
                invnr=invnr,
                Slg=self.slg,
                Typ=typ or self.typ,
                workflow=workflow or self.controlled,
                Objekttyp=None,
                durchmesser="28.0",
                gewicht="14.02",
                stempelstellung=12,
            )
        finally:
            enable_mtoa_sync()

    def test_nomisma_rdf_requires_collection_opt_in(self):
        self.slg.nomisma_export_erlaubt = False
        self.slg.save(update_fields=["nomisma_export_erlaubt"])

        response = self.client.get(reverse("collection_nomisma_rdf", kwargs={"id": self.slg.id}))

        self.assertEqual(response.status_code, 404)

    def test_nomisma_rdf_exports_expected_core_triples(self):
        obj = self._create_obj("ID147")

        response = self.client.get(reverse("collection_nomisma_rdf", kwargs={"id": self.slg.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rdf+xml; charset=utf-8")

        graph = Graph()
        graph.parse(data=response.content, format="xml")
        nmo = Namespace("http://nomisma.org/ontology#")
        dcterms = Namespace("http://purl.org/dc/terms/")
        foaf = Namespace("http://xmlns.com/foaf/0.1/")
        obj_uri = URIRef(f"http://testserver{obj.get_absolute_url()}")
        obverse_uri = URIRef(f"{obj_uri}#obverse")

        self.assertIn((obj_uri, dcterms.identifier, None), graph)
        self.assertIn((obj_uri, nmo.hasCollection, URIRef("http://nomisma.org/id/test_collection")), graph)
        self.assertIn((obj_uri, nmo.hasTypeSeriesItem, URIRef("http://numismatics.org/pco/id/cpe.1_1.518")), graph)
        self.assertIn((obj_uri, nmo.hasObverse, obverse_uri), graph)
        self.assertIn((obverse_uri, foaf.depiction, URIRef("https://example.org/images/ID147_av.jpg")), graph)

    def test_nomisma_rdf_excludes_variant_objects(self):
        obj = self._create_obj("ID148")
        ref = Ref.objects.create(zitat="Referenz")
        Obj_Ref.objects.create(
            idfk_Obj=obj,
            idfk_Ref=ref,
            nummer="1",
            nach=True,
            link="http://numismatics.org/pco/id/cpe.1_2.B175",
        )

        response = self.client.get(reverse("collection_nomisma_rdf", kwargs={"id": self.slg.id}))

        self.assertNotIn(b"ID148", response.content)

    def test_nomisma_rdf_requires_controlled_object_and_type_workflows(self):
        self._create_obj("OBJ-DRAFT", workflow=self.draft)
        draft_typ = Muenztyp.objects.create(
            muenztyptitel="Typ Entwurf",
            titel="Nicht kontrollierter Typ",
            link="http://numismatics.org/pco/id/cpe.1_2.B175",
            Objekttyp=None,
            Herstellung=None,
            workflow=self.draft,
        )
        self._create_obj("TYP-DRAFT", typ=draft_typ)

        response = self.client.get(reverse("collection_nomisma_rdf", kwargs={"id": self.slg.id}))

        self.assertNotIn(b"OBJ-DRAFT", response.content)
        self.assertNotIn(b"TYP-DRAFT", response.content)
