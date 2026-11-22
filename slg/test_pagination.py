from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Obj, Person, Ref
from .test_bugfix_regressions import Fixtures


class OptInPaginationTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_data()
        cls.user = User.objects.create_user(username='api-reader')
        Obj.objects.create(Slg=cls.slg, Typ=cls.typ, invnr='PAGE-001')
        Person.objects.create(name='Person A')
        Ref.objects.bulk_create([Ref(abk='RIC') for _ in range(505)] + [Ref(abk='RPC')])

    def test_legacy_arrays_and_paginated_response_on_list_routes(self):
        self.client.force_login(self.user)
        for endpoint in ('objekt', 'muenztyp', 'person', 'ref'):
            with self.subTest(endpoint=endpoint):
                url = f'/api/{endpoint}/'
                legacy = self.client.get(url)
                page = self.client.get(url, {'page': 1})
                self.assertEqual(legacy.status_code, 200)
                self.assertEqual(page.status_code, 200)
                self.assertIsInstance(legacy.json(), list)
                self.assertEqual(page.json()['count'], len(legacy.json()))
                self.assertEqual(len(page.json()['results']), min(100, len(legacy.json())))

    def test_page_size_cap_and_filtered_links(self):
        response = self.client.get('/api/ref/', {'abk': 'RIC', 'page_size': 10000})
        self.assertEqual(response.status_code, 200)
        page = response.json()
        self.assertEqual(page['count'], 505)
        self.assertEqual(len(page['results']), 500)
        self.assertIsNone(page['previous'])

        next_url = urlsplit(page['next'])
        self.assertEqual(parse_qs(next_url.query)['abk'], ['RIC'])
        next_page = self.client.get(f'{next_url.path}?{next_url.query}').json()
        self.assertEqual(len(next_page['results']), 5)
        self.assertIsNone(next_page['next'])
        self.assertTrue(next_page['previous'])
        ids = [row['id'] for row in page['results'] + next_page['results']]
        self.assertEqual(ids, list(Ref.objects.filter(abk='RIC').order_by('pk').values_list('pk', flat=True)))

    def test_bad_page_sizes_and_missing_pages(self):
        for invalid in ('', '0', '-1', 'foo'):
            with self.subTest(page_size=invalid):
                response = self.client.get('/api/ref/', {'page_size': invalid})
                self.assertEqual(response.status_code, 400)
                self.assertIn('page_size', response.json())
        self.assertEqual(self.client.get('/api/ref/', {'page': 999}).status_code, 404)
