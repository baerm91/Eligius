import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from slg.models import Mzstaette, Person
from slg.services.authority_review import record_hash
from slg.services.identifier_enrichment import (
    PROPOSAL_SCHEMA,
    decide,
    geonames_id,
    geonames_uri,
    gnd_id,
    nomisma_links,
    viaf_id,
    wikidata_values,
)

RDF = b'''<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:skos="http://www.w3.org/2004/02/skos/core#">
  <skos:Concept rdf:about="http://nomisma.org/id/vienna">
    <skos:closeMatch rdf:resource="http://www.wikidata.org/entity/Q1741"/>
    <skos:closeMatch rdf:resource="https://sws.geonames.org/2761369/"/>
    <skos:exactMatch rdf:resource="http://d-nb.info/gnd/4066009-6"/>
    <skos:closeMatch rdf:resource="http://viaf.org/viaf/155870729"/>
  </skos:Concept>
  <skos:Concept rdf:about="http://nomisma.org/id/other">
    <skos:closeMatch rdf:resource="https://sws.geonames.org/1/"/>
  </skos:Concept>
</rdf:RDF>'''


def claim(value, rank='normal'):
    return {'rank': rank, 'mainsnak': {'datavalue': {'value': value}}}


class ParsingTests(SimpleTestCase):
    def test_identifier_parsers_and_canonical_uri(self):
        self.assertEqual(geonames_id('https://www.geonames.org/2761369/vienna.html'), '2761369')
        self.assertEqual(geonames_id(' 2761369 '), '2761369')
        self.assertIsNone(geonames_id('Wien'))
        self.assertEqual(geonames_uri('2761369'), 'https://sws.geonames.org/2761369/')
        self.assertEqual(gnd_id('https://d-nb.info/gnd/118540238x'), '118540238X')
        self.assertEqual(gnd_id('4066009-6'), '4066009-6')
        self.assertEqual(viaf_id('http://viaf.org/viaf/155870729/'), '155870729')
        self.assertIsNone(viaf_id('https://example.org/viaf/1'))

    def test_nomisma_links_only_of_requested_concept(self):
        self.assertEqual(nomisma_links(RDF, 'vienna'), {
            'wikidata': ['Q1741'], 'geonames': ['2761369'], 'gnd': ['4066009-6'], 'viaf': ['155870729']})

    def test_wikidata_preferred_rank_and_deprecated(self):
        entity = {'claims': {'P214': [claim('1'), claim('2', 'preferred'), claim('3', 'deprecated')]}}
        self.assertEqual(wikidata_values(entity, 'P214'), {'2'})
        entity = {'claims': {'P214': [claim('1'), claim('3', 'deprecated')]}}
        self.assertEqual(wikidata_values(entity, 'P214'), {'1'})


class DecideTests(SimpleTestCase):
    def mint(self, **kwargs):
        return dict(id=1, label='Wien', name_nom_id='http://nomisma.org/id/vienna', geonames='', **kwargs)

    def test_single_nomisma_link_is_automatic(self):
        row, = decide('slg.Mzstaette', self.mint(), {'geonames': ['2761369'], 'wikidata': ['Q1']}, {})
        self.assertEqual((row['status'], row['value']), ('auto', '2761369'))

    def test_multiple_links_need_review(self):
        row, = decide('slg.Mzstaette', self.mint(), {'geonames': ['2761333', '2761369']}, {})
        self.assertEqual(row['status'], 'review')
        self.assertIsNone(row['value'])

    def test_wikidata_only_as_fallback(self):
        entities = {'Q1741': {'claims': {'P1566': [claim('2761369')]}}}
        row, = decide('slg.Mzstaette', self.mint(), {'wikidata': ['Q1741']}, entities)
        self.assertEqual((row['status'], row['candidates'][0]['via']), ('auto', 'wikidata'))
        # Nomisma has a GeoNames link: Wikidata is not consulted, no conflict is produced.
        entities = {'Q1741': {'claims': {'P1566': [claim('9')]}}}
        row, = decide('slg.Mzstaette', self.mint(), {'geonames': ['2761369'], 'wikidata': ['Q1741']}, entities)
        self.assertEqual(row['value'], '2761369')

    def test_existing_values_are_never_proposed(self):
        row, = decide('slg.Mzstaette', self.mint() | {'geonames': '2761369'}, {'geonames': ['2761369']}, {})
        self.assertEqual(row['status'], 'present')
        row, = decide('slg.Mzstaette', self.mint() | {'geonames': '5'}, {'geonames': ['2761369']}, {})
        self.assertEqual(row['status'], 'present_differs')
        self.assertIsNone(row['value'])

    def test_person_fields_and_stored_uris(self):
        record = dict(id=2, label='Rudolf IV.', name_nom_id='rudolf_iv', DNB='', VIAF='')
        entities = {'Q2': {'claims': {'P227': [claim('118603272')], 'P214': [claim('1'), claim('2')]}}}
        gnd, viaf = decide('slg.Person', record, {'wikidata': ['Q2']}, entities)
        self.assertEqual((gnd['status'], gnd['value']), ('auto', 'https://d-nb.info/gnd/118603272'))
        self.assertEqual(viaf['status'], 'review')
        self.assertEqual(decide('slg.Person', record, None, {})[0]['status'], 'none')


