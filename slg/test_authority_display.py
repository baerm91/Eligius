import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.template import Context, Template
from django.test import TestCase, RequestFactory
from django.utils.translation import override

from slg.models import Metall, Nominal, Person, Obj, MuenztypObjektAnzeige
from slg.services.authority_display import display_label, display_text, clear_display_cache, qualified_label
from slg.services.public_api import facet_values


class AuthorityDisplayTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'labels.json'
        self.path.write_text(json.dumps({'schema': 'eligius-authority-labels-v1', 'labels': {
            'nomisma:ar': {'label': 'Silver'}, 'nomisma:ae': {'label': 'Bronze'},
            'nomisma:denarius': {'label': 'Denarius'},
            'wikidata:Q1': {'label': 'English person'}, 'gnd:118521071': {'label': 'Claudius Gothicus'},
        }}), encoding='utf-8')
        self.settings_override = self.settings(ELIGIUS_AUTHORITY_LABELS_PATH=self.path)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(clear_display_cache)
        clear_display_cache()

    def test_uri_sources_priority_and_originals_stay_unchanged(self):
        silver = Metall.objects.create(name='Silber', name_nom_id='http://nomisma.org/id/ar')
        with override('en'), patch('requests.get', side_effect=AssertionError('No live requests')):
            self.assertEqual(display_label(silver), 'Silver')
            self.assertEqual(str(silver), 'Silber')
            self.assertEqual(display_text('Silber', 'Metall'), 'Silver')
            silver.name_nom_id = 'https://nomisma.org/id/ae'
            self.assertEqual(display_label(silver), 'Bronze')
            silver.name_nom_id = 'https://nomisma.org/id/unknown'
            self.assertEqual(display_label(silver), 'Silber')
            person = Person(name='Lokaler Name', DNB='http://d-nb.info/gnd/118521071')
            self.assertEqual(display_label(person), 'Claudius Gothicus')
            person.WikiEn = 'https://www.wikidata.org/entity/Q1'
            self.assertEqual(display_label(person), 'English person')
        silver.refresh_from_db()
        with override('de'):
            self.assertEqual(display_label(silver), 'Silber')
        self.assertEqual(silver.name_nom_id, 'http://nomisma.org/id/ar')

    def test_facets_search_english_but_preserve_original_values_and_counts(self):
        silver = Metall.objects.create(name='Silber', name_nom_id='http://nomisma.org/id/ar')
        obj = Obj.objects.bulk_create([Obj(invnr='URI-1', Objekttyp=None, workflow=None)])[0]
        MuenztypObjektAnzeige.objects.create(obj_id=obj.pk, invnr='URI-1', metall='Silber', metall_fk=silver)
        request = RequestFactory().get('/api/facet/')
        with override('en'):
            self.assertEqual(facet_values(request, 'material', term='silver'),
                [dict(id=silver.pk, name='Silber', label='Silver', count=1)])
            filtered = RequestFactory().get('/api/facet/', {'material': 'Silber'})
            self.assertEqual(facet_values(filtered, 'material', include_current=True)[0]['count'], 1)
        with override('de'):
            self.assertEqual(facet_values(request, 'material'), [dict(id=silver.pk, name='Silber', count=1)])

    def test_card_text_changes_but_href_keeps_original_and_escaping(self):
        Metall.objects.create(name='Silber', name_nom_id='http://nomisma.org/id/ar')
        template = Template('{% load authority_labels %}<a href="?material={{ name }}">{{ name|authority_text:"Metall" }}</a>')
        with override('en'):
            self.assertEqual(template.render(Context({'name': 'Silber'})), '<a href="?material=Silber">Silver</a>')
            # The table lookup is cached across cards, not repeated per rendered coin.
            with self.assertNumQueries(0):
                for _ in range(30):
                    self.assertEqual(display_text('Silber', 'Metall'), 'Silver')

    def test_changed_reference_invalidates_name_cache(self):
        metal = Metall.objects.create(name='Silber', name_nom_id='http://nomisma.org/id/ar')
        with override('en'):
            self.assertEqual(display_text('Silber', 'Metall'), 'Silver')
            metal.name_nom_id = ''
            metal.save()
            self.assertEqual(display_text('Silber', 'Metall'), 'Silber')

    def test_install_keeps_only_source_labels_and_gnd_reciprocal_links(self):
        source = Path(self.directory.name) / 'proposals.json'
        source.write_text(json.dumps(dict(generated_at='now', proposals=[dict(original='PRIVATE', candidates=[
            dict(uri='http://www.wikidata.org/entity/Q1', label='English person',
                 source_url='https://example.org/evidence', via_gnd='http://d-nb.info/gnd/118521071',
                 reciprocal_gnd=True)])])), encoding='utf-8')
        call_command('install_authority_labels', str(source), output=self.path)
        saved = self.path.read_text(encoding='utf-8')
        self.assertNotIn('PRIVATE', saved)
        self.assertEqual(json.loads(saved)['labels']['gnd:118521071']['label'], 'English person')

    def test_local_side_dates_and_uncertainty_are_preserved(self):
        self.assertEqual(qualified_label('dezentriert (Av.)', 'Off centre'), 'Off centre (obv.)')
        self.assertEqual(qualified_label('Herrscher [188–217] (?)', 'Ruler'), 'Ruler [188–217] (?)')
        self.assertEqual(qualified_label('Name (?)', 'Name (?)'), 'Name (?)')
