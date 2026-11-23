import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from .operations import ServerErrorEmailHandler


class OperationLoggingTests(TestCase):
    def test_oai_protocol_error_logs_code_but_not_request_values(self):
        with self.assertLogs('slg.operations', level='INFO') as captured:
            response = self.client.get('/oai/', {'verb': 'ListSets', 'resumptionToken': 'private-token'})
        self.assertEqual(response.status_code, 200)
        event = json.loads(captured.records[0].getMessage())
        self.assertEqual(event['action'], 'ListSets')
        self.assertEqual(event['outcome'], 'protocol_error')
        self.assertEqual(event['error_code'], 'badResumptionToken')
        self.assertNotIn('private-token', captured.records[0].getMessage())

    @override_settings(DEBUG=False, ELIGIUS_ERROR_ALERT_RECIPIENTS=['operations@example.test'],
                       EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_alert_is_throttled_and_omits_request_data(self):
        cache.clear()
        request = SimpleNamespace(resolver_match=SimpleNamespace(view_name='oai_endpoint'),
                                  path='/oai/?resumptionToken=private-token')
        handler = ServerErrorEmailHandler()
        handler.emit(SimpleNamespace(status_code=400, request=request))
        handler.emit(SimpleNamespace(status_code=500, request=request))
        handler.emit(SimpleNamespace(status_code=500, request=request))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('oai_endpoint', mail.outbox[0].body)
        self.assertNotIn('private-token', mail.outbox[0].body)

    @override_settings(DEBUG=False, ELIGIUS_ERROR_ALERT_RECIPIENTS=[])
    @patch('slg.operations.send_mail')
    def test_no_email_without_configured_recipients(self, send_mail):
        ServerErrorEmailHandler().emit(SimpleNamespace(status_code=500))
        send_mail.assert_not_called()
