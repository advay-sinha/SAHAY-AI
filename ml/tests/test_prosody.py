"""Prosody features, baseline deviation, quality gate and signal measurement (plan M12a).

The prosody and quality tests are standard library only and run everywhere. The signal tests
need numpy (EXT-121). They run in the private model environment and are skipped in the
dependency-free default environment. Every signal is synthetic: no speech, no recording.
"""

import importlib.util
import math
import unittest

from ml.acoustics import prosody, quality

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HOP = prosody.FRAME_HOP_S


def _tracks(seconds, f0=None, level=-20.0):
    n = int(round(seconds / HOP))
    f0s = [f0(i) if callable(f0) else f0 for i in range(n)]
    return f0s, [level] * n


class TestPauseFeatures(unittest.TestCase):
    def test_pauses_inside_span_only(self):
        p = prosody.pause_features([(1.0, 2.0), (2.5, 3.0), (3.1, 4.0)])
        self.assertAlmostEqual(p["speech_s"], 2.4)
        self.assertAlmostEqual(p["span_s"], 3.0)
        self.assertAlmostEqual(p["pause_ratio"], 0.2)
        # 0.5 s counts as a pause; the 0.1 s gap is below MIN_PAUSE_S.
        self.assertEqual(p["pause_count"], 1)
        self.assertAlmostEqual(p["max_pause_s"], 0.5)

    def test_no_speech_is_unmeasured_not_zero(self):
        p = prosody.pause_features([])
        self.assertIsNone(p["pause_ratio"])

    def test_interval_validation(self):
        for bad in ([(1.0, 0.5)], [(0.0, 1.0), (0.5, 2.0)], [(True, 1.0)], [(0.0, 9.0)], [(float("nan"), 1.0)],
                    [(0.0,)]):
            with self.assertRaises(ValueError):
                prosody.validate_intervals(bad, 5.0)


class TestSummary(unittest.TestCase):
    def test_constant_pitch_turn(self):
        f0, rms = _tracks(3.0, f0=200.0)
        s = prosody.summarize_turn(f0, rms, [(0.0, 3.0)], 3.0, word_count=6)
        feats = s["features"]
        self.assertTrue(s["qualifies_for_baseline"])
        self.assertAlmostEqual(feats["f0_median_hz"], 200.0)
        self.assertAlmostEqual(feats["f0_std_st"], 0.0)
        self.assertAlmostEqual(feats["f0_perturbation"], 0.0)
        self.assertAlmostEqual(feats["speech_rate_wps"], 2.0)
        self.assertAlmostEqual(feats["voiced_ratio"], 1.0)
        self.assertEqual(set(feats), set(prosody.FEATURE_NAMES))

    def test_octave_range_is_twelve_semitones(self):
        # Half the frames at 100 Hz, half at 200 Hz: the 10th to 90th percentile spans one octave.
        f0, rms = _tracks(4.0, f0=lambda i: 100.0 if i % 2 else 200.0)
        feats = prosody.summarize_turn(f0, rms, [(0.0, 4.0)], 4.0)["features"]
        self.assertAlmostEqual(feats["f0_range_st"], 12.0, places=3)

    def test_unmeasurable_features_are_none(self):
        f0, rms = _tracks(0.5, f0=None)
        s = prosody.summarize_turn(f0, rms, [(0.0, 0.5)], 0.5)
        self.assertFalse(s["qualifies_for_baseline"])
        self.assertIn("insufficient_speech", s["reasons"])
        self.assertIn("too_few_voiced_frames", s["reasons"])
        self.assertIsNone(s["features"]["f0_median_hz"])
        self.assertIsNone(s["features"]["speech_rate_wps"])

    def test_frames_outside_speech_are_ignored(self):
        # Pitch is 400 Hz outside the speech interval and 150 Hz inside it.
        f0, rms = _tracks(4.0, f0=lambda i: 150.0 if 100 <= i < 300 else 400.0)
        feats = prosody.summarize_turn(f0, rms, [(1.0, 3.0)], 4.0)["features"]
        self.assertAlmostEqual(feats["f0_median_hz"], 150.0)

    def test_track_length_mismatch_refused(self):
        with self.assertRaises(ValueError):
            prosody.summarize_turn([None] * 10, [-20.0] * 9, [], 0.1)


class TestBaselineDeviation(unittest.TestCase):
    def _turn(self, f0_hz, level=-20.0, words=None):
        f0, rms = _tracks(3.0, f0=f0_hz, level=level)
        return prosody.summarize_turn(f0, rms, [(0.0, 3.0)], 3.0, word_count=words)

    def test_no_baseline_until_two_qualifying_turns(self):
        base = prosody.baseline([self._turn(200.0)])
        self.assertEqual(base["status"], prosody.UNAVAILABLE)
        dev = prosody.deviation(self._turn(250.0), base)
        self.assertEqual(dev["status"], prosody.UNAVAILABLE)
        self.assertEqual(dev["reason"], "no_baseline")

    def test_deviation_uses_floor_and_sign(self):
        base = prosody.baseline([self._turn(200.0), self._turn(200.0)])
        self.assertEqual(base["status"], "ready")
        # Identical baseline turns: the spread is the 1-semitone floor.
        up = prosody.deviation(self._turn(200.0 * 2 ** (3 / 12)), base)
        self.assertAlmostEqual(up["deviations"]["f0_median_st"], 3.0, places=3)
        down = prosody.deviation(self._turn(200.0, level=-26.0), base)
        self.assertAlmostEqual(down["deviations"]["rms_mean_db"], -2.0, places=3)

    def test_unqualified_turns_do_not_form_baseline(self):
        short = prosody.summarize_turn(*_tracks(0.5, f0=200.0), [(0.0, 0.5)], 0.5)
        base = prosody.baseline([short, self._turn(200.0)])
        self.assertEqual(base["status"], prosody.UNAVAILABLE)
        self.assertEqual(base["turns_used"], 1)

    def test_deviation_carries_no_judgement(self):
        base = prosody.baseline([self._turn(200.0), self._turn(210.0)])
        dev = prosody.deviation(self._turn(260.0), base)
        for key in ("distress", "emotion", "d4", "band", "svi", "score"):
            self.assertNotIn(key, dev)


