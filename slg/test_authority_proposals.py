import copy
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from scripts.build_authority_proposals import CachedHTTP, csv_text, git_rdf_blobs, main
from slg.services.authority_proposals import build_proposals, gnd_evidence, review_flags


def reference(field='name_nom_id', value='http://nomisma.org/id/robert', **kwargs):
    return dict(model='slg.Person', id=1, label='Abt Robert Leeb (1688–1755)', field=field, value=value, **kwargs)


class ProposalTests(SimpleTestCase):
    def test_preserves_local_entity_and_combines_sources_without_approval(self):
        records = [reference(), reference('DNB', 'http://d-nb.info/gnd/139172955')]
        original = copy.deepcopy(records)
        resolved = {
            ('nomisma', 'robert'): {'candidates': [{'label': 'Robert Leeb', 'provider': 'nomisma'}]},
            ('gnd', '139172955'): {'candidates': [{'label': 'Robert Leeb', 'provider': 'wikidata', 'reciprocal_gnd': True}]},
        }
        proposal, = build_proposals(records, resolved)
        self.assertEqual(records, original)
        self.assertEqual(proposal['status'], 'pending_review')
        self.assertFalse(proposal['approved'])
        self.assertEqual(len(proposal['references']), 2)
        self.assertIn('numbers_or_ordinals_missing', proposal['issues'])
        self.assertNotIn('source_label_conflict', proposal['issues'])
        records[0]['label'] = 'Changed source'
        self.assertNotEqual(proposal['original_sha256'], build_proposals(records, resolved)[0]['original_sha256'])

    def test_conflicts_and_missing_reciprocal_link_are_visible(self):
        result = {('nomisma', 'robert'): {'candidates': [
            {'label': 'Robert', 'provider': 'nomisma'},
            {'label': 'Robert II', 'provider': 'wikidata', 'reciprocal_gnd': False}]}}
        proposal, = build_proposals([reference()], result)
        self.assertIn('source_label_conflict', proposal['issues'])
        self.assertIn('gnd_link_not_reciprocated', proposal['issues'])

    def test_no_label_or_fetch_failure_never_uses_original_as_english(self):
        proposal, = build_proposals([reference()], {('nomisma', 'robert'): {'error': 'Timeout'}})
        self.assertIsNone(proposal['proposed_entity_label'])
        self.assertEqual(proposal['status'], 'unresolved')
        self.assertIn('source_fetch_or_parse_error', proposal['issues'])
        other = reference('WikiDe', 'https://de.wikipedia.org/wiki/Robert')
        self.assertIn('unresolved_reference', build_proposals([other], {})[0]['issues'])

    def test_flags_known_bad_english_and_uncertainty(self):
        flags = review_flags('Maria (?)', 'Maria Fürstin (gest. 1698) (BLKÖ)', 'slg.Person')
        self.assertIn('possible_german_catalogue_text', flags)
        self.assertIn('preserve_uncertainty', flags)
        self.assertIn('numbers_or_ordinals_missing', review_flags('Typ 1', 'Type 10', 'slg.Objekttyp'))

    def test_git_blobs_keep_case_distinct_ids_and_missing_files(self):
        raw = b'abc blob 3\none\ndef blob 3\ntwo\nrev:id/absent.rdf missing\n'
        with patch('scripts.build_authority_proposals.subprocess.check_output', return_value=raw):
            result = git_rdf_blobs(Path('repo'), 'rev', ['AE3_4', 'ae3_4', 'absent'])
        self.assertEqual(result, {'AE3_4': b'one', 'ae3_4': b'two', 'absent': None})

    def test_shared_uri_does_not_merge_local_records(self):
        a, b = reference(), reference()
        b['id'] = 2
        self.assertEqual(len(build_proposals([a, b], {})), 2)

    def test_gnd_names_without_language_are_not_english(self):
        xml = '''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:gndo="https://d-nb.info/standards/elementset/gnd#"
        xmlns:owl="http://www.w3.org/2002/07/owl#">
        <rdf:Description rdf:about="https://d-nb.info/gnd/123">
        <gndo:preferredNameForThePerson>Leeb, Robert</gndo:preferredNameForThePerson>
        <owl:sameAs rdf:resource="http://www.wikidata.org/entity/Q2157997"/>
        </rdf:Description></rdf:RDF>'''
        result = gnd_evidence(xml, '123')
        self.assertEqual(result['english_labels'], [])
        self.assertEqual(result['wikidata_ids'], ['Q2157997'])
        self.assertEqual(result['preferred_names'][0]['value'], 'Leeb, Robert')

    def test_cache_avoids_second_request_and_keeps_provenance(self):
        response = Mock(status_code=200, url='https://nomisma.org/apis/getRdf', content=b'<rdf/>')
        with TemporaryDirectory() as directory, patch('scripts.build_authority_proposals.requests.get', return_value=response) as get:
            http = CachedHTTP(Path(directory))
            first = http.get('https://nomisma.org/apis/getRdf')
            second = http.get('https://nomisma.org/apis/getRdf')
            self.assertEqual(first, second)
            self.assertEqual(get.call_count, 1)
            self.assertTrue(first['retrieved_at'])
            self.assertEqual(len(first['response_sha256']), 64)

    def test_csv_formula_protection(self):
        self.assertEqual(csv_text('=1+1'), "'=1+1")
        self.assertEqual(csv_text(' @SUM(A1)'), "' @SUM(A1)")
        self.assertEqual(csv_text('Robert'), 'Robert')

    def test_complete_local_run_writes_review_artifacts_without_approval(self):
        xml = '''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:skos="http://www.w3.org/2004/02/skos/core#">
        <rdf:Description rdf:about="http://nomisma.org/id/ar">
        <skos:prefLabel xml:lang="en">Silver</skos:prefLabel>
        </rdf:Description></rdf:RDF>'''
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'inventory.json'
            source.write_text(json.dumps({'records': [dict(model='slg.Metall', id=1,
                label='Silber', field='name_nom_id', value='ar'),
                dict(model='slg.Person', id=2, label='Robert', field='DNB', value='http://d-nb.info/gnd/123')]}), encoding='utf-8')
            response = dict(body=xml, source_url='https://nomisma.org/apis/getRdf',
                            retrieved_at='2026-11-13T12:00:00+00:00', response_sha256='a' * 64)
            gnd_xml = '''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns:owl="http://www.w3.org/2002/07/owl#"><rdf:Description rdf:about="http://d-nb.info/gnd/123">
                <owl:sameAs rdf:resource="http://www.wikidata.org/entity/Q42"/></rdf:Description></rdf:RDF>'''
            wd = {'entities': {'Q42': {'id': 'Q42', 'labels': {'en': {'language': 'en', 'value': 'Robert'}},
                'claims': {'P227': [{'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {'value': '123'}}}]}}}}

            def fetch(url, *args, **kwargs):
                body = gnd_xml if 'd-nb.info' in url else json.dumps(wd) if 'wikidata.org' in url else xml
                return dict(response, body=body, source_url=url)

            with patch('sys.argv', ['build', '--inventory', str(source), '--output', str(root / 'out')]), \
                 patch.object(CachedHTTP, 'get', side_effect=fetch), patch('builtins.print'):
                main()
            result = json.loads((root / 'out/proposals.json').read_text(encoding='utf-8'))
            self.assertEqual(result['summary']['with_candidates'], 2)
            self.assertEqual(result['summary']['approved'], 0)
            self.assertEqual(result['summary']['changed_labels'], 1)
            self.assertEqual(result['summary']['unchanged_labels'], 1)
            self.assertEqual(result['proposals'][0]['original'], 'Silber')
            self.assertEqual(result['proposals'][0]['proposed_entity_label'], 'Silver')
            self.assertTrue(result['proposals'][1]['candidates'][0]['reciprocal_gnd'])
            self.assertTrue((root / 'out/review.csv').is_file())
            self.assertTrue((root / 'out/review.md').is_file())
            self.assertTrue((root / 'out/changes.csv').is_file())
            self.assertTrue((root / 'out/open.csv').is_file())
