from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Kontaktanfrage


class AdminContactDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.goffo = get_user_model().objects.create_user(
            username='goffo', is_staff=True,
        )
        cls.goffo.user_permissions.add(Permission.objects.get(
            content_type__app_label='slg', codename='view_kontaktanfrage',
        ))
        cls.other_admin = get_user_model().objects.create_superuser(
            username='other-admin', email='admin@example.test', password='test',
        )
        cls.contact = Kontaktanfrage.objects.create(
            name='Testabsender', email='sender@example.test',
            betreff='Frage zur Sammlung', nachricht='Eine Nachricht für die Übersicht.',
        )
        cls.processed = Kontaktanfrage.objects.create(
            name='Erledigt', email='done@example.test', betreff='Bereits bearbeitet',
            nachricht='Diese Anfrage ist abgeschlossen.', bearbeitet=True,
        )

    def dashboard(self, user=None):
        self.client.force_login(user or self.goffo)
        return self.client.get(reverse('admin:index'))

    def test_goffo_sees_open_contacts_and_direct_links_with_view_permission(self):
        response = self.dashboard()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['contact_dashboard']['count'], 1)
        self.assertContains(response, 'Offene Kontaktanfragen')
        self.assertContains(response, self.contact.betreff)
        self.assertContains(response, self.contact.name)
        self.assertContains(response, self.contact.email)
        self.assertContains(response, self.contact.nachricht)
        self.assertContains(response, reverse(
            'admin:slg_kontaktanfrage_change', args=[self.contact.pk],
        ))
        self.assertNotContains(response, self.processed.betreff)

        list_url = response.context['contact_dashboard']['list_url']
        listing = self.client.get(list_url)
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, self.contact.betreff)
        self.assertNotContains(listing, self.processed.betreff)

    def test_only_five_newest_open_contacts_are_previewed(self):
        now = timezone.now()
        contacts = []
        for index in range(6):
            contact = Kontaktanfrage.objects.create(
                name='Absender', email='sender@example.test',
                betreff=f'Neue Anfrage {index}', nachricht='Nachricht',
            )
            Kontaktanfrage.objects.filter(pk=contact.pk).update(
                erstellt_am=now + timedelta(minutes=index + 1),
            )
            contacts.append(contact)

        response = self.dashboard()
        self.assertEqual(response.context['contact_dashboard']['count'], 7)
        self.assertEqual(
            [contact.pk for contact in response.context['contact_dashboard']['latest']],
            [contact.pk for contact in reversed(contacts[1:])],
        )
        self.assertNotContains(response, self.contact.betreff)
        self.assertContains(response, 'die fünf neuesten offenen Anfragen')

    def test_marking_contact_processed_in_admin_clears_dashboard(self):
        self.goffo.user_permissions.add(Permission.objects.get(
            content_type__app_label='slg', codename='change_kontaktanfrage',
        ))
        self.client.force_login(self.goffo)
        response = self.client.post(reverse(
            'admin:slg_kontaktanfrage_change', args=[self.contact.pk],
        ), {'bearbeitet': 'on', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.bearbeitet)

        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.context['contact_dashboard']['count'], 0)
        self.assertContains(response, 'Zurzeit gibt es keine offenen Kontaktanfragen.')
        self.assertNotContains(response, 'class="contact-dashboard-list"')

    def test_other_admin_gets_existing_dashboard_without_contact_preview(self):
        contact_admin = admin.site._registry[Kontaktanfrage]
        with patch.object(contact_admin, 'get_queryset') as get_queryset:
            response = self.dashboard(self.other_admin)
        get_queryset.assert_not_called()
        self.assertNotIn('contact_dashboard', response.context)
        self.assertNotContains(response, 'id="contact-dashboard-title"')
        self.assertNotContains(response, self.contact.betreff)
        self.assertContains(response, 'id="recent-actions-module"')
        self.assertContains(response, reverse('admin:slg_obj_changelist'))

    def test_goffo_without_contact_permission_does_not_query_or_see_contacts(self):
        self.goffo.user_permissions.clear()
        contact_admin = admin.site._registry[Kontaktanfrage]
        with patch.object(contact_admin, 'get_queryset') as get_queryset:
            response = self.dashboard()
        get_queryset.assert_not_called()
        self.assertNotIn('contact_dashboard', response.context)
        self.assertNotContains(response, self.contact.betreff)

    def test_inactive_or_nonstaff_goffo_does_not_get_contact_context(self):
        for attribute in ('is_active', 'is_staff'):
            with self.subTest(attribute=attribute):
                user = get_user_model().objects.get(pk=self.goffo.pk)
                setattr(user, attribute, False)
                request = RequestFactory().get(reverse('admin:index'))
                request.user = user
                response = admin.site.index(request)
                self.assertNotIn('contact_dashboard', response.context_data)

    def test_anonymous_admin_request_redirects_to_login(self):
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('admin:login')))

    def test_new_contact_form_submission_appears_on_next_dashboard_load(self):
        response = self.client.post(reverse('kontakt'), {
            'name': 'Neuer Absender', 'email': 'new@example.test',
            'betreff': 'Neue Kontaktformular-Nachricht', 'nachricht': 'Neue Nachricht',
        })
        self.assertEqual(response.status_code, 302)

        response = self.dashboard()
        self.assertEqual(response.context['contact_dashboard']['count'], 2)
        self.assertContains(response, 'Neue Kontaktformular-Nachricht')

    def test_contact_input_is_escaped_and_message_preview_is_limited(self):
        self.contact.betreff = '<script>alert("subject")</script>'
        self.contact.name = '<script>alert("name")</script>'
        self.contact.nachricht = '<script>alert("message")</script>' + 'x' * 300
        self.contact.save()

        response = self.dashboard()
        self.assertNotContains(response, '<script>alert(')
        self.assertContains(response, '&lt;script&gt;alert(')
        self.assertNotContains(response, 'x' * 300)
