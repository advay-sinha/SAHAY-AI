"""PC-14 advisory model signals: sanitising, the review flag, officer-only delivery."""

import unittest
from unittest.mock import patch

from backend.tests.test_vertical_slice import HAVE_DEPS, TURNS, SliceBase, drain, recv_until

if HAVE_DEPS:
    from backend.app.adapters import signals as sig

FIRED = {"status": "loaded", "checkpoint_status": "rejected_for_product_integration",
         "labels": {"crisis_self_harm": {"probability": 0.91, "fired": True},
                    "legal_urgency": {"probability": 0.12, "fired": False}}}


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestSanitize(unittest.TestCase):
    def test_only_allowlisted_labels_and_fields_survive(self):
        raw = {**FIRED, "svi": 80, "band": "Critical",
               "labels": {**FIRED["labels"], "immediate_danger": {"probability": 0.9, "fired": True},
                          "legal_urgency": {"probability": 1.7, "fired": True}}}
        out = sig.sanitize(raw)
        self.assertEqual(set(out), {"status", "model", "checkpoint_status", "advisory", "uncalibrated", "labels"})
        self.assertEqual(set(out["labels"]), {"crisis_self_harm"})  # out-of-range probability dropped too
        self.assertTrue(out["advisory"] and out["uncalibrated"])

    def test_unusable_replies_give_no_signal(self):
        for raw in (None, [], {"status": "great"}, "text"):
            self.assertIsNone(sig.sanitize(raw))
        self.assertEqual(sig.sanitize({"status": "failed", "labels": FIRED["labels"]})["labels"], {})

    def test_flag_only_when_the_model_catches_what_the_rules_missed(self):
        s = sig.sanitize(FIRED)
        self.assertTrue(sig.with_flag(s, rules_crisis=False)["flag"])
        self.assertFalse(sig.with_flag(s, rules_crisis=True)["flag"])
        quiet = sig.sanitize({**FIRED, "labels": {"crisis_self_harm": {"probability": 0.2, "fired": False}}})
        self.assertFalse(sig.with_flag(quiet, rules_crisis=False)["flag"])
        self.assertIsNone(sig.with_flag(None, rules_crisis=False))


class _FakeProvider:
    name = "local_service"

    def signals(self, texts):
        return sig.sanitize(FIRED)


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestDelivery(SliceBase):
    def run_turns(self, s, turns):
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            for t in turns:
                self.say(ws, t)
        self.settle()

    def test_signal_reaches_officers_and_the_packet_but_never_the_victim(self):
        s = self.new_session(lang="hi")
        officer = self.login("exec1")
        with patch("backend.app.workers.assessment.get_signal_provider", return_value=_FakeProvider()):
            with self.client.websocket_connect(f"/ws/session/{s['session_id']}?token="
                                               f"{officer['Authorization'].split()[1]}") as exec_ws, \
                    self.client.websocket_connect(s["connect"]) as victim_ws:
                recv_until(exec_ws, "session.status")
                recv_until(victim_ws, "session.status")
                self.say(victim_ws, TURNS[0])
                self.settle()
                exec_frames = drain(exec_ws, timeout=1.0)
                victim_frames = drain(victim_ws, timeout=0.5)
        signals = [f for f in exec_frames if f["type"] == "model.signal"]
        self.assertEqual(len(signals), 1)
        self.assertTrue(signals[0]["flag"])
        self.assertEqual(set(signals[0]["labels"]), {"crisis_self_harm", "legal_urgency"})
        self.assertNotIn("model.signal", [f["type"] for f in victim_frames])
        for frame in victim_frames:
            self.assertNotIn("probability", str(frame))
        self.assertEqual(self.packet(s["case_id"])["model_signals"]["labels"]["crisis_self_harm"]["fired"], True)

    def test_mock_provider_and_declined_consent_show_no_signal(self):
        s = self.new_session(lang="hi")
        self.run_turns(s, TURNS[:1])
        self.assertIsNone(self.packet(s["case_id"])["model_signals"])
        d = self.new_session(consent="declined", lang="hi")
        with patch("backend.app.workers.assessment.get_signal_provider", return_value=_FakeProvider()):
            self.run_turns(d, TURNS[:1])
        self.assertIsNone(self.packet(d["case_id"])["model_signals"])


if __name__ == "__main__":
    unittest.main()
