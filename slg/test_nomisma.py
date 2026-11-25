"""Nomisma-Export: Auswahl, RDF-Struktur, VoID, Fundkontexte und Dateicache."""
import tempfile
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, FOAF, RDF, RDFS, XSD

from .models import Faelschung, Herstellung, Muenztyp, Obj, Obj_Ref, Objekttyp, Paket, Ref, Slg, Workflow
from .nomisma_rdf import count_exportable, is_type_series_uri, nomisma_readiness
from .signals import disable_mtoa_sync, enable_mtoa_sync

NMO = Namespace('http://nomisma.org/ontology#')
VOID = Namespace('http://rdfs.org/ns/void#')
CRM = Namespace('http://www.cidoc-crm.org/cidoc-crm/')
GEO = Namespace('http://www.w3.org/2003/01/geo/wgs84_pos#')
BASE = 'https://example.test'
OCRE = 'http://numismatics.org/ocre/id/ric.2_1(2).dom.101'


@override_settings(ELIGIUS_NOMISMA_CACHE_DIR=tempfile.mkdtemp(), ELIGIUS_NOMISMA_CACHE_SECONDS=0)
class NomismaExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        disable_mtoa_sync()
        try:
            cls.controlled = Workflow.objects.create(name='kontrolliert', reihenfolge=1)
            cls.draft = Workflow.objects.create(name='Entwurf', reihenfolge=2)
            Herstellung.objects.create(id=1, name='Geprägt')
            Objekttyp.objects.create(id=1, name='Münze')
            cls.slg = Slg.objects.create(
                name='Stift Heiligenkreuz', beschreibung='Die Münzsammlung des Stiftes.',
                bildurl='https://images.example.test/', bild_endung_av='_a', bild_endung_rv='_r',
                nomisma_export_erlaubt=True, nomisma_collection_uri='http://nomisma.org/id/heiligenkreuz',
                kulturpool_metadata_rights_uri='http://creativecommons.org/publicdomain/zero/1.0/')
            cls.typ = Muenztyp.objects.create(muenztyptitel='RIC II.1 Domitian 101', titel='Domitianus',
                                             link=OCRE, workflow=cls.controlled)
            cls.ref = Ref.objects.create(zitat='RIC', abk='RIC')
        finally:
            enable_mtoa_sync()

    def setUp(self):
        cache.clear()
        disable_mtoa_sync()
        self.addCleanup(enable_mtoa_sync)

    def obj(self, invnr, **kwargs):
        values = dict(Slg=self.slg, Typ=self.typ, workflow=self.controlled, gewicht=Decimal('3.21'),
                      durchmesser=Decimal('19.5'), stempelstellung=6)
        values.update(kwargs)
        return Obj.objects.create(invnr=invnr, **values)

    def dump(self):
        response = self.client.get(reverse('collection_nomisma_rdf', kwargs={'id': self.slg.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/rdf+xml; charset=utf-8')
        content = b''.join(response.streaming_content) if response.streaming else response.content
        graph = Graph()
        graph.parse(data=content, format='xml')
        return graph, content

    def uri(self, obj):
        return URIRef(f'{BASE}/objekt/{obj.id}/')

    def test_requires_collection_opt_in(self):
        Slg.objects.filter(pk=self.slg.pk).update(nomisma_export_erlaubt=False)
        self.assertEqual(self.client.get(reverse('collection_nomisma_rdf', kwargs={'id': self.slg.id})).status_code, 404)
        self.assertEqual(self.client.get(reverse('collection_nomisma_void', kwargs={'id': self.slg.id})).status_code, 404)

    def test_void_dataset(self):
        self.obj('H1')
        graph, _ = self.dump()
        dataset = URIRef(f'{BASE}/slg/{self.slg.id}/')
        self.assertIn((dataset, RDF.type, VOID.Dataset), graph)
        self.assertIn((dataset, DCTERMS.title, Literal('Eligius – Stift Heiligenkreuz', lang='de')), graph)
        self.assertIn((dataset, DCTERMS.description, Literal('Die Münzsammlung des Stiftes.', lang='de')), graph)
        self.assertIn((dataset, DCTERMS.publisher, Literal('Stift Heiligenkreuz')), graph)
        self.assertIn((dataset, DCTERMS.license, URIRef('http://creativecommons.org/publicdomain/zero/1.0/')), graph)
        self.assertIn((dataset, VOID.uriSpace, Literal(f'{BASE}/objekt/')), graph)
        self.assertIn((dataset, VOID.dataDump, URIRef(f'{BASE}/slg/{self.slg.id}/nomisma.rdf')), graph)
        void = Graph().parse(data=self.client.get(f'/slg/{self.slg.id}/void.rdf').content, format='xml')
        self.assertIn((dataset, VOID.dataDump, URIRef(f'{BASE}/slg/{self.slg.id}/nomisma.rdf')), void)

    def test_coin(self):
        obj = self.obj('H1')
        graph, _ = self.dump()
        coin = self.uri(obj)
        self.assertIn((coin, RDF.type, NMO.NumismaticObject), graph)
        self.assertIn((coin, DCTERMS.title, Literal('Domitianus', lang='de')), graph)
        self.assertIn((coin, DCTERMS.identifier, Literal('H1')), graph)
        self.assertIn((coin, NMO.hasCollection, URIRef('http://nomisma.org/id/heiligenkreuz')), graph)
        self.assertIn((coin, NMO.hasTypeSeriesItem, URIRef(OCRE)), graph)
        self.assertIn((coin, NMO.hasAxis, Literal(6, datatype=XSD.integer)), graph)
        self.assertIn((coin, NMO.hasWeight, Literal('3.21', datatype=XSD.decimal)), graph)
        self.assertIn((coin, NMO.hasDiameter, Literal('19.5', datatype=XSD.decimal)), graph)
        self.assertIn((coin, VOID.inDataset, URIRef(f'{BASE}/slg/{self.slg.id}/')), graph)
        obverse = URIRef(f'{coin}#obverse')
        self.assertIn((coin, NMO.hasObverse, obverse), graph)
        # Wie bei Kulturpool: stabile Weiterleitungs-URIs, die auf die aktuelle Bilddatei zeigen.
        self.assertIn((obverse, FOAF.depiction, URIRef(f'{BASE}/bild/{obj.id}/av/')), graph)
        self.assertIn((obverse, FOAF.thumbnail, URIRef(f'{BASE}/bild/{obj.id}/av-vorschau/')), graph)
        self.assertIn((URIRef(f'{coin}#reverse'), FOAF.depiction, URIRef(f'{BASE}/bild/{obj.id}/rv/')), graph)

    @override_settings(ELIGIUS_OAI_IMAGE_REDIRECTS=False)
    def test_direct_image_files(self):
        obj = self.obj('H1')
        graph, _ = self.dump()
        obverse = URIRef(f'{self.uri(obj)}#obverse')
        self.assertIn((obverse, FOAF.depiction, URIRef('https://images.example.test/H1_a.jpg')), graph)

    def test_without_images_no_side_nodes(self):
        Slg.objects.filter(pk=self.slg.pk).update(bildurl='')
        obj = self.obj('H1')
        graph, _ = self.dump()
        self.assertIsNone(graph.value(self.uri(obj), NMO.hasObverse))

    def test_selection(self):
        ok = self.obj('OK')
        self.obj('DRAFT', workflow=self.draft)
        self.obj('FAKE', faelschung=Faelschung.objects.create(name='Moderne Fälschung'))
        self.obj('UNSURE', Typ_unsicher=True)
        draft_typ = Muenztyp.objects.create(muenztyptitel='Entwurf', link=OCRE + 'x', workflow=self.draft)
        self.obj('TYPDRAFT', Typ=draft_typ)
        variant = self.obj('VARIANT')
        Obj_Ref.objects.create(idfk_Obj=variant, idfk_Ref=self.ref, nummer='1', nach=True, link=OCRE)
        no_link = Muenztyp.objects.create(muenztyptitel='Ohne Link', workflow=self.controlled)
        self.obj('NOLINK', Typ=no_link)
        _, content = self.dump()
        self.assertIn(f'/objekt/{ok.id}/'.encode(), content)
        for invnr in ('DRAFT', 'FAKE', 'UNSURE', 'TYPDRAFT', 'VARIANT', 'NOLINK'):
            self.assertNotIn(f'>{invnr}<'.encode(), content, invnr)

    def test_type_variant_uses_exact_object_reference(self):
        variant_typ = Muenztyp.objects.create(muenztyptitel='RIC 101 var.', link=OCRE, nach=True,
                                              workflow=self.controlled)
        plain = self.obj('VARTYP', Typ=variant_typ)
        exact = self.obj('VARTYP-REF', Typ=variant_typ)
        Obj_Ref.objects.create(idfk_Obj=exact, idfk_Ref=self.ref, nummer='102', nach=False,
                               link='http://numismatics.org/ocre/id/ric.2_1(2).dom.102')
        graph, _ = self.dump()
        self.assertNotIn((self.uri(plain), RDF.type, NMO.NumismaticObject), graph)
        self.assertIn((self.uri(exact), NMO.hasTypeSeriesItem,
                       URIRef('http://numismatics.org/ocre/id/ric.2_1(2).dom.102')), graph)

    def test_mir_and_lrbc_concordances_export_the_ocre_type(self):
        coins = []
        for citation in ('MIR 36,43,44', 'LRBC'):
            primary = Muenztyp.objects.create(muenztyptitel=f'{citation} 1', workflow=self.controlled,
                                               Ref=Ref.objects.create(abk=citation), nummer='1')
            self.typ.Konkordanz.add(primary)
            coins.append(self.obj(citation, Typ=primary))
        graph, _ = self.dump()
        for coin in coins:
            self.assertEqual(list(graph.objects(self.uri(coin), NMO.hasTypeSeriesItem)), [URIRef(OCRE)])
        self.assertEqual(count_exportable(self.slg), 2)
        image = self.client.get(f'/bild/{coins[0].pk}/av/')
        self.assertRedirects(image, 'https://images.example.test/MIR%2036,43,44_a.jpg',
                             fetch_redirect_response=False)

    def test_concordance_requires_a_unique_controlled_non_variant_ocre_type(self):
        primary = Muenztyp.objects.create(muenztyptitel='MIR 1', workflow=self.controlled)
        coin = self.obj('MIR1', Typ=primary)
        draft = Muenztyp.objects.create(muenztyptitel='RIC draft', link=OCRE, workflow=self.draft)
        variant = Muenztyp.objects.create(muenztyptitel='RIC variant', link=OCRE, workflow=self.controlled, nach=True)
        unlinked = Muenztyp.objects.create(muenztyptitel='RIC without link', workflow=self.controlled)
        non_type = Muenztyp.objects.create(muenztyptitel='RIC invalid link', link='https://numismatics.org/ocre/id/',
                                          workflow=self.controlled)
        primary.Konkordanz.add(draft, variant, unlinked, non_type)
        self.assertEqual(count_exportable(self.slg), 0)

        duplicate = Muenztyp.objects.create(muenztyptitel='RIC duplicate', link=OCRE.replace('http:', 'https:'),
                                           workflow=self.controlled)
        primary.Konkordanz.add(self.typ, duplicate)
        self.assertEqual(count_exportable(self.slg), 1)

        other_uri = 'http://numismatics.org/ocre/id/ric.2_1(2).dom.102'
        other = Muenztyp.objects.create(muenztyptitel='RIC 102', link=other_uri, workflow=self.controlled)
        primary.Konkordanz.add(other)
        graph, _ = self.dump()
        self.assertNotIn((self.uri(coin), RDF.type, NMO.NumismaticObject), graph)
        self.assertEqual(count_exportable(self.slg), 0)

        Obj_Ref.objects.create(idfk_Obj=coin, idfk_Ref=self.ref, nummer='102', nach=False, link=other_uri)
        graph, _ = self.dump()
        self.assertEqual(graph.value(self.uri(coin), NMO.hasTypeSeriesItem), URIRef(other_uri))
        self.assertEqual(count_exportable(self.slg), 1)

    def test_primary_type_variant_does_not_inherit_ocre_link(self):
        variant = Muenztyp.objects.create(muenztyptitel='LRBC 1 var.', workflow=self.controlled, nach=True)
        variant.Konkordanz.add(self.typ)
        coin = self.obj('LRBC1', Typ=variant)
        graph, _ = self.dump()
        self.assertNotIn((self.uri(coin), RDF.type, NMO.NumismaticObject), graph)
        self.assertEqual(count_exportable(self.slg), 0)

    def test_type_series_hosts(self):
        self.assertTrue(is_type_series_uri('http://numismatics.org/crro/id/rrc-476.1b'))
        self.assertTrue(is_type_series_uri('https://www.corpus-nummorum.eu/types/29'))
        self.assertFalse(is_type_series_uri('https://numismatics.org/collection/1944.100.26728'))
        self.assertFalse(is_type_series_uri('https://numismatics.org/ocre/id/'))
        self.assertFalse(is_type_series_uri('https://rpc.ashmus.ox.ac.uk/type/74718'))
        self.assertFalse(is_type_series_uri('https://rpc.ashmus.ox.ac.uk/coins/1/3340'))
        self.assertFalse(is_type_series_uri('https://numismatics.org.evil.test/ocre/id/x'))
        self.assertFalse(is_type_series_uri('https://www.google.com/?q=numismatics.org'))

    def test_hoard_and_findspot(self):
        hoard = Paket.objects.create(name='Schatzfund Carnuntum', online_freigegeben=True,
                                     kontexttyp=Paket.KONTEXTTYP_HORTFUND,
                                     fund_lat=Decimal('48.116000'), fund_lng=Decimal('16.867000'))
        site = Paket.objects.create(name='Fundplatz Tulln', online_freigegeben=True,
                                    kontexttyp=Paket.KONTEXTTYP_FUNDKONTEXT)
        hidden = Paket.objects.create(name='Intern', online_freigegeben=False, kontexttyp=Paket.KONTEXTTYP_HORTFUND)
        in_hoard, single = self.obj('HORT'), self.obj('EINZEL')
        in_hoard.pakete.add(hoard, hidden)
        single.pakete.add(site)
        graph, content = self.dump()
        hoard_uri = URIRef(f'{BASE}/pakete/{hoard.slug}/#hoard')
        self.assertIn((self.uri(in_hoard), DCTERMS.isPartOf, hoard_uri), graph)
        self.assertIn((hoard_uri, RDF.type, NMO.Hoard), graph)
        self.assertIn((hoard_uri, NMO.hasFindspot, URIRef(f'{BASE}/pakete/{hoard.slug}/#find')), graph)
        place = URIRef(f'{BASE}/pakete/{hoard.slug}/#place')
        self.assertIn((URIRef(f'{BASE}/pakete/{hoard.slug}/#find'), CRM.P7_took_place_at, place), graph)
        location = graph.value(place, GEO.location)
        self.assertEqual(graph.value(location, GEO.lat), Literal('48.116000', datatype=XSD.decimal))
        self.assertIn((self.uri(single), NMO.hasFindspot, URIRef(f'{BASE}/pakete/{site.slug}/#find')), graph)
        self.assertNotIn(hidden.slug.encode(), content)
        self.assertEqual(content.count(f'rdf:about="{BASE}/pakete/{hoard.slug}/#find"'.encode()), 1)

    def test_xml_escaping(self):
        obj = self.obj('A&B<1>')
        graph, _ = self.dump()
        self.assertIn((self.uri(obj), DCTERMS.identifier, Literal('A&B<1>')), graph)

    def test_file_cache(self):
        self.obj('H1')
        with override_settings(ELIGIUS_NOMISMA_CACHE_SECONDS=3600):
            first = self.client.get(f'/slg/{self.slg.id}/nomisma.rdf')
            self.assertTrue(first.streaming)  # aus Datei
            b''.join(first.streaming_content)
            self.obj('H2')
            cached = b''.join(self.client.get(f'/slg/{self.slg.id}/nomisma.rdf').streaming_content)
            self.assertNotIn(b'>H2<', cached)
        fresh = b''.join(self.client.get(f'/slg/{self.slg.id}/nomisma.rdf').streaming_content)
        self.assertIn(b'>H2<', fresh)

    @override_settings(ELIGIUS_PUBLIC_BASE_URL='')
    def test_without_public_base_url_no_cache(self):
        self.obj('H1')
        response = self.client.get(f'/slg/{self.slg.id}/nomisma.rdf')
        self.assertFalse(response.streaming)
        self.assertIn(b'http://testserver/objekt/', response.content)

    def test_readiness(self):
        self.assertEqual(nomisma_readiness(self.slg), [
            'Keine exportierbaren Münzen (kontrolliert, mit Link auf OCRE/CRRO-Typ o. Ä.)'])
        self.obj('H1')
        self.assertEqual(nomisma_readiness(self.slg), [])
        bare = Slg.objects.create(name='Leer', nomisma_export_erlaubt=True)
        self.assertEqual(len(nomisma_readiness(bare)), 3)
