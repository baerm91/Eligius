from datetime import datetime, timezone as datetime_timezone

from django.test import SimpleTestCase

from .views import _clean_export_invnrs, _export_datetime


class ExportCoinStateHelperTests(SimpleTestCase):
    def test_clean_export_invnrs_strips_empty_values_and_deduplicates(self):
        self.assertEqual(
            _clean_export_invnrs([" 1 ", "", None, "2", "1", " 2 "]),
            ["1", "2"],
        )

    def test_export_datetime_uses_isoformat_and_empty_string_for_none(self):
        value = datetime(2026, 5, 7, 5, 1, tzinfo=datetime_timezone.utc)

        self.assertEqual(_export_datetime(value), "2026-05-07T05:01:00+00:00")
        self.assertEqual(_export_datetime(None), "")
