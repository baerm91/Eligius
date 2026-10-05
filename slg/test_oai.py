"""OAI protocol, publication policy, RDF semantics and query-budget regressions."""
from datetime import datetime, timezone as utc_timezone
from io import StringIO
from unittest.mock import patch
from xml.etree import ElementTree as ET

from django.core import signing
from django.contrib import admin
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DC, DCTERMS, RDF, SKOS

from .models import (AvBeizeichen, AvBildtyp, AvOffizin, Herstellung, Metall, MtoaPerson, Muenztyp, MuenztypObjektAnzeige,
                     Mzstaette, Mztyp_Person, Nominal, Obj, Objekttyp, Obj_Person,
                     Obj_Ref, Person, PersonFunktion, Ref, Region, RvBeizeichen, RvBildtyp, RvOffizin, Slg, SlgTeil, Workflow)
from .mtoa_sync import sync_objs_to_mtoa
from .oai.identifiers import identifier, set_spec
from .oai.service import TOKEN_SALT
from .oai.xml import NS
from .signals import disable_mtoa_sync, enable_mtoa_sync

EDM = Namespace(NS['edm'])
ORE = Namespace(NS['ore'])
BASE = 'https://example.test'


class OAIFixtures:
    @classmethod
    def setUpTestData(cls):
        cls.controlled = Workflow.objects.create(name='kontrolliert', reihenfolge=1)
        cls.draft = Workflow.objects.create(name='Entwurf', reihenfolge=2)
        cls.kind = Objekttyp.objects.create(name='Münze', name_nom_id='http://nomisma.org/id/coin')
        cls.manufacture = Herstellung.objects.create(name='Geprägt', name_nom_id='struck')
        cls.material = Metall.objects.create(name='Silber', name_nom_id='http://nomisma.org/id/ar')
        cls.nominal = Nominal.objects.create(name='Denar', name_nom_id='denarius')
        cls.mint = Mzstaette.objects.create(name='Rom', name_nom_id='http://nomisma.org/id/rome', geonames='3169070')
        cls.obverse = AvBildtyp.objects.create(name='Kopf nach rechts')
        cls.reverse = RvBildtyp.objects.create(name='Stehende Gestalt')
        cls.collection = Slg.objects.create(name='Testsammlung', kulturpool_export_erlaubt=True,
                                            bildurl='https://images.example.test/', bild_endung_av='_a', bild_endung_rv='_r')
        cls.private = Slg.objects.create(name='Private Sammlung', nomisma_export_erlaubt=True)
        cls.typ = Muenztyp.objects.create(muenztyptitel='RIC 1', titel='Denar des Augustus',
                                         Nominal=cls.nominal, Metall=cls.material, Mzstaette=cls.mint,
                                         workflow=cls.controlled, Objekttyp=cls.kind, Herstellung=cls.manufacture,
                                         link='http://numismatics.org/ocre/id/ric.1(2).aug.1',
                                         av_bildtyp=cls.obverse, rv_bildtyp=cls.reverse,
                                         avbeschr='Separater Av-Freitext', rvbeschr='Separater Rv-Freitext')
        cls.draft_typ = Muenztyp.objects.create(muenztyptitel='Entwurfstyp', titel='Entwurf',
                                               workflow=cls.draft, Objekttyp=cls.kind, Herstellung=cls.manufacture)

    def obj(self, invnr='A1', **kwargs):
        defaults = dict(Slg=self.collection, workflow=self.controlled, Objekttyp=self.kind, Typ=None)
        defaults.update(kwargs)
        return Obj.objects.create(invnr=invnr, **defaults)

    def request(self, verb, **params):
        response = self.client.get(reverse('oai_endpoint'), dict(verb=verb, **params))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/xml; charset=utf-8')
        root = ET.fromstring(response.content)
        self.assertEqual(root.tag, '{' + NS['oai'] + '}OAI-PMH')
        self.assertRegex(root.findtext('oai:responseDate', namespaces=NS), r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        return root

    def error(self, verb, code, **params):
        root = self.request(verb, **params)
        self.assertEqual(root.find('oai:error', NS).get('code'), code)
        if code in ('badArgument', 'badVerb'):
            self.assertEqual(root.find('oai:request', NS).attrib, {})
        return root

    def graph(self, obj):
        root = self.request('GetRecord', metadataPrefix='edm', identifier=identifier(obj.pk))
        rdf = root.find('oai:GetRecord/oai:record/oai:metadata/rdf:RDF', NS)
        self.assertIsNotNone(rdf)
        return Graph().parse(data=ET.tostring(rdf), format='xml'), root


class OAITests(OAIFixtures, TestCase):
    def test_identify(self):
        root = self.request('Identify')
        node = root.find('oai:Identify', NS)
        self.assertEqual(node.findtext('oai:baseURL', namespaces=NS), BASE + '/oai/')
        self.assertEqual(node.findtext('oai:protocolVersion', namespaces=NS), '2.0')
        self.assertEqual(node.findtext('oai:repositoryName', namespaces=NS), 'Eligius – Kulturpool')
        self.assertEqual(node.findtext('oai:deletedRecord', namespaces=NS), 'no')
        self.assertEqual(node.findtext('oai:granularity', namespaces=NS), 'YYYY-MM-DDThh:mm:ssZ')

    @override_settings(ELIGIUS_PUBLIC_BASE_URL='')
    def test_request_based_base_url(self):
        root = self.request('Identify')
        self.assertEqual(root.findtext('oai:Identify/oai:baseURL', namespaces=NS), 'http://testserver/oai/')

    def test_metadata_formats(self):
        root = self.request('ListMetadataFormats')
        self.assertEqual(root.findall('.//oai:metadataPrefix', NS)[0].text, 'edm')
        self.assertEqual({n.text for n in root.findall('.//oai:metadataPrefix', NS)}, {'edm', 'oai_dc'})
        obj = self.obj()
        self.assertIsNotNone(self.request('ListMetadataFormats', identifier=identifier(obj.pk)).find('oai:ListMetadataFormats', NS))
        self.error('ListMetadataFormats', 'idDoesNotExist', identifier=identifier(999999))

    def test_sets_only_opt_in_and_stable_after_rename(self):
        self.assertFalse(self.private.kulturpool_export_erlaubt)
        root = self.request('ListSets')
        self.assertEqual([n.text for n in root.findall('.//oai:setSpec', NS)], [set_spec(self.collection.pk)])
        self.assertNotIn(self.private.name, ET.tostring(root).decode())
        self.collection.name = 'Neuer Name'
        self.collection.save()
        root = self.request('ListSets')
        self.assertEqual(root.findtext('.//oai:setSpec', namespaces=NS), set_spec(self.collection.pk))
        self.assertEqual(root.findtext('.//oai:setName', namespaces=NS), 'Neuer Name')

    def test_no_set_hierarchy(self):
        Slg.objects.update(kulturpool_export_erlaubt=False)
        self.error('ListSets', 'noSetHierarchy')
        self.error('ListRecords', 'noSetHierarchy', metadataPrefix='edm', set='eligius')

    def test_five_export_rules(self):
        allowed_untyped = self.obj('1', freigabe=False)
        allowed_typed = self.obj('2', Typ=self.typ)
        denied_type = self.obj('3', Typ=self.draft_typ)
        denied_obj = self.obj('4', workflow=self.draft, freigabe=True)
        denied_slg = self.obj('5', Slg=self.private)
        root = self.request('ListRecords', metadataPrefix='edm')
        ids = {n.text for n in root.findall('.//oai:identifier', NS)}
        self.assertEqual(ids, {identifier(allowed_untyped.pk), identifier(allowed_typed.pk)})
        for obj in (denied_type, denied_obj, denied_slg):
            self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=identifier(obj.pk))

    def test_get_record_unknown_and_orphan(self):
        obj = self.obj()
        self.graph(obj)
        for value in ('garbage', identifier(999999), 'oai:other:object:1', identifier(0)):
            self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=value)
        obj.delete()
        self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=identifier(obj.pk or 1))

    def test_stale_collection_or_type_projection_is_not_exported(self):
        obj = self.obj(Typ=self.typ)
        Obj.objects.filter(pk=obj.pk).update(Typ=self.draft_typ)
        self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=identifier(obj.pk))
        Obj.objects.filter(pk=obj.pk).update(Typ=None)
        self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=identifier(obj.pk))
        Obj.objects.filter(pk=obj.pk).update(Typ=self.typ, Slg=self.private)
        self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=identifier(obj.pk))

    def test_controlled_workflow_case_insensitive_and_null_is_denied(self):
        self.controlled.name = 'KONTROLLIERT'
        self.controlled.save()
        self.graph(self.obj())
        obj = self.obj('2', workflow=None)
        self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=identifier(obj.pk))
        self.typ.workflow = None
        self.typ.save()
        obj = self.obj('3', Typ=self.typ)
        self.error('GetRecord', 'idDoesNotExist', metadataPrefix='edm', identifier=identifier(obj.pk))

    def test_protocol_parameter_errors(self):
        self.error('Nonsense', 'badVerb')
        self.error('Identify', 'badArgument', foo='bar')
        self.error('Identify', 'badArgument', identifier='x')
        self.error('GetRecord', 'badArgument', metadataPrefix='edm')
        self.error('ListRecords', 'badArgument')
        self.error('ListRecords', 'cannotDisseminateFormat', metadataPrefix='bogus')
        self.error('GetRecord', 'cannotDisseminateFormat', metadataPrefix='bogus', identifier=identifier(1))
        self.error('ListRecords', 'badArgument', metadataPrefix='edm', set='bad set')
        self.error('ListRecords', 'badArgument', metadataPrefix='')
        self.error('ListRecords', 'badArgument', metadataPrefix='edm', resumptionToken='foo')
        self.error('ListSets', 'badArgument', metadataPrefix='edm')
        self.error('ListMetadataFormats', 'badArgument', metadataPrefix='edm')

    def test_duplicate_arguments_and_missing_verb(self):
        for query, code in (('?verb=Identify&verb=ListSets', 'badVerb'),
                            ('?verb=ListRecords&metadataPrefix=edm&metadataPrefix=edm', 'badArgument'),
                            ('', 'badVerb')):
            root = ET.fromstring(self.client.get('/oai/' + query).content)
            self.assertEqual(root.find('oai:error', NS).get('code'), code)

    def test_invalid_xml_characters_in_arguments_are_rejected(self):
        self.error('GetRecord', 'badArgument', metadataPrefix='edm', identifier='invalid\x01')
        self.error('ListRecords', 'badArgument', resumptionToken='invalid\x01')

    def test_public_post_needs_no_csrf_or_login(self):
        obj = self.obj()
        client = Client(enforce_csrf_checks=True)
        response = client.post('/oai/', 'verb=GetRecord&metadataPrefix=edm&identifier=' + identifier(obj.pk),
                               content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(ET.fromstring(response.content).find('oai:GetRecord', NS))
        response = client.post('/oai/?verb=Identify', 'verb=Identify', content_type='application/x-www-form-urlencoded')
        self.assertEqual(ET.fromstring(response.content).find('oai:error', NS).get('code'), 'badVerb')
        response = client.post('/oai/?verb=Identify', '{}', content_type='application/json')
        self.assertEqual(ET.fromstring(response.content).find('oai:error', NS).get('code'), 'badArgument')
        self.assertEqual(client.put('/oai/').status_code, 405)

    @override_settings(ELIGIUS_OAI_PAGE_SIZE=2)
    def test_pagination_and_token_replay(self):
        objects = [self.obj(str(i)) for i in range(5)]
        first = self.request('ListRecords', metadataPrefix='edm', set=set_spec(self.collection.pk))
        token = first.findtext('.//oai:resumptionToken', namespaces=NS)
        self.assertIsNotNone(token)
        # Newly inserted records are handled by the next harvest, not appended to this sequence.
        self.obj('new')
        second = self.request('ListRecords', resumptionToken=token)
        repeat = self.request('ListRecords', resumptionToken=token)
        self.assertEqual(ET.tostring(second.find('oai:ListRecords', NS)), ET.tostring(repeat.find('oai:ListRecords', NS)))
        next_token = second.findtext('.//oai:resumptionToken', namespaces=NS)
        third = self.request('ListRecords', resumptionToken=next_token)
        self.assertEqual(third.find('.//oai:resumptionToken', NS).text, None)
        self.assertEqual(third.find('.//oai:resumptionToken', NS).get('cursor'), '4')
        ids = [node.text for root in (first, second, third) for node in root.findall('.//oai:identifier', NS)]
        self.assertEqual(ids, [identifier(obj.pk) for obj in objects])
        self.error('ListRecords', 'badResumptionToken', resumptionToken=token + 'x')
        self.error('ListIdentifiers', 'badResumptionToken', resumptionToken=token)

    @override_settings(ELIGIUS_OAI_PAGE_SIZE=1, ELIGIUS_OAI_TOKEN_MAX_AGE=-1)
    def test_expired_token_and_bad_signed_payload(self):
        self.obj('1')
        self.obj('2')
        token = self.request('ListRecords', metadataPrefix='edm').findtext('.//oai:resumptionToken', namespaces=NS)
        self.error('ListRecords', 'badResumptionToken', resumptionToken=token)
        bad = signing.dumps(['unsafe', 'payload'], salt=TOKEN_SALT)
        self.error('ListRecords', 'badResumptionToken', resumptionToken=bad)

    def test_invalid_signed_state_and_empty_token(self):
        self.error('ListSets', 'badResumptionToken', resumptionToken='')
        for state in (['unexpected'], {'v': 1}, {'verb': 'ListSets', 'size': -1}):
            self.error('ListSets', 'badResumptionToken', resumptionToken=signing.dumps(state, salt=TOKEN_SALT))

    @override_settings(ELIGIUS_OAI_PAGE_SIZE=1)
    def test_list_sets_and_identifiers_pagination(self):
        Slg.objects.create(name='Zweite Sammlung', kulturpool_export_erlaubt=True)
        first = self.request('ListSets')
        token = first.findtext('.//oai:resumptionToken', namespaces=NS)
        last = self.request('ListSets', resumptionToken=token)
        self.assertEqual(len(last.findall('.//oai:set', NS)), 1)
        self.assertIsNone(last.find('.//oai:resumptionToken', NS).text)
        self.obj('1')
        self.obj('2')
        first = self.request('ListIdentifiers', metadataPrefix='edm')
        token = first.findtext('.//oai:resumptionToken', namespaces=NS)
        last = self.request('ListIdentifiers', resumptionToken=token)
        self.assertEqual(len(last.findall('.//oai:header', NS)), 1)
        self.assertEqual(len(last.findall('.//oai:metadata', NS)), 0)

    def test_set_filter_parent_and_unknown_private_sets(self):
        obj = self.obj()
        other = Slg.objects.create(name='Andere', kulturpool_export_erlaubt=True)
        self.obj('2', Slg=other)
        root = self.request('ListRecords', metadataPrefix='edm', set=set_spec(self.collection.pk))
        self.assertEqual([n.text for n in root.findall('.//oai:identifier', NS)], [identifier(obj.pk)])
        self.assertEqual(len(self.request('ListIdentifiers', metadataPrefix='edm', set='eligius').findall('.//oai:header', NS)), 2)
        for value in (set_spec(self.private.pk), 'eligius:unknown'):
            self.error('ListRecords', 'noRecordsMatch', metadataPrefix='edm', set=value)

    def test_date_filter_inclusive_seconds_and_days(self):
        obj = self.obj()
        MuenztypObjektAnzeige.objects.filter(obj_id=obj.pk).update(last_modified=datetime(2026, 1, 2, 23, 59, 59, 999999, tzinfo=utc_timezone.utc))
        for lower, upper in (('2026-01-02', '2026-01-02'), ('2026-01-02T23:59:59Z', '2026-01-02T23:59:59Z')):
            root = self.request('ListRecords', metadataPrefix='edm', **{'from': lower, 'until': upper})
            self.assertEqual(root.findtext('.//oai:datestamp', namespaces=NS), '2026-01-02T23:59:59Z')
        self.error('ListRecords', 'noRecordsMatch', metadataPrefix='edm', **{'until': '2026-01-01'})
        self.error('ListRecords', 'noRecordsMatch', metadataPrefix='edm', **{'from': '2026-01-03'})
        self.error('ListRecords', 'noRecordsMatch', metadataPrefix='edm', **{'until': '2026-01-02T23:59:58Z'})

    def test_invalid_dates(self):
        for value in ('2026-02-30', '2026-1-01', '2026-01-01T00:00:00+02:00', '2026-01-01T00:00:00.5Z', 'yesterday', '9999-12-31'):
            self.error('ListRecords', 'badArgument', metadataPrefix='edm', **{'until': value})
        self.error('ListRecords', 'badArgument', metadataPrefix='edm', **{'from': '2026-01-02', 'until': '2026-01-01'})
        self.error('ListRecords', 'badArgument', metadataPrefix='edm', **{'from': '2026-01-01', 'until': '2026-01-02T00:00:00Z'})

    @override_settings(ELIGIUS_OAI_PAGE_SIZE=1)
    def test_token_preserves_dates_format_and_collection(self):
        objects = [self.obj(str(i)) for i in range(3)]
        MuenztypObjektAnzeige.objects.filter(obj_id__in=[o.pk for o in objects]).update(last_modified=datetime(2026, 1, 2, tzinfo=utc_timezone.utc))
        other = Slg.objects.create(name='Andere', kulturpool_export_erlaubt=True)
        self.obj('outside', Slg=other)
        root = self.request('ListRecords', metadataPrefix='oai_dc', set=set_spec(self.collection.pk), **{'from': '2026-01-02', 'until': '2026-01-02'})
        token = root.findtext('.//oai:resumptionToken', namespaces=NS)
        state = signing.loads(token, salt=TOKEN_SALT)
        self.assertEqual((state['prefix'], state['set'], state['from'], state['until']), ('oai_dc', set_spec(self.collection.pk), '2026-01-02', '2026-01-02'))
        root = self.request('ListRecords', resumptionToken=token)
        self.assertIsNotNone(root.find('.//oai_dc:dc', NS))
        self.assertEqual(root.findtext('.//oai:identifier', namespaces=NS), identifier(objects[1].pk))

    def test_edm_one_coin_two_images_and_normdata(self):
        self.collection.nomisma_collection_uri = 'http://nomisma.org/id/test_collection'
        self.collection.save()
        obj = self.obj(Typ=self.typ, avleg='AVGVSTVS', rvleg='CAESAR', gewicht='3.45', durchmesser='19.0', stempelstellung=6)
        graph, root = self.graph(obj)
        cho = URIRef(BASE + obj.get_absolute_url() + '#providedCHO')
        agg = URIRef(BASE + obj.get_absolute_url() + '#aggregation')
        self.assertEqual(list(graph.subjects(RDF.type, EDM.ProvidedCHO)), [cho])
        self.assertIn((agg, RDF.type, ORE.Aggregation), graph)
        self.assertEqual(len(list(graph.subjects(RDF.type, EDM.WebResource))), 2)
        self.assertIn((agg, EDM.isShownBy, URIRef('https://images.example.test/A1_a.jpg')), graph)
        self.assertIn((agg, EDM.hasView, URIRef('https://images.example.test/A1_r.jpg')), graph)
        self.assertIn((cho, DCTERMS.medium, URIRef('http://nomisma.org/id/ar')), graph)
        self.assertIn((cho, DC.type, URIRef('http://nomisma.org/id/denarius')), graph)
        self.assertIn((cho, DCTERMS.spatial, URIRef('http://nomisma.org/id/rome')), graph)
        self.assertIn((cho, DC.subject, URIRef(self.typ.link)), graph)
        self.assertIn((cho, DCTERMS.isPartOf, URIRef(self.collection.nomisma_collection_uri)), graph)
        descriptions = ' '.join(str(v) for v in graph.objects(cho, DC.description))
        for value in ('Vorderseite: Kopf nach rechts', 'Rückseite: Stehende Gestalt', 'Vorderseite, Legende: AVGVSTVS', 'Rückseite, Legende: CAESAR'):
            self.assertIn(value, descriptions)
        self.assertIn((cho, DCTERMS.extent, Literal('Gewicht: 3.45 g', lang='de')), graph)
        self.assertFalse(list(graph.triples((None, EDM.rights, None))))
        self.assertFalse(list(graph.triples((None, SKOS.exactMatch, None))))

    def test_all_typology_links_and_no_exact_match_or_draft_concordance(self):
        obj = self.obj(Typ=self.typ)
        crro = Muenztyp.objects.create(muenztyptitel='CRRO', workflow=self.controlled, Objekttyp=self.kind,
                                      Herstellung=self.manufacture, link='http://numismatics.org/crro/id/rrc-1.1')
        self.typ.Konkordanz.add(crro, self.draft_typ)
        ref = Ref.objects.create(abk='RPC')
        rpc = 'https://rpc.ashmus.ox.ac.uk/coins/1/1'
        Obj_Ref.objects.create(idfk_Obj=obj, idfk_Ref=ref, nummer='1', nach=False, link=rpc)
        graph, _ = self.graph(obj)
        cho = URIRef(BASE + obj.get_absolute_url() + '#providedCHO')
        for uri in (self.typ.link, crro.link, rpc):
            self.assertIn((cho, DC.subject, URIRef(uri)), graph)
        self.assertFalse(list(graph.triples((None, SKOS.exactMatch, None))))

    def test_descriptions_and_mint_marks_use_mtoa_in_both_formats(self):
        obj = self.obj(Typ=self.typ, avbeschr='Objekt-Freitext Av', rvbeschr='Objekt-Freitext Rv')
        MuenztypObjektAnzeige.objects.filter(obj_id=obj.pk).update(
            av_bildtyp='Aufbereiteter Avers', rv_bildtyp='Aufbereiteter Revers',
            av_beizeichen='Stern & Kranz', rv_beizeichen='B im Feld',
        )
        expected = {'Vorderseite: Aufbereiteter Avers', 'Rückseite: Aufbereiteter Revers',
                    'Vorderseite, Beizeichen: Stern & Kranz', 'Rückseite, Beizeichen: B im Feld'}
        for prefix in ('edm', 'oai_dc'):
            root = self.request('GetRecord', metadataPrefix=prefix, identifier=identifier(obj.pk))
            self.assertEqual({node.text for node in root.findall('.//oai:metadata//dc:description', NS)}, expected | ({'Vorderseite', 'Rückseite'} if prefix == 'edm' else set()))
            self.assertNotIn('Freitext', ET.tostring(root).decode())

    def test_mtoa_description_and_mint_mark_merging(self):
        own_obverse = AvBildtyp.objects.create(name='Objektspezifischer Kopf')
        inherited_av = AvBeizeichen.objects.create(name='Typ-Av-Beizeichen')
        own_av = AvBeizeichen.objects.create(name='Stern ?')
        inherited_rv = RvBeizeichen.objects.create(name='Feld ?')
        av_offizin = AvOffizin.objects.create(name='A')
        rv_offizin = RvOffizin.objects.create(name='B')
        self.typ.av_beizeichen = inherited_av
        self.typ.rv_beizeichen = inherited_rv
        self.typ.save()
        obj = self.obj(Typ=self.typ, av_bildtyp=own_obverse, av_beizeichen=own_av,
                       av_offizin=av_offizin, rv_offizin=rv_offizin)
        row = MuenztypObjektAnzeige.objects.get(obj_id=obj.pk)
        self.assertEqual((row.av_bildtyp, row.rv_bildtyp, row.av_beizeichen, row.rv_beizeichen),
                         ('Objektspezifischer Kopf', 'Stehende Gestalt', 'Stern A', 'Feld B'))
        graph, _ = self.graph(obj)
        cho = URIRef(BASE + obj.get_absolute_url() + '#providedCHO')
        descriptions = {str(value) for value in graph.objects(cho, DC.description)}
        self.assertEqual(descriptions, {'Vorderseite: Objektspezifischer Kopf', 'Rückseite: Stehende Gestalt',
                                        'Vorderseite, Beizeichen: Stern A', 'Rückseite, Beizeichen: Feld B'})

    def test_empty_mtoa_description_fields_emit_no_source_model_fallback(self):
        obj = self.obj(Typ=self.typ, avbeschr='Nur im Objekt vorhanden')
        MuenztypObjektAnzeige.objects.filter(obj_id=obj.pk).update(
            av_bildtyp='', rv_bildtyp=None, av_beizeichen='', rv_beizeichen=None,
        )
        graph, _ = self.graph(obj)
        cho = URIRef(BASE + obj.get_absolute_url() + '#providedCHO')
        self.assertFalse(list(graph.objects(cho, DC.description)))

    def test_people_roles_and_external_authorities(self):
        obj = self.obj()
        ruler = PersonFunktion.objects.create(pk=1, name='Münzherr')
        depicted = PersonFunktion.objects.create(pk=2, name='Dargestellte Person')
        person = Person.objects.create(name='Augustus', name_nom_id='augustus', DNB='https://d-nb.info/gnd/118505122')
        Obj_Person.objects.create(idfk_Obj=obj, idfk_Person=person, idfk_PersonFunktion=ruler, appears_on_rev=False)
        Obj_Person.objects.create(idfk_Obj=obj, idfk_Person=person, idfk_PersonFunktion=depicted, appears_on_rev=True)
        graph, _ = self.graph(obj)
        cho = URIRef(BASE + obj.get_absolute_url() + '#providedCHO')
        uri = URIRef('http://nomisma.org/id/augustus')
        self.assertIn((cho, DC.creator, uri), graph)
        self.assertIn((cho, DC.subject, uri), graph)
        self.assertIn((uri, RDF.type, EDM.Agent), graph)
        self.assertIn((cho, DC.creator, URIRef(person.DNB)), graph)

    def test_separate_rights_and_freetext_not_assumed(self):
        obj = self.obj()
        self.collection.bildrechte_lizenz = 'Copyright; Lizenz noch offen. CC BY nicht vereinbart.'
        self.collection.save()
        graph, _ = self.graph(obj)
        self.assertFalse(list(graph.triples((None, EDM.rights, None))))
        image_uri = 'https://rightsstatements.org/vocab/InC/1.0/'
        metadata_uri = 'https://creativecommons.org/publicdomain/zero/1.0/'
        self.collection.kulturpool_rights_uri = image_uri
        self.collection.kulturpool_metadata_rights_uri = metadata_uri
        self.collection.save()
        graph, _ = self.graph(obj)
        agg = URIRef(BASE + obj.get_absolute_url() + '#aggregation')
        self.assertIn((agg, EDM.rights, URIRef(image_uri)), graph)
        self.assertIn((agg, DC.rights, URIRef(metadata_uri)), graph)
        for web in graph.subjects(RDF.type, EDM.WebResource):
            self.assertIn((web, EDM.rights, URIRef(image_uri)), graph)
            self.assertNotIn((web, EDM.rights, URIRef(metadata_uri)), graph)

    def test_legacy_rights_uri_and_invalid_uris(self):
        obj = self.obj()
        self.collection.bildrechte_lizenz = 'https://rightsstatements.org/vocab/InC/1.0/'
        self.collection.save()
        graph, _ = self.graph(obj)
        self.assertTrue(list(graph.triples((None, EDM.rights, URIRef(self.collection.bildrechte_lizenz)))))
        self.collection.bildrechte_lizenz = 'javascript:alert(1)'
        self.collection.kulturpool_rights_uri = 'https://example.test/rights with spaces'
        self.collection.save()
        self.typ.link = 'https://example.test/invalid uri'
        self.typ.save()
        graph, _ = self.graph(obj)
        self.assertFalse(list(graph.triples((None, EDM.rights, None))))

    def test_local_and_part_image_paths_reuse_existing_resolver(self):
        part = SlgTeil.objects.create(name='Teil', idfk_Slg_SlgTeil=self.collection, bildurl='https://part.example.test/',
                                     bild_endung_av='_obv', bild_endung_rv='_rev')
        obj = self.obj(SlgTeil=part)
        graph, _ = self.graph(obj)
        self.assertIn(URIRef(obj.get_bild_urls()['av']), list(graph.subjects(RDF.type, EDM.WebResource)))
        cho = URIRef(BASE + obj.get_absolute_url() + '#providedCHO')
        self.assertNotIn(Literal(part.name, lang='de'), list(graph.objects(cho, DCTERMS.isPartOf)))
        dc = self.request('GetRecord', metadataPrefix='oai_dc', identifier=identifier(obj.pk))
        self.assertNotIn(part.name, [node.text for node in dc.findall('.//dc:relation', NS)])
        self.collection.bildurl = ''
        self.collection.bilder_lokal = True
        self.collection.save()
        part.bildurl = ''
        part.save()
        graph, _ = self.graph(obj)
        self.assertIn(URIRef(BASE + obj.get_bild_urls()['av']), list(graph.subjects(RDF.type, EDM.WebResource)))

    def test_without_images_and_sensible_title_xml_escaping(self):
        self.collection.bildurl = ''
        self.collection.save()
        description = AvBildtyp.objects.create(name='Kopf & Kranz')
        obj = self.obj(titel='Münze & <b>Silber</b>\x01', anmerkung='SECRET INTERNAL TEXT', av_bildtyp=description)
        graph, root = self.graph(obj)
        self.assertFalse(list(graph.subjects(RDF.type, EDM.WebResource)))
        cho = URIRef(BASE + obj.get_absolute_url() + '#providedCHO')
        self.assertIn((cho, DC.title, Literal('Münze & Silber', lang='de')), graph)
        self.assertNotIn('SECRET INTERNAL TEXT', ET.tostring(root).decode())

    def test_generated_title_and_date_from_mtoa(self):
        obj = self.obj(titel='', idfk_Nominal=self.nominal, dat_von=-10, dat_bis=-5)
        graph, _ = self.graph(obj)
        title = str(next(graph.objects(None, DC.title)))
        self.assertIn('Denar', title)
        self.assertIn('v. Chr.', title)

    def test_duplicate_projection_emits_one_stable_identifier(self):
        obj = self.obj()
        row = MuenztypObjektAnzeige.objects.get(obj_id=obj.pk)
        row.pk = None
        row.save()
        root = self.request('ListIdentifiers', metadataPrefix='edm')
        self.assertEqual([node.text for node in root.findall('.//oai:identifier', NS)], [identifier(obj.pk)])

    def test_publication_withdrawal_and_no_cache(self):
        obj = self.obj(Typ=self.typ)
        self.graph(obj)
        self.typ.workflow = self.draft
        self.typ.save()
        self.error('GetRecord', 'idDoesNotExist', identifier=identifier(obj.pk), metadataPrefix='edm')
        self.typ.workflow = self.controlled
        self.typ.save()
        self.collection.kulturpool_export_erlaubt = False
        self.collection.save()
        self.error('ListRecords', 'noRecordsMatch', metadataPrefix='edm')
        self.assertEqual(self.client.get('/oai/?verb=Identify')['Cache-Control'], 'no-store')

    def test_oai_identifier_and_cho_survive_collection_and_inventory_rename(self):
        obj = self.obj()
        original = identifier(obj.pk)
        original_uri = BASE + obj.get_absolute_url() + '#providedCHO'
        obj.invnr = 'NEW1'
        obj.save()
        self.collection.name = 'Umbenannt'
        self.collection.save()
        graph, root = self.graph(obj)
        self.assertEqual(root.findtext('.//oai:identifier', namespaces=NS), original)
        self.assertIn((URIRef(original_uri), RDF.type, EDM.ProvidedCHO), graph)

    def test_deleted_or_withdrawn_records_are_not_exposed_in_token_page(self):
        with override_settings(ELIGIUS_OAI_PAGE_SIZE=1):
            self.obj('first')
            second = self.obj('second')
            third = self.obj('third')
            token = self.request('ListRecords', metadataPrefix='edm').findtext('.//oai:resumptionToken', namespaces=NS)
            second.workflow = self.draft
            second.save()
            root = self.request('ListRecords', resumptionToken=token)
            self.assertEqual([n.text for n in root.findall('.//oai:identifier', NS)], [identifier(third.pk)])

    def test_query_count_is_constant_for_many_records(self):
        self.obj('one', Typ=self.typ)
        with CaptureQueriesContext(connection) as single:
            self.request('ListRecords', metadataPrefix='edm')
        disable_mtoa_sync()
        try:
            more = [Obj(invnr=str(i), Typ=self.typ, Slg=self.collection, workflow=self.controlled, Objekttyp=self.kind) for i in range(30)]
            Obj.objects.bulk_create(more)
            sync_objs_to_mtoa([obj.pk for obj in more])
        finally:
            enable_mtoa_sync()
        with CaptureQueriesContext(connection) as many:
            root = self.request('ListRecords', metadataPrefix='edm')
        self.assertEqual(len(root.findall('.//oai:record', NS)), 31)
        self.assertEqual(len(single), len(many))
        self.assertLessEqual(len(many), 7)

    def test_readiness_command_and_admin_status(self):
        self.obj()
        collection_admin = admin.site._registry[Slg]
        self.assertIn('kulturpool_export_erlaubt', collection_admin.list_filter)
        self.assertIn('kulturpool_readiness', collection_admin.readonly_fields)
        self.assertIn('Bildrechte-URI fehlt', collection_admin.kulturpool_readiness(self.collection))
        self.assertEqual(collection_admin.kulturpool_readiness(self.private), 'Export deaktiviert')
        output = StringIO()
        call_command('validate_kulturpool_export', stdout=output)
        self.assertIn('grundsätzlich exportfähig: 1', output.getvalue())
        self.assertIn('Bildrechte-URI fehlt', output.getvalue())
        self.assertNotIn(self.private.name, output.getvalue())
        with self.assertRaises(CommandError):
            call_command('validate_kulturpool_export', strict=True, stdout=StringIO())
        self.collection.kulturpool_rights_uri = 'https://rightsstatements.org/vocab/InC/1.0/'
        self.collection.kulturpool_metadata_rights_uri = 'https://creativecommons.org/publicdomain/zero/1.0/'
        self.collection.save()
        call_command('validate_kulturpool_export', strict=True, stdout=StringIO())


class OAISynchronizationTests(OAIFixtures, TestCase):
    """Run source-change regressions with the real existing MTOA synchronizer."""
    def stamp(self, obj):
        return MuenztypObjektAnzeige.objects.get(obj_id=obj.pk).last_modified

    def test_object_and_type_changes_increment_stamp(self):
        obj = self.obj(Typ=self.typ)
        previous = self.stamp(obj)
        obj.gewicht = '4.00'
        obj.save()
        self.assertGreater(self.stamp(obj), previous)
        previous = self.stamp(obj)
        self.obverse.name = 'Neuer Kopf'
        self.obverse.save()
        self.assertGreater(self.stamp(obj), previous)

    def test_mint_mark_and_offizin_renames_refresh_mtoa_and_datestamp(self):
        own_av = AvBeizeichen.objects.create(name='Av ?')
        inherited_rv = RvBeizeichen.objects.create(name='Rv ?')
        av_offizin = AvOffizin.objects.create(name='A')
        rv_offizin = RvOffizin.objects.create(name='B')
        self.typ.rv_beizeichen = inherited_rv
        self.typ.save()
        obj = self.obj(Typ=self.typ, av_beizeichen=own_av, av_offizin=av_offizin, rv_offizin=rv_offizin)
        for model, value, field, expected in (
            (own_av, 'Av-Stern ?', 'av_beizeichen', 'Av-Stern A'),
            (inherited_rv, 'Rv-Stern ?', 'rv_beizeichen', 'Rv-Stern B'),
            (av_offizin, 'C', 'av_beizeichen', 'Av-Stern C'),
            (rv_offizin, 'D', 'rv_beizeichen', 'Rv-Stern D'),
        ):
            previous = self.stamp(obj)
            model.name = value
            model.save()
            row = MuenztypObjektAnzeige.objects.get(obj_id=obj.pk)
            self.assertGreater(row.last_modified, previous)
            self.assertEqual(getattr(row, field), expected)

    def test_authority_and_collection_changes_increment_stamp(self):
        obj = self.obj(Typ=self.typ)
        for model, field, value in ((self.material, 'name', 'Ag'), (self.nominal, 'name', 'Denarius'),
                                    (self.mint, 'name', 'Roma'), (self.kind, 'name', 'Coin'),
                                    (self.manufacture, 'name', 'Prägung'), (self.collection, 'bildurl', 'https://new.example.test/')):
            previous = self.stamp(obj)
            setattr(model, field, value)
            model.save()
            self.assertGreater(self.stamp(obj), previous, model.__class__.__name__)

    def test_person_rename_and_relation_reassignment_updates_both(self):
        obj = self.obj()
        other = self.obj('B1')
        role = PersonFunktion.objects.create(pk=1, name='Münzherr')
        person = Person.objects.create(name='A', name_nom_id='augustus')
        relation = Obj_Person.objects.create(idfk_Obj=obj, idfk_Person=person, idfk_PersonFunktion=role, appears_on_rev=False)
        previous = self.stamp(obj)
        person.name = 'B'
        person.save()
        self.assertGreater(self.stamp(obj), previous)
        previous = self.stamp(obj)
        relation.idfk_Obj = other
        relation.save()
        self.assertGreater(self.stamp(obj), previous)
        self.assertFalse(MtoaPerson.objects.filter(mtoa__obj_id=obj.pk).exists())
        self.assertTrue(MtoaPerson.objects.filter(mtoa__obj_id=other.pk).exists())

    def test_type_person_links_and_removal_increment_stamp(self):
        obj = self.obj(Typ=self.typ)
        role = PersonFunktion.objects.create(pk=1, name='Münzherr')
        person = Person.objects.create(name='Augustus', name_nom_id='augustus')
        previous = self.stamp(obj)
        relation = Mztyp_Person.objects.create(Mztyp=self.typ, idfk_Person=person, idfk_PersonFunktion=role, appears_on_rev=False)
        self.assertGreater(self.stamp(obj), previous)
        previous = self.stamp(obj)
        relation.delete()
        self.assertGreater(self.stamp(obj), previous)

    def test_references_concordance_and_part_updates_increment_stamp(self):
        part = SlgTeil.objects.create(name='Teil', idfk_Slg_SlgTeil=self.collection)
        obj = self.obj(Typ=self.typ, SlgTeil=part)
        ref = Ref.objects.create(abk='RPC')
        previous = self.stamp(obj)
        relation = Obj_Ref.objects.create(idfk_Obj=obj, idfk_Ref=ref, nummer='1', nach=False, link='https://rpc.ashmus.ox.ac.uk/coins/1/1')
        self.assertGreater(self.stamp(obj), previous)
        previous = self.stamp(obj)
        relation.delete()
        self.assertGreater(self.stamp(obj), previous)
        for operation in (lambda: self.typ.Konkordanz.add(self.draft_typ), lambda: self.typ.Konkordanz.clear()):
            previous = self.stamp(obj)
            operation()
            self.assertGreater(self.stamp(obj), previous)
        previous = self.stamp(obj)
        part.name = 'Neuer Teil'
        part.save()
        self.assertGreater(self.stamp(obj), previous)

    def test_all_type_objects_are_synced_in_bounded_batches(self):
        Obj.objects.bulk_create([Obj(invnr=str(i), Typ=self.typ, Slg=self.collection, workflow=self.controlled, Objekttyp=self.kind) for i in range(1201)])
        with patch('slg.signals._schedule_sync') as sync:
            self.typ.save()
        batches = [call.args[0] for call in sync.call_args_list if call.args[0]]
        self.assertEqual([len(batch) for batch in batches], [500, 500, 201])
        self.assertEqual(len({pk for batch in batches for pk in batch}), 1201)

    def test_collection_sync_has_no_2000_object_cutoff(self):
        Obj.objects.bulk_create([Obj(invnr=str(i), Slg=self.collection, workflow=self.controlled, Objekttyp=self.kind) for i in range(2101)])
        with patch('slg.signals._schedule_sync') as sync:
            self.collection.save()
        batches = [call.args[0] for call in sync.call_args_list if call.args[0]]
        self.assertEqual([len(batch) for batch in batches], [500, 500, 500, 500, 101])
        self.assertEqual(len({pk for batch in batches for pk in batch}), 2101)
