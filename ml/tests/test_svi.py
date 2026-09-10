"""SVI engine tests. Standard library unittest so they run with no install."""

import unittest

from ml.svi import compute
from ml.svi.dimensions import DIMENSION_ORDER, WEIGHTS


def full(score=50.0, conf=0.9):
    scores = {d: score for d in DIMENSION_ORDER}
    confs = {d: conf for d in DIMENSION_ORDER}
    return scores, confs


class TestWeightedScore(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0, places=6)

    def test_uniform_scores_produce_that_score(self):
        scores, confs = full(50.0)
        result = compute(scores, confs, {})
        self.assertFalse(result["needs_human"])
        self.assertAlmostEqual(result["svi"], 50.0, places=2)

    def test_band_boundaries(self):
        cases = [(10.0, "Low"), (40.0, "Moderate"), (60.0, "High")]
        for score, band in cases:
            scores, confs = full(score)
            self.assertEqual(compute(scores, confs, {})["band"], band, msg=score)

    def test_breakdown_covers_every_dimension(self):
        scores, confs = full()
        breakdown = compute(scores, confs, {})["breakdown"]
        self.assertEqual([b["dimension"] for b in breakdown], list(DIMENSION_ORDER))
        for entry in breakdown:
            self.assertTrue(entry["weight_is_provisional"])

    def test_scores_are_clamped(self):
        scores, confs = full()
        scores["D1"] = 5000.0
        result = compute(scores, confs, {})
        self.assertLessEqual(result["svi"], 100.0)


class TestHardOverrides(unittest.TestCase):
    def test_confirmed_d1_forces_critical_over_a_low_weighted_score(self):
        scores = {d: 0.0 for d in DIMENSION_ORDER}
        confs = {d: 0.9 for d in DIMENSION_ORDER}
        scores["D1"] = 90.0
        result = compute(scores, confs, {})
        self.assertEqual(result["band"], "Critical")
        self.assertIn("D1_confirmed_forces_critical", result["overrides_applied"])

    def test_confirmed_d2_forces_critical(self):
        scores = {d: 0.0 for d in DIMENSION_ORDER}
        confs = {d: 0.9 for d in DIMENSION_ORDER}
        scores["D2"] = 85.0
        self.assertEqual(compute(scores, confs, {})["band"], "Critical")

    def test_crisis_interrupt_forces_critical_regardless_of_scores(self):
        scores = {d: 0.0 for d in DIMENSION_ORDER}
        confs = {d: 0.9 for d in DIMENSION_ORDER}
        result = compute(scores, confs, {"crisis_interrupt_fired": True})
        self.assertEqual(result["band"], "Critical")
        self.assertTrue(result["needs_human"])

    def test_immediate_danger_confirmed_forces_critical(self):
        scores, confs = full(5.0)
        result = compute(scores, confs, {"immediate_danger_confirmed": True})
        self.assertEqual(result["band"], "Critical")

    def test_low_confidence_d1_does_not_force_critical(self):
        scores = {d: 0.0 for d in DIMENSION_ORDER}
        confs = {d: 0.9 for d in DIMENSION_ORDER}
        scores["D1"] = 95.0
        confs["D1"] = 0.2
        result = compute(scores, confs, {})
        self.assertEqual(result["overrides_applied"], [])


class TestAbstention(unittest.TestCase):
    def test_low_aggregate_confidence_returns_needs_human_and_no_score(self):
        scores, confs = full(80.0, conf=0.10)
        result = compute(scores, confs, {})
        self.assertTrue(result["needs_human"])
        self.assertIsNone(result["svi"])
        self.assertIsNone(result["band"])
        self.assertIn("aggregate_confidence_below_floor", result["abstention_reasons"])

    def test_poor_audio_returns_needs_human_and_no_score(self):
        scores, confs = full()
        result = compute(scores, confs, {"poor_audio": True})
        self.assertTrue(result["needs_human"])
        self.assertIsNone(result["svi"])

    def test_low_language_confidence_returns_needs_human(self):
        scores, confs = full()
        result = compute(scores, confs, {"low_language_confidence": True})
        self.assertTrue(result["needs_human"])
        self.assertIsNone(result["svi"])

    def test_consent_declined_suppresses_scoring_entirely(self):
        scores, confs = full(95.0)
        result = compute(scores, confs, {"consent_declined": True, "crisis_interrupt_fired": True})
        self.assertIsNone(result["svi"])
        self.assertIsNone(result["band"])
        self.assertEqual(result["overrides_applied"], [])
        self.assertIn("consent_declined", result["abstention_reasons"])

    def test_no_dimensions_scored_abstains(self):
        result = compute({}, {}, {})
        self.assertTrue(result["needs_human"])
        self.assertIsNone(result["svi"])


if __name__ == "__main__":
    unittest.main()