class TestQualityGate(unittest.TestCase):
    def test_missing_measurements_are_poor(self):
        self.assertTrue(quality.is_poor({}))
        self.assertTrue(quality.is_poor({"snr_db": None, "speech_ms": 2000, "clipping_ratio": 0.0}))
        self.assertTrue(quality.is_poor({"snr_db": 30.0, "speech_ms": 2000}))

    def test_good_audio_passes(self):
        self.assertFalse(quality.is_poor({"snr_db": 25.0, "speech_ms": 2000, "clipping_ratio": 0.0}))

    def test_each_threshold(self):
        ok = {"snr_db": 25.0, "speech_ms": 2000, "clipping_ratio": 0.0}
        self.assertTrue(quality.is_poor({**ok, "snr_db": 9.9}))
        self.assertTrue(quality.is_poor({**ok, "speech_ms": 799}))
        self.assertTrue(quality.is_poor({**ok, "clipping_ratio": 0.03}))


class TestNoHeavyImports(unittest.TestCase):
    def test_signal_module_imports_without_numpy_at_module_scope(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "acoustics" / "signal.py").read_text(encoding="utf-8")
        for node in ast.parse(src).body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for name in names:
                    self.assertNotIn(name.split(".")[0], {"numpy", "torch", "torchaudio", "scipy", "librosa"})


@unittest.skipUnless(HAS_NUMPY, "numpy is available only in the private model environment (EXT-121)")
class TestSignal(unittest.TestCase):
    SR = 16000

    def setUp(self):
        import numpy as np
        from ml.acoustics import signal
        self.np, self.signal = np, signal

    def _tone(self, hz, seconds=1.0, amp=0.3):
        t = self.np.arange(int(self.SR * seconds)) / self.SR
        return amp * self.np.sin(2 * self.np.pi * hz * t)

    def _median_f0(self, x):
        voiced = [v for v in self.signal.yin_f0(x) if v is not None]
        self.assertGreater(len(voiced), 50)
        return float(self.np.median(voiced))

    def test_pure_tones(self):
        for hz in (90.0, 150.0, 220.0, 400.0):
            self.assertAlmostEqual(self._median_f0(self._tone(hz)), hz, delta=hz * 0.01)

    def test_harmonic_voice_like_signal_tracks_fundamental(self):
        x = self._tone(130.0) + 0.5 * self._tone(260.0) + 0.25 * self._tone(390.0)
        self.assertAlmostEqual(self._median_f0(x), 130.0, delta=2.0)

    def test_silence_and_noise_are_unvoiced(self):
        rng = self.np.random.default_rng(0)
        self.assertTrue(all(v is None for v in self.signal.yin_f0(self.np.zeros(self.SR))))
        noise = 0.1 * rng.standard_normal(self.SR)
        voiced = [v for v in self.signal.yin_f0(noise) if v is not None]
        self.assertLess(len(voiced) / self.signal.frame_count(self.SR), 0.1)

    def test_rms_level(self):
        levels = self.signal.rms_db(self._tone(200.0, amp=0.5))
        # A sine of amplitude A has RMS A / sqrt(2): 0.5 gives about -9.03 dBFS.
        self.assertAlmostEqual(float(self.np.median(levels)), 20 * math.log10(0.5 / math.sqrt(2)), delta=0.1)

    def test_quality_snr_and_clipping(self):
        rng = self.np.random.default_rng(1)
        speech = self._tone(200.0, seconds=1.0, amp=0.3)
        noise = 0.003 * rng.standard_normal(self.SR)
        x = self.np.concatenate([noise, speech + 0.003 * rng.standard_normal(self.SR), noise])
        q = self.signal.quality(x, [(1.0, 2.0)])
        self.assertEqual(q["snr_method"], "non_speech_frames")
        self.assertGreater(q["snr_db"], 30.0)
        self.assertEqual(q["clipping_ratio"], 0.0)
        clipped = self.signal.quality(self.np.clip(5 * speech, -1, 1), [(0.0, 1.0)])
        self.assertGreater(clipped["clipping_ratio"], 0.1)

    def test_measure_feeds_prosody(self):
        x = self.np.concatenate([self.np.zeros(self.SR // 2), self._tone(180.0, seconds=2.0), self.np.zeros(self.SR // 2)])
        m = self.signal.measure(x, [(0.5, 2.5)])
        self.assertEqual(len(m["f0_hz"]), len(m["rms_db"]))
        s = prosody.summarize_turn(m["f0_hz"], m["rms_db"], [(0.5, 2.5)], m["duration_s"])
        self.assertTrue(s["qualifies_for_baseline"])
        self.assertAlmostEqual(s["features"]["f0_median_hz"], 180.0, delta=2.0)

    def test_rejects_bad_input(self):
        for bad in ([], [[0.0, 0.1]], [float("nan")] * 10):
            with self.assertRaises(ValueError):
                self.signal.rms_db(bad)
        with self.assertRaises(ValueError):
            self.signal.measure(self._tone(200.0), [], sample_rate=8000)


if __name__ == "__main__":
    unittest.main()
