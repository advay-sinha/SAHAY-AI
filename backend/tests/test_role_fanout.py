"""Role-filtered fan-out: a victim token must never receive assessment events.

CONTRACTS.md section 3 names this file explicitly. Standard library unittest,
so it runs before EXT-001 is approved:
    python -m unittest discover -s backend/tests -t .
"""

import unittest

from backend.app.ws.events import (
    EXECUTIVE_ONLY,
    ROLE_EXECUTIVE,
    ROLE_SUPERVISOR,
    ROLE_VICTIM,
    VICTIM_ALLOWED,
)
from backend.app.ws.fanout import LeakageError, fan_out, filter_event, find_leaks, is_allowed

ASSESSMENT_PAYLOAD = {
    "dims": {"D1": {"score": 90, "conf": 0.9, "evidence_turn_ids": [3]}},
    "svi": 82.4,
    "band": "Critical",
    "needs_human": False,
    "overrides_applied": ["D1_confirmed_forces_critical"],
}


class TestAllowlist(unittest.TestCase):
    def test_victim_may_not_receive_any_executive_event(self):
        for event in EXECUTIVE_ONLY:
            self.assertFalse(is_allowed(ROLE_VICTIM, event), msg=event)
            self.assertIsNone(filter_event(ROLE_VICTIM, event, ASSESSMENT_PAYLOAD), msg=event)

    def test_executive_may_receive_executive_events(self):
        for event in EXECUTIVE_ONLY:
            self.assertTrue(is_allowed(ROLE_EXECUTIVE, event), msg=event)

    def test_supervisor_may_receive_executive_events(self):
        for event in EXECUTIVE_ONLY:
            self.assertTrue(is_allowed(ROLE_SUPERVISOR, event), msg=event)

    def test_victim_may_receive_the_five_victim_events(self):
        for event in VICTIM_ALLOWED:
            self.assertTrue(is_allowed(ROLE_VICTIM, event), msg=event)

    def test_officer_message_reaches_the_victim_but_never_with_assessment_data(self):
        # PC-07: allowed only as the plain human-officer message.
        clean = {"turn_id": "t9", "text": "An officer is here.", "lang": "en",
                 "ts": "2026-09-11T00:00:00+00:00", "origin": "human_officer"}
        self.assertIn("officer.message", VICTIM_ALLOWED)
        self.assertIsNotNone(filter_event(ROLE_VICTIM, "officer.message", clean))
        for leak in ({"band": "High"}, {"svi": 50}, {"alert": {"severity": "high"}}, {"confidence": 0.9}):
            with self.assertRaises(LeakageError, msg=leak):
                filter_event(ROLE_VICTIM, "officer.message", {**clean, **leak})

    def test_the_two_sets_do_not_overlap(self):
        self.assertEqual(VICTIM_ALLOWED & EXECUTIVE_ONLY, frozenset())

    def test_an_unknown_event_is_denied_to_a_victim_by_default(self):
        self.assertFalse(is_allowed(ROLE_VICTIM, "some.future.event"))
        self.assertIsNone(filter_event(ROLE_VICTIM, "some.future.event", {}))

    def test_an_unknown_role_receives_nothing(self):
        for event in VICTIM_ALLOWED | EXECUTIVE_ONLY:
            self.assertIsNone(filter_event("attacker", event, {}), msg=event)


class TestPayloadLeakage(unittest.TestCase):
    def test_find_leaks_walks_nested_structures(self):
        payload = {"a": [{"b": {"svi": 1}}]}
        self.assertEqual(find_leaks(payload), ["a[0].b.svi"])

    def test_find_leaks_is_case_insensitive(self):
        self.assertTrue(find_leaks({"Band": "Critical"}))

    def test_a_clean_victim_payload_has_no_leaks(self):
        payload = {"turn_id": "t1", "text": "Are you safe right now?", "lang": "hi"}
        self.assertEqual(find_leaks(payload), [])

    def test_an_allowed_event_carrying_assessment_data_raises(self):
        # assistant.turn is victim-allowed, but this payload was widened wrongly.
        with self.assertRaises(LeakageError):
            filter_event(ROLE_VICTIM, "assistant.turn", {"turn_id": "t1", "band": "Critical"})

    def test_the_leak_is_not_silently_stripped(self):
        # Stripping would hide the bug. It must fail loudly during tests.
        with self.assertRaises(LeakageError):
            filter_event(ROLE_VICTIM, "session.status", {"state": "S2", "dims": {}})

    def test_an_executive_payload_may_carry_assessment_data(self):
        event = filter_event(ROLE_EXECUTIVE, "dimension.update", ASSESSMENT_PAYLOAD)
        self.assertIsNotNone(event)
        self.assertEqual(event["band"], "Critical")


class TestFanOut(unittest.TestCase):
    def test_a_mixed_room_delivers_only_to_the_executive(self):
        subscribers = [("victim-1", ROLE_VICTIM), ("exec-1", ROLE_EXECUTIVE)]
        delivery = fan_out(subscribers, "alert.safety", {"type": "crisis", "severity": "critical"})
        self.assertIn("exec-1", delivery)
        self.assertNotIn("victim-1", delivery)

    def test_a_victim_event_reaches_both(self):
        subscribers = [("victim-1", ROLE_VICTIM), ("exec-1", ROLE_EXECUTIVE)]
        delivery = fan_out(subscribers, "assistant.turn", {"turn_id": "t1", "text": "ok", "lang": "hi"})
        self.assertEqual(set(delivery), {"victim-1", "exec-1"})

    def test_a_payload_can_never_rename_the_event(self):
        # Regression: the frozen alert.safety shape has its own `type` field,
        # which used to overwrite "alert.safety" in the delivered frame.
        event = filter_event(ROLE_EXECUTIVE, "alert.safety", {"type": "threat", "severity": "high"})
        self.assertEqual(event["type"], "alert.safety")
        spoof = filter_event(ROLE_VICTIM, "session.status", {"type": "dimension.update", "state": "S1"})
        self.assertEqual(spoof["type"], "session.status")

    def test_every_delivered_event_carries_its_type(self):
        delivery = fan_out([("exec-1", ROLE_EXECUTIVE)], "escalation.packet", {"case_id": "c1"})
        self.assertEqual(delivery["exec-1"]["type"], "escalation.packet")


if __name__ == "__main__":
    unittest.main()
