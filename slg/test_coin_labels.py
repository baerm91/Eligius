from django.contrib import admin
from django.test import RequestFactory, TestCase

from .models import Obj
from .views import prepare_coin_labels_html


class CoinLabelTests(TestCase):
    def create_objects(self, count):
        return Obj.objects.bulk_create([
            Obj(
                invnr=f'LABEL-{index:03d}',
                titel='Marcus Aurelius & Lucius Verus <unsicher>' if index == 0 else '',
                Objekttyp=None,
                workflow=None,
            )
            for index in range(count)
        ])

    def test_admin_action_renders_only_selected_objects(self):
        objects = self.create_objects(3)
        response = admin.site._registry[Obj].create_coin_labels(
            RequestFactory().post('/admin/slg/obj/'),
            Obj.objects.filter(pk__in=[objects[0].pk, objects[1].pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(response['Content-Disposition'], 'inline; filename="unterlagszettel.html"')
        self.assertContains(response, 'class="card"', count=2)
        self.assertContains(response, '>LABEL-000</span>', count=1)
        self.assertContains(response, '>LABEL-001</span>', count=1)
        self.assertNotContains(response, 'LABEL-002')
        self.assertContains(response, 'Marcus Aurelius &amp; Lucius Verus &lt;unsicher&gt;')

    def test_more_than_forty_labels_use_multiple_sheets(self):
        objects = self.create_objects(41)
        response = prepare_coin_labels_html(Obj.objects.filter(pk__in=[obj.pk for obj in objects]))

        self.assertContains(response, 'class="sheet"', count=2)
        self.assertContains(response, 'class="card"', count=41)
        self.assertContains(response, '>LABEL-040</span>', count=1)
