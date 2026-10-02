"""Advisory signal service (EXT-133, PC-14): request parsing and the shown-label filter."""

import unittest

from ml.shadow.service import SHOWN_LABELS, ServiceError, SignalEngine, check_bind_host, parse_request, to_signal

RESULT = {
    "status": "loaded", "deployment_status": "rejected_for_product_integration",
    "probabilities": {"crisis_self_harm": 0.81, "immediate_danger": 0.9, "legal_urgency": 0.06,
                      "communication_safety_coercion": 0.12, "medical_urgency": 0.7},
    "development_firings": {"crisis_self_harm": True, "immediate_danger": True, "medical_urgency": True},
}


class TestSignalService(unittest.TestCase):
    def test_only_the_three_gated_labels_leave_the_process(self):
        out = to_signal(RESULT)
        self.assertEqual(set(out["labels"]), set(SHOWN_LABELS))
        self.assertTrue(out["advisory"] and out["uncalibrated"])
        self.assertEqual(out["labels"]["crisis_self_harm"], {"probability": 0.81, "fired": True})
        self.assertNotIn("immediate_danger", str(out))

    def test_unloaded_results_carry_no_labels(self):
        self.assertEqual(to_signal({"status": "unavailable"})["labels"], {})
        self.assertEqual(to_signal({"status": "weird"})["status"], "failed")

    def test_requests_are_bounded(self):
        self.assertEqual(parse_request(b'{"texts": ["a", "b"]}'), ["a", "b"])
        for body in (b"[]", b'{"texts": []}', b'{"texts": [1]}', b"not json", b'{"texts": ["x"]}' + b" " * 70000):
            with self.assertRaises(ServiceError):
                parse_request(body)

    def test_loopback_only_and_injectable_engine(self):
        with self.assertRaises(ServiceError):
            check_bind_host("0.0.0.0")
        engine = SignalEngine(classify=lambda texts: RESULT)
        self.assertTrue(engine.ready)
        self.assertEqual(engine.signals(["x"])["labels"]["legal_urgency"]["fired"], False)


if __name__ == "__main__":
    unittest.main()