class ApplyTests(TestCase):
    def setUp(self):
        self.mint = Mzstaette.objects.create(name='Wien', name_nom_id='http://nomisma.org/id/vienna')
        self.filled = Mzstaette.objects.create(name='Rom', name_nom_id='http://nomisma.org/id/rome', geonames='3169070')
        self.moved = Mzstaette.objects.create(name='Linz', name_nom_id='http://nomisma.org/id/other')
        self.person = Person.objects.create(name='Rudolf IV.', name_nom_id='rudolf_iv')
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def proposal(self, obj, field, kind, status, value, nom, candidates=()):
        return dict(model=obj._meta.label, id=obj.pk, label=obj.name, name_nom_id=nom, field=field, kind=kind,
                    current='', status=status, value=value, candidates=[{'value': c, 'via': 'nomisma'} for c in candidates])

    def write(self, proposals):
        target = self.path / 'proposals.json'
        target.write_text(json.dumps({'schema': PROPOSAL_SCHEMA, 'inventory_sha256': 'x', 'proposals': proposals}))
        return target

    def run_command(self, *args):
        out = StringIO()
        call_command('apply_identifier_proposals', *args, stdout=out)
        return out.getvalue()

    def standard(self):
        return self.write([
            self.proposal(self.mint, 'geonames', 'geonames', 'auto', '2761369', 'http://nomisma.org/id/vienna'),
            self.proposal(self.filled, 'geonames', 'geonames', 'auto', '1', 'http://nomisma.org/id/rome'),
            self.proposal(self.moved, 'geonames', 'geonames', 'auto', '2', 'http://nomisma.org/id/linz'),
            self.proposal(self.person, 'DNB', 'gnd', 'auto', 'https://d-nb.info/gnd/118603272', 'rudolf_iv'),
            self.proposal(self.person, 'VIAF', 'viaf', 'review', None, 'rudolf_iv', ['1', '2']),
        ])

    def test_dry_run_writes_nothing(self):
        output = self.run_command(str(self.standard()))
        self.assertIn('2 Felder würden gefüllt', output)
        self.assertIn('Feld inzwischen befüllt', output)
        self.assertIn('Nomisma-ID geändert', output)
        self.mint.refresh_from_db()
        self.assertIsNone(self.mint.geonames)
        self.assertEqual(list(self.path.glob('applied-*.json')), [])

    @override_settings(ELIGIUS_REVIEWED_AUTHORITY_LABELS_PATH='/nonexistent/reviewed.json')
    def test_apply_fills_only_empty_fields_logs_and_touches_datestamps(self):
        with patch('slg.management.commands.apply_identifier_proposals.touch_oai_datestamps') as touch:
            self.run_command(str(self.standard()), '--apply')
        self.mint.refresh_from_db(); self.filled.refresh_from_db(); self.moved.refresh_from_db(); self.person.refresh_from_db()
        self.assertEqual(self.mint.geonames, '2761369')
        self.assertEqual(self.filled.geonames, '3169070')
        self.assertIsNone(self.moved.geonames)
        self.assertEqual(self.person.DNB, 'https://d-nb.info/gnd/118603272')
        self.assertIsNone(self.person.VIAF)
        touched = {call.args[0]: call.args[1] for call in touch.call_args_list}
        self.assertEqual(touched, {'mzstaette': {self.mint.pk}, 'person': {self.person.pk}})
        log, = self.path.glob('applied-*.json')
        self.assertEqual(len(json.loads(log.read_text())['changes']), 2)

    def test_review_decisions(self):
        proposals = self.standard()
        decisions = self.path / 'review.csv'
        decisions.write_text('Modell;ID;Name;Nomisma;Feld;Kandidaten;Quellen;Entscheidung\n'
                             f'slg.Person;{self.person.pk};Rudolf;rudolf_iv;VIAF;1 | 2;;2\n', encoding='utf-8-sig')
        self.run_command(str(proposals), '--decisions', str(decisions), '--apply')
        self.person.refresh_from_db()
        self.assertEqual(self.person.VIAF, 'https://viaf.org/viaf/2')
        decisions.write_text('Modell;ID;Feld;Entscheidung\nslg.Person;999;VIAF;2\n', encoding='utf-8-sig')
        with self.assertRaises(CommandError):
            self.run_command(str(proposals), '--decisions', str(decisions))
        decisions.write_text(f'Modell;ID;Feld;Entscheidung\nslg.Person;{self.person.pk};VIAF;abc\n', encoding='utf-8-sig')
        with self.assertRaises(CommandError):
            self.run_command(str(proposals), '--decisions', str(decisions))

    def test_rejects_unknown_format(self):
        target = self.path / 'other.json'
        target.write_text('{"schema": "eligius-authority-review-v1"}')
        with self.assertRaises(CommandError):
            self.run_command(str(target))

    def test_reviewed_english_label_survives_new_gnd(self):
        reviewed = self.path / 'reviewed.json'
        before = record_hash('slg.Person', self.person.pk, {'name': self.person.name, 'name_nom_id': 'rudolf_iv'})
        reviewed.write_text(json.dumps({'schema': 'eligius-reviewed-authority-labels-v1', 'labels': {
            f'slg.Person:{self.person.pk}': {'label': 'Rudolf IV', 'original_sha256': before}}}))
        proposals = self.write([self.proposal(self.person, 'DNB', 'gnd', 'auto',
                                              'https://d-nb.info/gnd/118603272', 'rudolf_iv')])
        with override_settings(ELIGIUS_REVIEWED_AUTHORITY_LABELS_PATH=str(reviewed)):
            output = self.run_command(str(proposals), '--apply')
        self.assertIn('1 freigegebene', output)
        entry = json.loads(reviewed.read_text())['labels'][f'slg.Person:{self.person.pk}']
        after = record_hash('slg.Person', self.person.pk, {'name': self.person.name, 'name_nom_id': 'rudolf_iv',
                                                           'DNB': 'https://d-nb.info/gnd/118603272'})
        self.assertEqual(entry['original_sha256'], after)
        self.assertFalse(reviewed.with_suffix('.json.lock').exists())


class ExportTests(TestCase):
    def test_inventory_contains_targets_read_only(self):
        Mzstaette.objects.create(name='Wien', name_nom_id='http://nomisma.org/id/vienna')
        Person.objects.create(name='Rudolf IV.', name_nom_id='rudolf_iv', DNB='https://d-nb.info/gnd/118603272')
        out = StringIO()
        call_command('export_identifier_inventory', stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(data['schema'], 'eligius-identifier-inventory-v1')
        mint = next(r for r in data['records'] if r['model'] == 'slg.Mzstaette')
        person = next(r for r in data['records'] if r['model'] == 'slg.Person')
        self.assertEqual((mint['label'], mint['geonames']), ('Wien', ''))
        self.assertEqual((person['DNB'], person['VIAF']), ('https://d-nb.info/gnd/118603272', ''))
