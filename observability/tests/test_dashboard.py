import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    def test_panels_have_unique_ids_and_explain_their_signals(self):
        dashboard = json.loads((ROOT / "dashboards/diary-sharing.json").read_text())
        self.assertEqual(dashboard["uid"], "diary-sharing")
        self.assertNotIn("test-alert-delivery", json.dumps(dashboard))
        panels = dashboard["panels"]
        self.assertEqual(len({panel["id"] for panel in panels}), len(panels))
        for panel in panels:
            self.assertNotEqual(panel["type"], "text")
            self.assertTrue(panel["description"])
            self.assertEqual(panel["datasource"]["uid"], "prometheus")
            self.assertTrue(panel["targets"])

    def test_product_ratios_keep_their_denominators_and_empty_state(self):
        panels = json.loads((ROOT / "dashboards/diary-sharing.json").read_text())["panels"]
        adoption = next(panel for panel in panels if panel["id"] == 2)
        followup = next(panel for panel in panels if panel["id"] == 4)
        self.assertIn("/ clamp_min(diary_logging_patients", adoption["targets"][0]["expr"])
        self.assertIn("/ clamp_min(diary_sharing_followup_eligible", followup["targets"][0]["expr"])
        self.assertIn("== bool 0", followup["targets"][0]["expr"])
        defaults = followup["fieldConfig"]["defaults"]
        self.assertEqual(defaults["noValue"], "Unavailable — check health")
        mapping = defaults["mappings"][0]["options"]
        self.assertEqual(mapping["-1"]["text"], "Not enough follow-up")
        self.assertNotIn("or vector(0)", followup["targets"][0]["expr"])
