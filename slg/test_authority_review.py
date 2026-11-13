import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts.render_authority_review import render


class AuthorityReviewTests(unittest.TestCase):
    def test_embedded_data_preserves_provenance_and_cannot_close_script(self):
        row = {
            'model': 'slg.Person', 'id': 1,
            'original': '</script><script>alert("test")</script> & ü',
            'original_sha256': 'original-hash',
            'references': [{'field': 'uri', 'value': 'https://example.org/entity/1'}],
            'candidates': [{'label': 'English', 'source_url': 'https://example.org/source'}],
            'evidence': {'verbose': 'not needed in the page'},
        }
        report = dict(inventory_sha256='inventory-hash', generated_at='2026-11-13',
                      summary={}, proposals=[row])
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.json', Path(directory) / 'review.html'
            source.write_text(json.dumps(report), encoding='utf-8')
            render(source, output)
            html = output.read_text(encoding='utf-8')
        embedded = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1)
        self.assertNotIn('<', embedded)
        self.assertEqual(json.loads(embedded)['proposals'],
                         [{k: v for k, v in row.items() if k != 'evidence'}])
        self.assertEqual(json.loads(embedded)['inventory_sha256'], 'inventory-hash')
