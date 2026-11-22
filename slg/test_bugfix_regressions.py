"""Regressionstests zur Fehlerliste vom 21.11.2026 (Caching, Nomisma, Admin, MTOA, Endpunkte, Serializer)."""
import tempfile
import threading
from decimal import Decimal

import tablib
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from .admin import ObjImport, ObjPaketZuweisungResource, SlgInformationAdmin
from .models import (AvBildtyp, AvBildtyp_Schlagwort, Herstellung, Katalog, Metall, MtoaPerson, Muenztyp,
                     MuenztypObjektAnzeige, Mztyp_Person, Nominal, Obj, Obj_Person, Objekttyp, Paket, Person,
                     PersonFunktion, Schlagwort, Slg, SlgInformation, SlgTeil, Workflow)
from .mtoa_sync import fit_lengths, sync_objs_to_mtoa
from .nomisma_rdf import _image_uri
from .serializers import CoinImageSerializer, LatestObjSerializer
from .signals import mtoa_sync_is_disabled, mtoa_sync_paused
from .translation_resources import MetallTranslationResource

OCRE = 'http://numismatics.org/ocre/id/ric.2_1(2).dom.101'


class Fixtures:
    @classmethod
    def base_data(cls):
        cls.controlled = Workflow.objects.create(name='kontrolliert', reihenfolge=1)
        cls.draft = Workflow.objects.create(id=2, name='Entwurf', reihenfolge=2)
        Herstellung.objects.create(id=1, name='Geprägt')
        Objekttyp.objects.create(id=1, name='Münze')
        cls.ruler_fn = PersonFunktion.objects.create(id=1, name='Prägeherr')
        cls.depicted_fn = PersonFunktion.objects.create(id=2, name='Dargestellt')
        cls.slg = Slg.objects.create(name='Sammlung A', bildurl='https://img.example.test/',
                                     bild_endung_av='_a', bild_endung_rv='_r')
        cls.typ = Muenztyp.objects.create(muenztyptitel='RIC 101', titel='Domitian', link=OCRE,
                                          workflow=cls.controlled)


class CachedPagesCsrfTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()

    def setUp(self):
        cache.clear()

    def test_cached_page_never_serves_foreign_token_without_cookie(self):
        first = Client(enforce_csrf_checks=True).get('/about/')
        self.assertEqual(first.status_code, 200)
        self.assertIn('Cookie', first.get('Vary', ''))
        # Ein neuer Besucher ohne Cookie bekommt ein eigenes CSRF-Cookie, kein gecachtes Fremd-Token.
        second = Client(enforce_csrf_checks=True).get('/about/')
        self.assertIn('csrftoken', second.cookies)


@override_settings(ELIGIUS_NOMISMA_CACHE_DIR=tempfile.mkdtemp(), ELIGIUS_NOMISMA_CACHE_SECONDS=0,
                   ELIGIUS_OAI_IMAGE_REDIRECTS=True)
class NomismaImageTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        Slg.objects.filter(pk=cls.slg.pk).update(nomisma_export_erlaubt=True, kulturpool_export_erlaubt=False)
        cls.slg.refresh_from_db()
        cls.obj = Obj.objects.create(invnr='H 1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)

    def test_redirect_serves_nomisma_only_collection_both_sides(self):
        for side in ('av', 'rv', 'av-vorschau'):
            response = self.client.get(reverse('bild_weiterleitung', kwargs={'obj_id': self.obj.pk, 'ansicht': side}))
            self.assertEqual(response.status_code, 302, side)
            self.assertIn('H%201', response['Location'])

    def test_redirect_still_404_without_any_export_permission(self):
        Slg.objects.filter(pk=self.slg.pk).update(nomisma_export_erlaubt=False)
        response = self.client.get(reverse('bild_weiterleitung', kwargs={'obj_id': self.obj.pk, 'ansicht': 'av'}))
        self.assertEqual(response.status_code, 404)

    @override_settings(ELIGIUS_OAI_IMAGE_REDIRECTS=False)
    def test_direct_file_uri_is_percent_encoded(self):
        request = RequestFactory().get('/')
        uri = _image_uri(self.obj, request, 'av', 'https://img.example.test/H 1_a.jpg')
        self.assertEqual(uri, 'https://img.example.test/H%201_a.jpg')


class AdminRegressionTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.su = User.objects.create_superuser('su', 'su@x.test', 'pw')
        cls.viewer = User.objects.create_user('viewer', 'v@x.test', 'pw', is_staff=True)
        cls.viewer.user_permissions.set(Permission.objects.filter(codename__startswith='view_'))
        cls.obj = Obj.objects.create(invnr='A1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        cls.untyped = Obj.objects.create(invnr='A2', Slg=cls.slg, workflow=cls.controlled)
        cls.person = Person.objects.create(name='Domitian')

    def test_slginformation_admin_is_complete(self):
        model_admin = admin.site._registry[SlgInformation]
        self.assertIsInstance(model_admin, SlgInformationAdmin)
        self.assertIn('raw_personen', model_admin.search_fields)
        self.assertEqual(model_admin.raw_id_fields, ['person'])

    def test_search_on_fund_and_mtoa_does_not_crash(self):
        self.client.force_login(self.su)
        for name in ('admin:slg_fund_changelist', 'admin:slg_muenztypobjektanzeige_changelist'):
            self.assertEqual(self.client.get(reverse(name), {'q': 'A1'}).status_code, 200, name)

    def test_typ_filter_uses_null_checks(self):
        self.client.force_login(self.su)
        response = self.client.get(reverse('admin:slg_obj_changelist'), {'Typ__isempty': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([o.pk for o in response.context['cl'].queryset], [self.untyped.pk])

    def test_view_only_change_views(self):
        self.client.force_login(self.viewer)
        katalog = Katalog.objects.create(titel='Katalog', tafelteil=False)
        for name, pk in (('slg_person', self.person.pk), ('slg_muenztyp', self.typ.pk),
                         ('slg_obj', self.obj.pk), ('slg_katalog', katalog.pk)):
            response = self.client.get(reverse(f'admin:{name}_change', args=[pk]))
            self.assertEqual(response.status_code, 200, name)

    def test_obj_import_dry_run_with_import_export_4(self):
        dataset = tablib.Dataset(headers=['id', 'invnr', 'Sammlung', 'Sammlungsteil', 'Münztyp', 'TempTyp',
                                          'durchmesser', 'gewicht', 'stempelstellung', 'abnutzung'])
        dataset.append(['', 'A1', 'Sammlung A', '', '', '', '20', '', '', ''])
        result = ObjImport().import_data(dataset, dry_run=True)
        self.assertFalse(result.has_errors(), [e.error for e in result.base_errors])
        self.assertFalse(mtoa_sync_is_disabled())

        result = ObjImport().import_data(dataset, dry_run=False)
        self.assertFalse(result.has_errors(), [e.error for e in result.base_errors])
        self.assertEqual(Obj.objects.get(pk=self.obj.pk).durchmesser, Decimal('20'))
        self.assertEqual(MuenztypObjektAnzeige.objects.get(obj_id=self.obj.pk).durchmesser, Decimal('20'))
        self.assertFalse(mtoa_sync_is_disabled())

    def test_paket_import_reports_rows_and_creates_slug(self):
        other = Slg.objects.create(name='Sammlung B')
        teil_a = SlgTeil.objects.create(name='Teil', idfk_Slg_SlgTeil=self.slg)
        SlgTeil.objects.create(name='Teil', idfk_Slg_SlgTeil=other)  # gleicher Name, andere Sammlung
        in_teil = Obj.objects.create(invnr='T1', Slg=self.slg, SlgTeil=teil_a, workflow=self.controlled)
        dataset = tablib.Dataset(headers=['invnr', 'Sammlung', 'Sammlungsteil', 'Paket'])
        dataset.append(['T1', 'Sammlung A', 'Teil', 'Neues Paket'])
        dataset.append(['FEHLT', 'Sammlung A', '', 'Neues Paket'])
        dataset.append(['', 'Sammlung A', '', 'Neues Paket'])

        preview = ObjPaketZuweisungResource().import_data(dataset, dry_run=True)
        self.assertEqual([row.number for row in preview.invalid_rows], [3, 2])
        self.assertFalse(Paket.objects.filter(name='Neues Paket').exists())

        result = ObjPaketZuweisungResource().import_data(dataset, dry_run=False)
        paket = Paket.objects.get(name='Neues Paket')
        self.assertTrue(paket.slug)
        self.assertEqual(list(in_teil.pakete.all()), [paket])
        self.assertTrue(all(error.error for error in result.base_errors))

    def test_translation_import_with_non_numeric_id_does_not_raise(self):
        metall = Metall.objects.create(name='Gold')
        dataset = tablib.Dataset(headers=['id', 'name', 'name_en', 'revision'])
        dataset.append(['abc', 'Gold', 'Gold', 'x'])
        dataset.append([metall.pk, 'Gold', 'Gold', 'x'])
        result = MetallTranslationResource().import_data(dataset, dry_run=True)
        self.assertTrue(result.has_errors())


class MtoaRegressionTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()

    def test_deleting_object_removes_projection(self):
        obj = Obj.objects.create(invnr='D1', Slg=self.slg, workflow=self.controlled)
        self.assertTrue(MuenztypObjektAnzeige.objects.filter(obj_id=obj.pk).exists())
        obj_id = obj.pk
        obj.delete()
        self.assertFalse(MuenztypObjektAnzeige.objects.filter(obj_id=obj_id).exists())

    def test_sync_removes_orphans_and_is_idempotent(self):
        obj = Obj.objects.create(invnr='D2', Slg=self.slg, workflow=self.controlled)
        MuenztypObjektAnzeige.objects.create(obj_id=999999, invnr='GHOST')
        sync_objs_to_mtoa([obj.pk, 999999])
        sync_objs_to_mtoa([obj.pk])
        self.assertEqual(MuenztypObjektAnzeige.objects.filter(obj_id=obj.pk).count(), 1)
        self.assertFalse(MuenztypObjektAnzeige.objects.filter(obj_id=999999).exists())

    def test_force_with_since_keeps_other_projections(self):
        old = Obj.objects.create(invnr='OLD', Slg=self.slg, workflow=self.controlled)
        Obj.objects.filter(pk=old.pk).update(modified_at='2000-01-01T00:00:00Z')
        Obj.objects.create(invnr='NEW', Slg=self.slg, workflow=self.controlled)
        call_command('sync_mtoa', since='2020-01-01', force=True, verbosity=0)
        self.assertTrue(MuenztypObjektAnzeige.objects.filter(obj_id=old.pk).exists())

    def test_typed_object_keeps_object_persons(self):
        ruler = Person.objects.create(name='Domitian')
        moneyer = Person.objects.create(name='Münzmeister')
        Mztyp_Person.objects.create(Mztyp=self.typ, idfk_Person=ruler, idfk_PersonFunktion=self.ruler_fn, appears_on_rev=False)
        obj = Obj.objects.create(invnr='P1', Slg=self.slg, Typ=self.typ, workflow=self.controlled)
        Obj_Person.objects.create(idfk_Obj=obj, idfk_Person=moneyer, idfk_PersonFunktion=self.ruler_fn, appears_on_rev=False)
        persons = set(MtoaPerson.objects.filter(mtoa__obj_id=obj.pk).values_list('person_id', flat=True))
        self.assertEqual(persons, {ruler.pk, moneyer.pk})

    def test_keyword_link_change_updates_projection(self):
        bildtyp = AvBildtyp.objects.create(name='Victoria')
        obj = Obj.objects.create(invnr='K1', Slg=self.slg, av_bildtyp=bildtyp, workflow=self.controlled)
        AvBildtyp_Schlagwort.objects.create(avbildtyp=bildtyp, schlagwort=Schlagwort.objects.create(name='Kranz'))
        self.assertEqual(MuenztypObjektAnzeige.objects.get(obj_id=obj.pk).av_schlagworte, 'Kranz')

    def test_bulk_admin_action_syncs_projection(self):
        gold = Metall.objects.create(pk=9, name='Kupfer')
        obj = Obj.objects.create(invnr='B1', Slg=self.slg, Typ=self.typ, workflow=self.controlled)
        admin.site._registry[Muenztyp].verkupfern(None, Muenztyp.objects.filter(pk=self.typ.pk))
        self.assertEqual(MuenztypObjektAnzeige.objects.get(obj_id=obj.pk).metall, gold.name)

    def test_long_vocabulary_names_are_stored(self):
        long_name = 'N' * 200
        obj = Obj.objects.create(invnr='L1', Slg=self.slg, workflow=self.controlled,
                                 idfk_Nominal=Nominal.objects.create(name=long_name))
        self.assertEqual(MuenztypObjektAnzeige.objects.get(obj_id=obj.pk).nominal, long_name)
        self.assertEqual(len(fit_lengths({'invnr': 'x' * 50})['invnr']), 20)

    def test_vocabulary_delete_is_protected(self):
        metall = Metall.objects.create(name='Silber')
        Obj.objects.create(invnr='M1', Slg=self.slg, Metall=metall, workflow=self.controlled)
        with self.assertRaises(ProtectedError):
            metall.delete()
        self.assertTrue(Obj.objects.filter(invnr='M1').exists())

    def test_sync_pause_is_local_to_thread(self):
        seen = []
        with mtoa_sync_paused():
            worker = threading.Thread(target=lambda: seen.append(mtoa_sync_is_disabled()))
            worker.start()
            worker.join()
            self.assertTrue(mtoa_sync_is_disabled())
        self.assertEqual(seen, [False])
        self.assertFalse(mtoa_sync_is_disabled())


class EndpointRegressionTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.obj = Obj.objects.create(invnr='A1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)
        Obj.objects.create(invnr='DUP', Slg=cls.slg, workflow=cls.controlled)
        Obj.objects.create(invnr='DUP', Slg=Slg.objects.create(name='B'), workflow=cls.controlled)
        cls.su = User.objects.create_superuser('su', 'su@x.test', 'pw')

    def setUp(self):
        cache.clear()

    def test_invalid_parameters_are_client_errors(self):
        cases = {
            '/browse/?Slg=abc': 200, '/browse/?dat_von=None': 200, '/browse/?dat_bis=xyz': 200,
            '/browse/?Slg=999999': 200, '/api/cycle-coin/?type_id=abc&current_obj_id=1': 400,
            '/api/ereignisse/?von=abc': 400, '/objekt_detail_partial/': 404,
            f'/objekt_detail_partial/?id={self.obj.pk}': 200, '/avschlagwort/': 200,
            f'/api/muenzen/{self.obj.pk}/kontext/?Metall=Gold': 200,
        }
        for url, status in cases.items():
            self.assertEqual(self.client.get(url).status_code, status, url)

    def test_ambiguous_inventory_number_is_conflict(self):
        self.client.force_login(self.su)
        self.assertEqual(self.client.get('/api/objekt/DUP/').status_code, 409)
        self.assertEqual(self.client.get(f'/api/objekt/DUP/?slg={self.slg.pk}').status_code, 200)

    def test_staff_endpoints(self):
        self.client.force_login(self.su)
        for url in (f'/catalog/generate/?obj_ids={self.obj.pk}', '/export-obj-lsno/', '/create/',
                    f'/id/{self.obj.pk}/edit/'):
            self.assertLess(self.client.get(url).status_code, 400, url)

    def test_lsno_export_values(self):
        from .resources import ObjLSNOResource
        Herstellung.objects.create(id=2, name='Gegossen')
        obj = Obj.objects.create(invnr='X1', Slg=self.slg, workflow=self.controlled, idfk_Herstellung_id=2,
                                 Metall=Metall.objects.create(name='Gold'))
        resource = ObjLSNOResource()
        self.assertEqual(resource.dehydrate_Typ__Herstellung__name(obj), 'Gegossen')
        self.assertEqual(resource.dehydrate_Bereich(obj), 'RA-Münzen-Gold')

    def test_muenztyp_save_with_variant(self):
        from .models import Variantenbeschr
        typ = Muenztyp(variante=Variantenbeschr.objects.create(name='Stern'), workflow=self.controlled)
        typ.save()
        self.assertTrue(typ.muenztyptitel.endswith('var.Stern'))


class SerializerRegressionTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.person = Person.objects.create(name='Domitian')
        Mztyp_Person.objects.create(Mztyp=cls.typ, idfk_Person=cls.person, idfk_PersonFunktion=cls.depicted_fn,
                                    appears_on_rev=False)
        cls.typ.av_bildtyp = AvBildtyp.objects.create(name='Kopf')
        cls.typ.save()
        AvBildtyp_Schlagwort.objects.create(avbildtyp=cls.typ.av_bildtyp, schlagwort=Schlagwort.objects.create(name='Lorbeer'))
        cls.obj = Obj.objects.create(invnr='S1', Slg=cls.slg, Typ=cls.typ, workflow=cls.controlled)

    def test_latest_serializer_returns_persons_and_keywords(self):
        data = LatestObjSerializer(self.obj).data
        self.assertEqual(data['typ_personen_mit_funktion'][0]['person']['name'], 'Domitian')
        self.assertEqual([s['name'] for s in data['av_schlagworte']], ['Lorbeer'])

    def test_coin_images_are_serialized(self):
        data = CoinImageSerializer(self.obj).data
        self.assertTrue(data['images']['av'].endswith('S1_a.jpg') or data['images']['av'])
        response = self.client.get('/person_coin_images/', {'name': 'Domi'})
        self.assertEqual(response.status_code, 200)
        coins = response.json()['results'][0]['coins']
        self.assertTrue(coins[0]['images'])
