from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.test import TestCase

from slg import mtoa_queue
from slg.admin import HerstellungAdmin
from slg.models import Herstellung, MtoaSyncAuftrag


class MtoaQueueTests(TestCase):
    def setUp(self):
        self.herstellung = Herstellung.objects.create(name='Prägung')

    def _save_name(self, objects_count):
        with mock.patch('slg.signals._authority_objects') as affected, \
                mock.patch('slg.signals._sync_queryset') as sync_inline, \
                mock.patch('slg.mtoa_queue.start_worker') as start:
            qs = mock.MagicMock()
            qs.values.return_value.distinct.return_value.__getitem__.return_value.count.return_value = objects_count
            affected.return_value = qs
            with self.captureOnCommitCallbacks(execute=True):
                self.herstellung.name = 'Prägung neu'
                self.herstellung.save()
        return sync_inline, start

    def test_few_objects_sync_inline(self):
        sync_inline, start = self._save_name(10)
        sync_inline.assert_called_once()
        start.assert_not_called()
        self.assertFalse(MtoaSyncAuftrag.objects.exists())

    def test_many_objects_are_queued_and_worker_started_after_commit(self):
        sync_inline, start = self._save_name(mtoa_queue.INLINE_LIMIT + 1)
        sync_inline.assert_not_called()
        start.assert_called_once()
        auftrag = MtoaSyncAuftrag.objects.get()
        self.assertEqual((auftrag.model_label, auftrag.object_pk), ('slg.Herstellung', self.herstellung.pk))

    def test_process_queue_syncs_and_removes_job(self):
        MtoaSyncAuftrag.objects.create(model_label='slg.Herstellung', object_pk=self.herstellung.pk)
        with mock.patch('slg.signals._sync_queryset') as sync:
            self.assertEqual(mtoa_queue.process_queue(), 1)
        sync.assert_called_once()
        self.assertFalse(MtoaSyncAuftrag.objects.exists())

    def test_failed_job_stays_for_retry(self):
        MtoaSyncAuftrag.objects.create(model_label='slg.Herstellung', object_pk=self.herstellung.pk)
        with mock.patch('slg.signals._sync_queryset', side_effect=RuntimeError('db weg')):
            self.assertEqual(mtoa_queue.process_queue(limit=1), 0)
        auftrag = MtoaSyncAuftrag.objects.get()
        self.assertEqual(auftrag.attempts, 1)
        self.assertIsNone(auftrag.claimed_at)
        self.assertIn('db weg', auftrag.last_error)

    def test_admin_without_changes_does_not_resync(self):
        model_admin = HerstellungAdmin(Herstellung, AdminSite())
        form = mock.Mock(changed_data=[])
        with mock.patch('slg.signals._sync_queryset') as sync:
            model_admin.save_model(None, self.herstellung, form, True)
        sync.assert_not_called()

    def test_admin_nomisma_only_does_not_resync(self):
        model_admin = HerstellungAdmin(Herstellung, AdminSite())
        self.herstellung.name_nom_id = 'https://nomisma.org/id/struck'
        form = mock.Mock(changed_data=['name_nom_id'])
        with mock.patch('slg.signals._sync_queryset') as sync:
            model_admin.save_model(None, self.herstellung, form, True)
        sync.assert_not_called()
        self.herstellung.refresh_from_db()
        self.assertEqual(self.herstellung.name_nom_id, 'https://nomisma.org/id/struck')
