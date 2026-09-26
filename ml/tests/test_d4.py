"""D4 from voice: in-session prosodic deviation, the D-8 cap and SAFE-SIGNAL (plan M12h).

Standard library only. The prosody features are synthetic numbers, not recordings.
"""

import unittest

from ml.acoustics import d4
from ml.assessment import assess


def feats(f0=150.0, std=1.0, level=-30.0, pauses=0.1, rng=4.0):
    return {"f0_median_hz": f0, "f0_std_st": std, "f0_range_st": rng, "f0_perturbation": 0.01,
            "voiced_ratio": 0.6, "rms_mean_db": level, "rms_std_db": 5.0, "pause_ratio": pauses,
            "pause_count": 1, "mean_pause_s": 0.3, "max_pause_s": 0.3, "speech_rate_wps": 2.5,
            "response_latency_s": None}


def vturn(i, text="I went to the office to ask about the form.", poor=False, ser=None, **kw):
    asr = {"confidence": 0.85, "poor_audio": poor, "low_asr_confidence": False,
           "prosody": feats(**kw), "prosody_reasons": []}
    if ser is not None:
        asr["ser"] = ser
    return {"id": f"t{i}", "speaker": "victim", "text": text, "state": "S1", "asr": asr}


class TestScore(unittest.TestCase):
    def test_needs_a_baseline_and_a_comparison_turn(self):
        out = d4.score_d4([vturn(1), vturn(2)])
        self.assertIsNone(out["score"])
        self.assertEqual(out["reason"], "insufficient_usable_voice_turns")

    def test_raised_pitch_loudness_and_pausing_raise_d4_with_evidence(self):
        calm = [vturn(1), vturn(2)]
        out = d4.score_d4(calm + [vturn(3, f0=150.0 * 2 ** (4 / 12), level=-22.0, pauses=0.4)])
        self.assertGreater(out["score"], 50)
        self.assertEqual(out["evidence_turn_ids"], ["t3"])
        self.assertLessEqual(out["confidence"], d4.MAX_CONFIDENCE)

    def test_steady_or_quieter_speech_adds_nothing(self):
        out = d4.score_d4([vturn(1), vturn(2), vturn(3), vturn(4, f0=120.0, level=-40.0, pauses=0.0)])
        self.assertEqual(out["score"], 0.0)
        self.assertEqual(out["evidence_turn_ids"], [])

    def test_poor_audio_turns_are_excluded(self):
        out = d4.score_d4([vturn(1), vturn(2, poor=True), vturn(3, f0=300.0)])
        self.assertIsNone(out["score"])

    def test_confidence_is_capped(self):
        turns = [vturn(i) for i in range(1, 20)]
        self.assertEqual(d4.score_d4(turns)["confidence"], d4.MAX_CONFIDENCE)


class TestSerCap(unittest.TestCase):
    def test_ser_is_off_by_default(self):
        self.assertFalse(d4.SER_ENABLED)
        turns = [vturn(1), vturn(2), vturn(3, ser={"fearful": 0.9, "neutral": 0.1})]
        self.assertEqual(d4.score_d4(turns)["score"], 0.0)

    def test_ser_share_never_exceeds_thirty_percent(self):
        self.assertEqual(d4.fuse(0.0, 100.0, enabled=True), 30.0)
        self.assertEqual(d4.fuse(100.0, 0.0, enabled=True), 70.0)
        self.assertEqual(d4.fuse(40.0, 100.0, enabled=False), 40.0)
        self.assertEqual(d4.ser_distress({"fearful": 0.5, "angry": 0.3, "sad": 0.4}), 100.0)


class TestSafeSignal(unittest.TestCase):
    def test_divergence_threshold_and_direction(self):
        self.assertIsNone(d4.safe_signal(50, 20))
        self.assertIsNone(d4.safe_signal(None, 90))
        out = d4.safe_signal(10, 90)
        self.assertEqual(out["direction"], "words_more_severe_than_voice")
        self.assertEqual(d4.safe_signal(90, 10)["direction"], "voice_more_distressed_than_words")
        for forbidden in ("band", "alert", "severity", "emotion", "diagnosis"):
            self.assertNotIn(forbidden, out)


class TestAssessIntegration(unittest.TestCase):
    def test_voice_session_with_enough_turns_is_measured_not_abstained_for_acoustics(self):
        turns = [vturn(1), vturn(2), vturn(3, f0=190.0, level=-24.0, pauses=0.3)]
        out = assess(turns, True, channel="mobile_voice")
        self.assertIsNotNone(out["dims"]["D4"]["score"])
        self.assertNotIn("acoustic_not_measured", out["abstention_reasons"])
        self.assertTrue(out["uncertainty"]["acoustic"].startswith("measured"))

    def test_too_few_voice_turns_still_abstains(self):
        out = assess([vturn(1)], True, channel="mobile_voice")
        self.assertIsNone(out["dims"]["D4"]["score"])
        self.assertIn("acoustic_not_measured", out["abstention_reasons"])

    def test_crisis_override_is_untouched_by_a_calm_voice(self):
        turns = [vturn(1), vturn(2), vturn(3, text="I want to kill myself tonight.")]
        out = assess(turns, True, channel="mobile_voice")
        self.assertEqual(out["band"], "Critical")
        self.assertEqual(out["uncertainty"]["safe_signal"]["direction"], "words_more_severe_than_voice")

    def test_typed_channel_is_unchanged(self):
        out = assess([{"id": "t1", "speaker": "victim", "text": "They threatened us again.", "state": "S1"}],
                     True, channel="mobile_chat")
        self.assertEqual(out["dims"]["D4"]["basis"], "structurally_unavailable_on_text_channel")
        self.assertIsNone(out["uncertainty"]["safe_signal"])


if __name__ == "__main__":
    unittest.main()
