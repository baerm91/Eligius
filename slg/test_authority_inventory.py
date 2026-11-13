import json
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from slg.models import Nominal, Person
from slg.services.authority_inventory import identify_authority, inventory
from scripts.audit_authority_labels import nomisma_labels, wikidata_label


class AuthorityParsingTests(SimpleTestCase):
    def test_known_authorities_and_bare_ids(self):
        for value, expected in [
            ('http://nomisma.org/id/siscia', ('nomisma', 'siscia')),
            ("https://nomisma.org/id/ba'albakk", ('nomisma', "ba'albakk")),
            ('http://nomisma.org/id/ais(-)_callatis', ('nomisma', 'ais(-)_callatis')),
            ('https://www.wikidata.org/wiki/Q42', ('wikidata', 'Q42')),
            ('http://d-nb.info/gnd/118540238', ('gnd', '118540238')),
        ]:
            self.assertEqual(identify_authority(value), expected)
        self.assertIsNone(identify_authority('siscia'))
        self.assertEqual(identify_authority('siscia', allow_nomisma_id=True), ('nomisma', 'siscia'))
        self.assertEqual(identify_authority('-des_cos', allow_nomisma_id=True), ('nomisma', '-des_cos'))
        self.assertIsNone(identify_authority('-', allow_nomisma_id=True))

    def test_untrusted_or_ambiguous_values_not_followed(self):
        for value in [None, '', 'Frankreich / Departement Loire-Atlantique',
                      'https://nomisma.org.evil/id/ar', 'http://user@nomisma.org/id/ar',
                      'https://nomisma.org/id/ar?other=1', 'https://nomisma.org/id/ar#other',
                      'https://nomisma.org:bad/id/ar', 'https://en.wikipedia.org/wiki/Silver']:
            self.assertIsNone(identify_authority(value))

    def test_inventory_preserves_original_and_deduplicates_identity(self):
        records = [dict(model='Nominal', id=i, label='Test', field='name_nom_id', value=value)
                   for i, value in enumerate(['siscia', 'http://nomisma.org/id/siscia'])]
        result = inventory(records)
        self.assertEqual(result['unique_authorities'], 1)
        self.assertEqual(result['records'][0]['value'], 'siscia')

    def test_wikidata_requires_exact_entity_and_explicit_english(self):
        data = {'entities': {'Q42': {'id': 'Q42', 'labels': {
            'en': {'language': 'mul', 'value': 'Default name'}}}}}
        self.assertIsNone(wikidata_label(data, 'Q42')['english_label'])
        data['entities']['Q42']['labels']['en']['language'] = 'en'
        self.assertEqual(wikidata_label(data, 'Q42')['english_label'], 'Default name')
        data['entities']['Q42']['id'] = 'Q43'
        self.assertIsNone(wikidata_label(data, 'Q42')['english_label'])

    def test_only_exact_subject_english_labels_and_identity_links(self):
        xml = '''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:skos="http://www.w3.org/2004/02/skos/core#">
        <rdf:Description rdf:about="http://nomisma.org/id/ar">
          <skos:prefLabel xml:lang="de">Silber</skos:prefLabel>
          <skos:prefLabel>Unlabelled</skos:prefLabel>
          <skos:prefLabel xml:lang="en">Silver</skos:prefLabel>
          <skos:related rdf:resource="http://www.wikidata.org/entity/Q1"/>
          <skos:exactMatch rdf:resource="http://www.wikidata.org/entity/Q2"/>
        </rdf:Description>
        <rdf:Description rdf:about="http://nomisma.org/id/av">
          <skos:prefLabel xml:lang="en">Gold</skos:prefLabel>
        </rdf:Description></rdf:RDF>'''
        result = nomisma_labels(xml, ['ar', 'absent'])
        self.assertEqual(result[0]['english_labels'], ['Silver'])
        self.assertEqual([x['authority_id'] for x in result[0]['identity_links']], ['Q2'])
        self.assertEqual(result[1]['status'], 'review_required')


class AuthorityExportTests(TestCase):
    def test_export_covers_person_fields_without_changing_database(self):
        person = Person.objects.create(name='Original', DNB='https://d-nb.info/gnd/118540238',
                                       WikiEn='https://en.wikipedia.org/wiki/Example')
        Nominal.objects.create(name='Pfennig', name_nom_id='pfennig')
        output = StringIO()
        call_command('export_authority_inventory', stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result['by_provider'], {'nomisma': 1, 'gnd': 1, 'review_required': 1})
        person.refresh_from_db()
        self.assertEqual(person.name, 'Original')
        self.assertEqual(Person.objects.count(), 1)
