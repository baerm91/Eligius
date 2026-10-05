from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Kontaktanfrage, Obj, ObjektAenderung


class AdminObjectChangeDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.goffo = get_user_model().objects.create_user(username='goffo', is_staff=True)
        cls.goffo.user_permissions.add(Permission.objects.get(
            content_type__app_label='slg', codename='view_objektaenderung',
        ))
        cls.other_admin = get_user_model().objects.create_superuser(
            username='other-admin', email='admin@example.test', password='test',
        )
        cls.obj = Obj.objects.bulk_create([
            Obj(invnr='TEST-123', titel='Bisheriger Objekttitel', Objekttyp=None, workflow=None),
        ])[0]
        cls.change = ObjektAenderung.objects.create(
            objekt=cls.obj, name='Testabsender', email='sender@example.test', feld='titel',
            alter_wert=cls.obj.titel, neuer_wert='Vorgeschlagener Objekttitel',
            begruendung='Korrektur nach dem Sammlungskatalog.',
        )
        for status in ('angenommen', 'abgelehnt'):
            ObjektAenderung.objects.create(
                objekt=cls.obj, name='Erledigt', email='done@example.test', feld='titel',
                alter_wert='Alter Titel', neuer_wert=f'Erledigter Vorschlag: {status}',
                begruendung='Bereits geprüft.', status=status,
            )

    def dashboard(self, user=None):
        self.client.force_login(user or self.goffo)
        return self.client.get(reverse('admin:index'))

    def test_goffo_sees_open_changes_and_direct_links_with_view_permission(self):
        response = self.dashboard()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['object_change_dashboard']['count'], 1)
        self.assertContains(response, 'Offene Objektänderungen')
        self.assertContains(response, 'Objekt TEST-123 · Titel')
        for value in (
            self.change.name, self.change.email, self.change.alter_wert,
            self.change.neuer_wert, self.change.begruendung,
        ):
            self.assertContains(response, value)
        self.assertContains(response, reverse(
            'admin:slg_objektaenderung_change', args=[self.change.pk],
        ))
        self.assertNotContains(response, 'Erledigter Vorschlag:')
        self.assertNotIn('contact_dashboard', response.context)

        listing = self.client.get(response.context['object_change_dashboard']['list_url'])
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(list(listing.context['cl'].queryset), [self.change])

    def test_only_five_newest_open_changes_are_previewed(self):
        now = timezone.now()
        changes = []
        for index in range(6):
            change = ObjektAenderung.objects.create(
                objekt=self.obj, name='Absender', email='sender@example.test', feld='titel',
                alter_wert='Alt', neuer_wert=f'Neuer Vorschlag {index}', begruendung='Korrektur',
            )
            ObjektAenderung.objects.filter(pk=change.pk).update(
                erstellt_am=now + timedelta(minutes=index + 1),
            )
            changes.append(change)

        response = self.dashboard()
        self.assertEqual(response.context['object_change_dashboard']['count'], 7)
        self.assertEqual(
            [change.pk for change in response.context['object_change_dashboard']['latest']],
            [change.pk for change in reversed(changes[1:])],
        )
        self.assertNotContains(response, self.change.neuer_wert)
        self.assertContains(response, 'die fünf neuesten offenen Objektänderungen')

    def test_accepting_or_rejecting_change_in_admin_clears_dashboard(self):
        self.goffo.user_permissions.add(Permission.objects.get(
            content_type__app_label='slg', codename='change_objektaenderung',
        ))
        self.client.force_login(self.goffo)
        for status in ('angenommen', 'abgelehnt'):
            with self.subTest(status=status):
                ObjektAenderung.objects.filter(pk=self.change.pk).update(status='offen')
                response = self.client.post(reverse(
                    'admin:slg_objektaenderung_change', args=[self.change.pk],
                ), {'status': status, '_save': 'Save'})
                self.assertEqual(response.status_code, 302)
                self.change.refresh_from_db()
                self.assertEqual(self.change.status, status)
                self.assertEqual(self.change.bearbeitet_von_id, self.goffo.pk)
                self.assertIsNotNone(self.change.bearbeitet_am)

                response = self.client.get(reverse('admin:index'))
                self.assertEqual(response.context['object_change_dashboard']['count'], 0)
                self.assertContains(response, 'Zurzeit gibt es keine offenen Objektänderungen.')
                self.assertNotContains(response, 'class="contact-dashboard-list"')

    def test_other_admin_does_not_query_or_see_object_change_preview(self):
        change_admin = admin.site._registry[ObjektAenderung]
        with patch.object(change_admin, 'get_queryset') as get_queryset:
            response = self.dashboard(self.other_admin)
        get_queryset.assert_not_called()
        self.assertNotIn('object_change_dashboard', response.context)
        self.assertNotContains(response, 'id="object-change-dashboard-title"')
        self.assertNotContains(response, self.change.neuer_wert)

    def test_contact_permission_alone_does_not_expose_object_changes(self):
        self.goffo.user_permissions.clear()
        self.goffo.user_permissions.add(Permission.objects.get(
            content_type__app_label='slg', codename='view_kontaktanfrage',
        ))
        change_admin = admin.site._registry[ObjektAenderung]
        with patch.object(change_admin, 'get_queryset') as get_queryset:
            response = self.dashboard()
        get_queryset.assert_not_called()
        self.assertNotIn('object_change_dashboard', response.context)
        self.assertNotContains(response, self.change.neuer_wert)
        self.assertIn('contact_dashboard', response.context)

    def test_inactive_or_nonstaff_goffo_does_not_get_object_change_context(self):
        for attribute in ('is_active', 'is_staff'):
            with self.subTest(attribute=attribute):
                user = get_user_model().objects.get(pk=self.goffo.pk)
                setattr(user, attribute, False)
                request = RequestFactory().get(reverse('admin:index'))
                request.user = user
                response = admin.site.index(request)
                self.assertNotIn('object_change_dashboard', response.context_data)

    def test_new_website_form_submission_appears_on_next_dashboard_load(self):
        response = self.client.post(reverse('objekt_aenderung', args=[self.obj.pk]), {
            'name': 'Neuer Absender', 'email': 'new@example.test', 'feld': 'avleg',
            'alter_wert': 'Bisherige Legende', 'neuer_wert': 'Korrigierte Legende',
            'begruendung': 'Die Legende wurde auf der Webseite falsch wiedergegeben.',
        })
        self.assertEqual(response.status_code, 302)

        response = self.dashboard()
        self.assertEqual(response.context['object_change_dashboard']['count'], 2)
        self.assertContains(response, 'Korrigierte Legende')
        self.assertContains(response, 'Vorderseite Legende')
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.titel, 'Bisheriger Objekttitel')

    def test_both_dashboards_are_visible_with_their_own_counts(self):
        self.goffo.user_permissions.add(Permission.objects.get(
            content_type__app_label='slg', codename='view_kontaktanfrage',
        ))
        Kontaktanfrage.objects.create(
            name='Kontaktabsender', email='contact@example.test',
            betreff='Eine Kontaktanfrage', nachricht='Nachricht',
        )

        response = self.dashboard()
        self.assertEqual(response.context['contact_dashboard']['count'], 1)
        self.assertEqual(response.context['object_change_dashboard']['count'], 1)
        self.assertContains(response, 'Eine Kontaktanfrage')
        self.assertContains(response, self.change.neuer_wert)

    def test_object_change_input_is_escaped_and_previews_are_limited(self):
        self.change.feld = '<script>alert("field")</script>'
        self.change.name = '<script>alert("name")</script>'
        self.change.alter_wert = '<script>alert("old")</script>' + 'x' * 300
        self.change.neuer_wert = '<script>alert("new")</script>' + 'x' * 300
        self.change.begruendung = '<script>alert("reason")</script>' + 'x' * 300
        self.change.save()

        response = self.dashboard()
        self.assertNotContains(response, '<script>alert(')
        self.assertContains(response, '&lt;script&gt;alert(')
        self.assertNotContains(response, 'x' * 300)
