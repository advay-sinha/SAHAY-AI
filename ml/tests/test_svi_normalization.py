"""PC-08 renormalisation (lead decision 2026-09-11). Standard library unittest.

Rules under test:
  * rescale only over a STRUCTURALLY unavailable dimension (D4 on a typed
    channel): normalized_svi = weighted_sum_available / sum_available_weights,
    denominator 0.88 with only D4 absent;
  * the absent dimension is reported unavailable -- never scored, never zero;
  * a dimension missing for any other reason (poor audio, runtime failure,
    low confidence) is NOT rescaled; abstention decides;
  * hard overrides apply independently; band thresholds apply to the
    normalised value;
  * the record (scoring version, available/unavailable dimensions, factor)
    travels with the result, and contributions explain the score exactly.
"""

import unittest

from ml.assessment import assess
from ml.svi import compute
from ml.svi.dimensions import DIMENSION_ORDER, SCORING_VERSION, WEIGHTS, band_for

TEXT = {"structurally_unavailable": ["D4"]}
NOT_D4 = [d for d in DIMENSION_ORDER if d != "D4"]
THREAT_TURN = [{"id": "t1", "speaker": "victim", "state": "S1",
                "text": "They threatened to burn our house and I am very scared tonight."}]


def without_d4(score=50.0, conf=0.9, **overrides):
    scores = {d: score for d in NOT_D4}
    scores.update(overrides)
    return scores, {d: conf for d in scores}


class TestFormula(unittest.TestCase):
    def test_denominator_is_088_with_only_d4_absent(self):
        r = compute(*without_d4(), TEXT)
        self.assertAlmostEqual(r["weight_denominator"], 0.88, places=6)
        self.assertAlmostEqual(r["normalization_factor"], round(1 / 0.88, 6), places=6)
        self.assertEqual(r["structurally_unavailable"], ["D4"])
        self.assertEqual(r["available_dimensions"], NOT_D4)
        self.assertEqual(r["scoring_version"], SCORING_VERSION)

    def test_uniform_available_scores_normalise_to_that_score(self):
        for v in (0.0, 20.0, 50.0, 80.0, 100.0):
            r = compute(*without_d4(v), TEXT)
            self.assertAlmostEqual(r["svi"], v, places=2, msg=v)

    def test_formula_matches_hand_computation(self):
        scores, confs = without_d4(D1=40.0, D3=70.0, D6=10.0, D9=90.0)
        expected = sum(WEIGHTS[d] * scores[d] for d in NOT_D4) / 0.88
        self.assertAlmostEqual(compute(scores, confs, TEXT)["svi"], round(expected, 2), places=2)

    def test_no_declaration_means_no_rescale(self):
        scores, confs = without_d4(50.0)
        r = compute(scores, confs, {})
        self.assertAlmostEqual(r["weight_denominator"], 1.0, places=6)
        self.assertEqual(r["structurally_unavailable"], [])
        # D4 missing but available: its weight counts as zero evidence.
        self.assertAlmostEqual(r["svi"], 44.0, places=2)


class TestD4IsNeverPretended(unittest.TestCase):
    def test_d4_is_reported_unavailable_not_zero(self):
        r = compute(*without_d4(), TEXT)
        d4 = next(b for b in r["breakdown"] if b["dimension"] == "D4")
        self.assertIsNone(d4["score"])
        self.assertIsNone(d4["confidence"])
        self.assertIsNone(d4["contribution"])
        self.assertFalse(d4["scored"])
        self.assertFalse(d4["available"])
        self.assertEqual(d4["effective_weight"], 0.0)
        self.assertEqual(d4["unavailable_reason"], "structurally_unavailable_for_channel")

    def test_declared_dimension_with_a_score_is_rejected(self):
        scores, confs = without_d4()
        scores["D4"], confs["D4"] = 0.0, 0.9
        with self.assertRaises(ValueError):
            compute(scores, confs, TEXT)

    def test_only_d4_may_be_structurally_unavailable(self):
        scores, confs = without_d4()
        for dim in ("D1", "D2", "D7"):
            with self.assertRaises(ValueError, msg=dim):
                compute(scores, confs, {"structurally_unavailable": [dim]})
        with self.assertRaises(ValueError):
            compute(scores, confs, {"structurally_unavailable": ["D10"]})

    def test_text_assessment_never_scores_d4(self):
        for channel in ("mobile_chat", "portal_chat"):
            r = assess(THREAT_TURN, True, channel=channel)
            self.assertIsNone(r["dims"]["D4"]["score"], msg=channel)
            d4 = next(b for b in r["breakdown"] if b["dimension"] == "D4")
            self.assertIsNone(d4["score"])
            self.assertFalse(d4["available"])


