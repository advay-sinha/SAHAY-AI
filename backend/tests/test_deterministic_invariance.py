"""Controlled-MVP proof that experimental outcomes cannot affect authority."""

from pathlib import Path
import unittest

from ml.eval.predict import predict


SAMPLE = {
    "id": "FICTIONAL-INVARIANCE",
    "channel": "mobile_chat",
    "turns": [
        {
            "id": "fictional-turn-1",
            "speaker": "victim",
            "text": "I will kill myself now",
            "state": "S2",
        }
    ],
}


class TestDeterministicAuthority(unittest.TestCase):
    def authoritative_with_isolated_observer(self, observer):
        """The observer is deliberately outside and downstream of authority."""
        result = predict(SAMPLE)
        try:
            observer()
        except Exception:
            pass
        return result

    def test_all_optional_outcomes_leave_authoritative_output_identical(self):
        outcomes = {
            "fires": lambda: {"prediction": [1.0], "confidence": 1.0},
            "silent": lambda: None,
            "unavailable": lambda: (_ for _ in ()).throw(ImportError("unavailable")),
            "timeout": lambda: (_ for _ in ()).throw(TimeoutError("timeout")),
            "fails": lambda: (_ for _ in ()).throw(RuntimeError("failed")),
            "malformed": lambda: object(),
        }
        baseline = predict(SAMPLE)
        for name, observer in outcomes.items():
            with self.subTest(name=name):
                self.assertEqual(self.authoritative_with_isolated_observer(observer), baseline)
        self.assertTrue(baseline["crisis_precheck"])
        self.assertTrue(baseline["routed_critical"])
        self.assertEqual(baseline["d4"]["score"], None)
        self.assertEqual(baseline["d4"]["confidence"], None)
        self.assertEqual(baseline["d4"]["basis"], "structurally_unavailable_on_text_channel")

    def test_application_modules_do_not_import_experimental_packages(self):
        root = Path(__file__).resolve().parents[2]
        for area in (root / "backend" / "app", root / "frontend" / "src", root / "mobile" / "src"):
            for path in area.rglob("*"):
                if path.suffix not in {".py", ".ts", ".tsx", ".js"}:
                    continue
                source = path.read_text(encoding="utf-8")
                for package in ("shadow", "training"):
                    self.assertNotIn("ml." + package, source, str(path))


if __name__ == "__main__":
    unittest.main()
