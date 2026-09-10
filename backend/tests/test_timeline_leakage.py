"""The victim-safe timeline must contain no assessment field.

CONTRACTS.md section 4: GET /cases/{id}/timeline "must contain no assessment
field". Standard library unittest.
"""

import unittest

from backend.app.services.timeline import (
    TIMELINE_ENTRY_KEYS,
    project,
    timeline_entry,
    victim_timeline,
)
from backend.app.ws.fanout import find_leaks

INTERNAL_ENTRIES = [
    {
        "stage": "under_review",
        "label": "Your request is being reviewed",
        "ts": "2026-09-10T10:00:00Z",
        # Everything below is internal and must not survive the projection.
        "svi": 82.4,
        "band": "Critical",
        "dims": {"D1": {"score": 90}},
        "alerts": [{"type": "crisis"}],
        "confidence": 0.91,
        "officer_id": "off-3",
        "recommendations": [{"action_id": "a1"}],
    }
]


class TestTimelineProjection(unittest.TestCase):
    def test_projection_keeps_only_the_contract_keys(self):
        projected = project(INTERNAL_ENTRIES)
        self.assertEqual(set(projected[0]), set(TIMELINE_ENTRY_KEYS))

    def test_projection_drops_every_assessment_field(self):
        self.assertEqual(find_leaks(project(INTERNAL_ENTRIES)), [])

    def test_the_full_response_body_has_no_leaks(self):
        body = victim_timeline("NHAA-2026-0001", INTERNAL_ENTRIES)
        self.assertEqual(find_leaks(body), [])
        self.assertEqual(body["reference"], "NHAA-2026-0001")

    def test_an_allowlist_not_a_denylist(self):
        # A field invented after this test was written must still be dropped.
        entry = dict(INTERNAL_ENTRIES[0])
        entry["some_future_score"] = 99
        projected = project([entry])
        self.assertNotIn("some_future_score", projected[0])

    def test_a_clean_entry_survives_intact(self):
        entry = timeline_entry("recorded", "Your account has been recorded", "2026-09-10T10:00:00Z")
        self.assertEqual(project([entry])[0], entry)


if __name__ == "__main__":
    unittest.main()