class TestNoRescaleForOtherAbsence(unittest.TestCase):
    def test_poor_audio_abstains_and_is_not_rescaled(self):
        r = compute(*without_d4(60.0), {"poor_audio": True})
        self.assertTrue(r["needs_human"])
        self.assertIsNone(r["svi"])
        self.assertIn("poor_audio_quality", r["abstention_reasons"])
        self.assertAlmostEqual(r["weight_denominator"], 1.0, places=6)

    def test_low_confidence_abstains(self):
        scores, confs = without_d4(60.0, conf=0.2)
        r = compute(scores, confs, TEXT)
        self.assertTrue(r["needs_human"])
        self.assertIn("aggregate_confidence_below_floor", r["abstention_reasons"])
        self.assertIsNone(r["band"])

    def test_missing_available_dimension_is_not_rescaled(self):
        scores, confs = without_d4(50.0)
        del scores["D7"], confs["D7"]
        r = compute(scores, confs, TEXT)
        self.assertAlmostEqual(r["weight_denominator"], 0.88, places=6)
        self.assertAlmostEqual(r["svi"], round(50.0 * (0.88 - 0.08) / 0.88, 2), places=2)

    def test_audio_channel_without_acoustic_measurement_abstains(self):
        for channel in ("mobile_voice", "upload"):
            r = assess(THREAT_TURN, True, channel=channel)
            self.assertIn("acoustic_not_measured", r["abstention_reasons"], msg=channel)
            self.assertIsNone(r["band"])
            self.assertEqual(r["normalization"]["structurally_unavailable"], [])
            self.assertAlmostEqual(r["normalization"]["weight_denominator"], 1.0, places=6)
            self.assertIsNone(r["dims"]["D4"]["score"])

    def test_unknown_channel_is_rejected(self):
        with self.assertRaises(ValueError):
            assess([], True, channel="chat")


class TestBoundaries(unittest.TestCase):
    def test_band_thresholds_apply_to_the_normalised_value(self):
        # Uniform value v normalises to exactly v, so each threshold is exercised.
        # D1/D2 confidence stays under the override minimum (0.60) so the
        # weighted band, not the hard override, is what is being tested.
        for v, band in ((29.99, "Low"), (30.0, "Moderate"), (54.99, "Moderate"),
                        (55.0, "High"), (74.99, "High"), (75.0, "Critical")):
            scores, confs = without_d4(v)
            confs.update(D1=0.55, D2=0.55)
            r = compute(scores, confs, TEXT)
            self.assertEqual(r["overrides_applied"], [], msg=v)
            self.assertEqual(r["band"], band, msg=v)

    def test_band_for_has_no_gaps_between_bands(self):
        self.assertEqual(band_for(29.5), "Low")
        self.assertEqual(band_for(54.5), "Moderate")
        self.assertEqual(band_for(74.5), "High")

    def test_normalisation_can_cross_a_band_upwards(self):
        # 60 on eight dims: 52.8 un-normalised (Moderate) vs 60 normalised (High).
        scores, confs = without_d4(60.0)
        self.assertEqual(compute(scores, confs, {})["band"], "Moderate")
        self.assertEqual(compute(scores, confs, TEXT)["band"], "High")

    def test_hard_override_is_independent_of_normalisation(self):
        scores, confs = without_d4(10.0)
        for quality in ({"crisis_interrupt_fired": True}, {"immediate_danger_confirmed": True}):
            r = compute(scores, confs, {**TEXT, **quality})
            self.assertEqual(r["band"], "Critical")
            self.assertTrue(r["overrides_applied"])
            self.assertAlmostEqual(r["weight_denominator"], 0.88, places=6)

    def test_consent_declined_still_suppresses(self):
        r = compute(*without_d4(90.0), {**TEXT, "consent_declined": True})
        self.assertIsNone(r["svi"])
        self.assertIsNone(r["band"])


class TestSensitivityAndDeterminism(unittest.TestCase):
    def test_ten_points_move_svi_by_ten_times_the_effective_weight(self):
        base_scores, confs = without_d4(50.0)
        base = compute(base_scores, confs, TEXT)["svi"]
        for dim in NOT_D4:
            bumped = dict(base_scores, **{dim: 60.0})
            delta = compute(bumped, confs, TEXT)["svi"] - base
            self.assertAlmostEqual(delta, 10.0 * WEIGHTS[dim] / 0.88, places=1, msg=dim)

    def test_monotone_in_every_available_dimension(self):
        scores, confs = without_d4(40.0)
        lo = compute(scores, confs, TEXT)["svi"]
        for dim in NOT_D4:
            hi = compute(dict(scores, **{dim: 90.0}), confs, TEXT)["svi"]
            self.assertGreater(hi, lo, msg=dim)

    def test_same_input_same_output(self):
        scores, confs = without_d4(47.3, D1=12.0, D8=88.0)
        self.assertEqual(compute(scores, confs, TEXT), compute(scores, confs, TEXT))
        self.assertEqual(assess(THREAT_TURN, True, channel="mobile_chat"),
                         assess(THREAT_TURN, True, channel="mobile_chat"))

    def test_aggregate_confidence_is_normalised_too(self):
        r = compute(*without_d4(50.0, conf=0.9), TEXT)
        self.assertAlmostEqual(r["aggregate_confidence"], 0.9, places=4)


class TestExplanation(unittest.TestCase):
    def test_contributions_sum_to_the_svi(self):
        scores, confs = without_d4(33.0, D1=71.0, D5=12.0)
        r = compute(scores, confs, TEXT)
        total = sum(b["contribution"] for b in r["breakdown"] if b["contribution"] is not None)
        self.assertAlmostEqual(total, r["svi"], places=1)

    def test_effective_weights_sum_to_one(self):
        r = compute(*without_d4(), TEXT)
        self.assertAlmostEqual(sum(b["effective_weight"] for b in r["breakdown"]), 1.0, places=5)

    def test_assessment_carries_the_normalisation_record(self):
        r = assess(THREAT_TURN, True, channel="portal_chat")
        n = r["normalization"]
        self.assertEqual(n["scoring_version"], SCORING_VERSION)
        self.assertEqual(n["channel"], "portal_chat")
        self.assertEqual(n["structurally_unavailable"], ["D4"])
        self.assertAlmostEqual(n["weight_denominator"], 0.88, places=6)
        self.assertIn("not measured, not zero", r["uncertainty"]["acoustic"])


if __name__ == "__main__":
    unittest.main()
