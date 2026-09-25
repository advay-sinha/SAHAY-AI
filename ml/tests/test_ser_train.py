"""SER metrics, zero-shot mapping and training-data helpers (plan M12d). Standard library only."""

import json
import tempfile
import unittest
from pathlib import Path

from ml.ser import E2V_TO_AFFECT
from ml.ser import data as sd
from ml.ser import metrics as sm
from ml.ser import train as st

A = sd.AFFECT


class TestMetrics(unittest.TestCase):
    def test_uar_is_macro_recall_and_differs_from_accuracy(self):
        gold = ["neutral"] * 8 + ["angry"] * 2
        pred = ["neutral"] * 8 + ["neutral"] * 2
        r = sm.evaluate(gold, pred, A)
        self.assertEqual(r["accuracy"], 0.8)
        self.assertEqual(r["uar"], 0.5)  # neutral 1.0, angry 0.0
        self.assertEqual(r["min_class_recall"], 0.0)
        self.assertEqual(r["per_class"]["angry"]["f1"], 0.0)
        self.assertEqual(sorted(r["classes_excluded_undefined"]), ["fearful", "happy", "sad"])

    def test_abstentions_count_against_recall(self):
        r = sm.evaluate(["sad", "sad"], ["sad", None], A)
        self.assertEqual((r["abstained"], r["per_class"]["sad"]["recall"]), (1, 0.5))

    def test_groups(self):
        g = sm.by_group(["sad", "sad", "angry"], ["sad", "angry", "angry"], ["f", "m", "m"], A)
        self.assertEqual((g["f"]["uar"], g["m"]["n"]), (1.0, 2))

    def test_errors(self):
        with self.assertRaises(ValueError):
            sm.evaluate(["sad"], [], A)
        with self.assertRaises(ValueError):
            sm.evaluate(["calm"], ["sad"], A)


class TestZeroShot(unittest.TestCase):
    ORDER = ("angry", "disgusted", "fearful", "happy", "neutral", "other", "sad", "surprised", "<unk>")

    def test_forced_ignores_unmapped_and_abstaining_abstains(self):
        scores = [0.1, 0.5, 0.05, 0.05, 0.1, 0.0, 0.2, 0.0, 0.0]  # disgusted wins overall
        z = sm.e2v_zero_shot(scores, self.ORDER, E2V_TO_AFFECT, A)
        self.assertEqual(z["forced"], "sad")
        self.assertIsNone(z["abstaining"])

    def test_mapped_winner(self):
        scores = [0.7, 0.1, 0.05, 0.05, 0.1, 0.0, 0.0, 0.0, 0.0]
        self.assertEqual(sm.e2v_zero_shot(scores, self.ORDER, E2V_TO_AFFECT, A)["abstaining"], "angry")


def _row(i, actor, affect, split, f0=150.0, dataset="crema_d"):
    return {"clip_id": f"{dataset}:{i}", "actor": actor, "affect": affect, "split": split, "dataset": dataset,
            "sex": "female", "speech_s": 1.5, "quality": {"snr_db": 30.0},
            "prosody": {"f0_median_hz": f0, "f0_std_st": 1.0, "f0_range_st": 3.0, "f0_perturbation": 0.01,
                        "voiced_ratio": 0.6, "rms_mean_db": -30.0, "rms_std_db": 5.0, "pause_ratio": 0.1,
                        "pause_count": 1, "mean_pause_s": 0.3, "max_pause_s": 0.3}}


class TestData(unittest.TestCase):
    def test_prosody_vector_uses_semitones_and_keeps_missing(self):
        r = _row(1, "a", "sad", "train")
        v = sd.prosody_vector(r)
        self.assertAlmostEqual(v[0], 12.0 * 0.5849625, places=4)  # 150 Hz is 7.02 semitones above 100 Hz
        r["prosody"]["f0_median_hz"] = None
        self.assertIsNone(sd.prosody_vector(r)[0])

    def test_per_speaker_normalisation_removes_speaker_pitch(self):
        rows = [_row(1, "low", "sad", "train", 100.0), _row(2, "low", "sad", "train", 110.0),
                _row(3, "high", "sad", "test", 200.0), _row(4, "high", "sad", "test", 220.0)]
        x = sd.normalise(rows, per_speaker=True)
        self.assertAlmostEqual(x[0][0], x[2][0], places=4)  # same relative position within speaker
        pooled = sd.normalise(rows, per_speaker=False, train_ids={"crema_d:1", "crema_d:2"})
        self.assertNotAlmostEqual(pooled[0][0], pooled[2][0], places=2)
        self.assertEqual(len(x[0]), 2 * len(sd.PROSODY_FEATURES))

    def test_class_weights(self):
        w = sd.class_weights(["neutral", "sad", "sad", "sad"])
        self.assertGreater(w[A.index("neutral")], w[A.index("sad")])
        self.assertEqual(w[A.index("angry")], 0.0)
        with self.assertRaises(sd.DataError):
            sd.class_weights([])

    def test_load_rows_counts_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            clips = [{"clip_id": "crema_d:1", "dataset": "crema_d", "label": "affect:sad", "split": "train",
                      "actor": "a", "sex": "female"},
                     {"clip_id": "crema_d:2", "dataset": "crema_d", "label": "affect:angry", "split": "val",
                      "actor": "b", "sex": "male"}]
            feats = [{"clip_id": "crema_d:1", "status": "ok", "prosody": {}, "quality": {}, "speech_s": 1.0,
                      "audio_rel": "audio16k/crema_d/1.wav"},
                     {"clip_id": "crema_d:2", "status": "no_speech"}]
            (d / "clips.jsonl").write_text("\n".join(json.dumps(c) for c in clips), encoding="utf-8")
            (d / "features.jsonl").write_text("\n".join(json.dumps(f) for f in feats), encoding="utf-8")
            rows, report = sd.load_rows(d)
            self.assertEqual([r["affect"] for r in rows], ["sad"])
            self.assertEqual(report["excluded"], {"crema_d|affect:angry|no_speech": 1})


class TestEvalSets(unittest.TestCase):
    def test_cross_corpus_only_for_the_crema_regime(self):
        rows = [_row(1, "a", "sad", "train"), _row(2, "b", "sad", "val"), _row(3, "c", "sad", "test"),
                _row(4, "r", "sad", "test", dataset="ravdess_audio_speech")]
        both = st.eval_sets(rows, "both")
        self.assertIn("test:ravdess_audio_speech", both)
        self.assertNotIn("cross:ravdess_audio_speech", both)
        crema = st.eval_sets(rows, "crema")
        self.assertEqual(crema["cross:ravdess_audio_speech"], [3])
        self.assertNotIn("test:ravdess_audio_speech", crema)

    def test_empty_training_split_refused(self):
        with self.assertRaises(st.TrainError):
            st.eval_sets([_row(1, "a", "sad", "test")], "both")


if __name__ == "__main__":
    unittest.main()
