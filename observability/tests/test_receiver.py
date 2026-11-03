import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from receiver import notification  # noqa: E402 - load the sibling receiver from this test directory


class ReceiverTests(unittest.TestCase):
    def test_only_safe_fields_are_kept(self):
        alert = {
            "status": "firing",
            "labels": {
                "alertname": "DiaryAuditWriteFailed",
                "severity": "critical",
                "environment": "private-environment",
                "patient": "private-patient",
            },
            "annotations": {"details": "private-note"},
            "generatorURL": "private-url",
        }
        result = notification(alert)
        self.assertEqual(
            result,
            {
                "alertname": "DiaryAuditWriteFailed",
                "status": "firing",
                "severity": "critical",
            },
        )
        self.assertNotIn("private", json.dumps(result))

    def test_unknown_alerts_and_statuses_are_not_retained(self):
        for name in ("private-name", "DiaryProductMetricsUnavailable", "DiaryAlertDeliveryFailed"):
            self.assertIsNone(notification({"labels": {"alertname": name}, "status": "firing"}))
        self.assertIsNone(
            notification(
                {"labels": {"alertname": "DiaryAuditWriteFailed"}, "status": "private-status"}
            )
        )

    def test_unapproved_severity_is_not_echoed(self):
        result = notification(
            {
                "status": "resolved",
                "labels": {"alertname": "DiaryAuditWriteFailed", "severity": "private-severity"},
            },
        )
        self.assertEqual(result["severity"], "unknown")
        self.assertEqual(set(result), {"alertname", "status", "severity"})
