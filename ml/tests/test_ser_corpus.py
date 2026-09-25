"""SER corpus manifest and preprocessing helpers (plan M12c).

Standard library only. The WAV files here are tiny synthetic files written with ``wave``: no
real audio, and no model.
"""

import copy
import hashlib
import json
import tempfile
import unittest
import wave
from pathlib import Path

from ml.data import governance as gov
from ml.data import ser_corpus as sc
from ml.ser import e2v_features as ef
from ml.ser import preprocess as pp


def _wav(path: Path, seconds: float = 0.1, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))


class TestParsing(unittest.TestCase):
    def test_ravdess_fields(self):
        f = sc.parse_ravdess("03-01-05-02-01-02-12")
        self.assertEqual((f["affect"], f["actor"], f["sex"], f["intensity"]), ("angry", "ravdess:12", "female", "strong"))
        self.assertEqual(f["source_label"], "source:ravdess:05")
        self.assertEqual(sc.parse_ravdess("03-01-01-01-01-01-07")["sex"], "male")

    def test_ravdess_drops_are_named_not_folded(self):
        for code, name in (("02", "calm"), ("07", "disgust"), ("08", "surprised")):
            f = sc.parse_ravdess(f"03-01-{code}-01-01-01-01")
            self.assertIsNone(f["affect"])
            self.assertEqual(f["dropped_as"], name)

    def test_ravdess_non_speech_and_bad_names(self):
        self.assertIsNone(sc.parse_ravdess("01-01-05-01-01-01-01"))   # video
        self.assertIsNone(sc.parse_ravdess("03-02-05-01-01-01-01"))   # song
        for bad in ("03-01-05", "a3-01-05-01-01-01-01", "03-01-05-01-01-01-1"):
            with self.assertRaises(sc.CorpusError):
                sc.parse_ravdess(bad)

    def test_crema_fields(self):
        f = sc.parse_crema("1001_DFA_ANG_XX")
        self.assertEqual((f["affect"], f["actor"], f["intensity"]), ("angry", "crema_d:1001", "unspecified"))
        self.assertIsNone(sc.parse_crema("1001_DFA_DIS_HI")["affect"])
        with self.assertRaises(sc.CorpusError):
            sc.parse_crema("1001-DFA-ANG-XX")

    def test_only_five_affect_classes_exist(self):
        self.assertEqual(set(sc.RAVDESS_EMOTION.values()), set(sc.AFFECT))
        self.assertEqual(set(sc.CREMA_EMOTION.values()), set(sc.AFFECT))


class TestSplits(unittest.TestCase):
    def test_actor_disjoint_sex_stratified_and_deterministic(self):
        actors = {f"crema_d:{1000 + i}": ("male" if i % 2 else "female") for i in range(91)}
        a = sc.assign_splits(actors, 0.15, 0.15)
        self.assertEqual(a, sc.assign_splits(dict(reversed(list(actors.items()))), 0.15, 0.15))
        self.assertEqual(set(a), set(actors))
        for sex in ("male", "female"):
            splits = [a[x] for x, s in actors.items() if s == sex]
            for split in ("train", "val", "test"):
                self.assertGreater(splits.count(split), 0, (sex, split))

    def test_ravdess_shape(self):
        actors = {f"ravdess:{i:02d}": ("male" if i % 2 else "female") for i in range(1, 25)}
        counts = {}
        for split in sc.assign_splits(actors, 4 / 24, 4 / 24).values():
            counts[split] = counts.get(split, 0) + 1
        self.assertEqual(counts, {"train": 16, "val": 4, "test": 4})


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.out = Path(self.tmp.name) / "train" / "ser" / "corpus-v1"
        for actor in range(1, 7):
            for emo in ("01", "02", "05"):
                _wav(self.data / sc.RAVDESS_DIR / f"Actor_{actor:02d}" / f"03-01-{emo}-01-01-01-{actor:02d}.wav")
        demo = ["\"ActorID\",\"Age\",\"Sex\",\"Race\",\"Ethnicity\""]
        for i, actor in enumerate(range(1001, 1007)):
            demo.append(f"{actor},{25 + i},\"{'Male' if i % 2 else 'Female'}\",\"Asian\",\"Not Hispanic\"")
            for emo in ("ANG", "DIS", "NEU"):
                _wav(self.data / sc.CREMA_AUDIO / f"{actor}_DFA_{emo}_XX.wav")
        (self.data / sc.CREMA_DEMOGRAPHICS).write_text("\n".join(demo) + "\n", encoding="utf-8")
        self.reg = copy.deepcopy(gov.load_registry())

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_writes_hashed_manifest_and_drops_named_classes(self):
        m = sc.build(self.data, self.out, registry=self.reg)
        rav, cre = m["datasets"]["ravdess_audio_speech"], m["datasets"]["crema_d"]
        self.assertEqual((rav["clips"], rav["dropped"]), (12, {"calm": 6}))
        self.assertEqual((cre["clips"], cre["dropped"]), (12, {"disgust": 6}))
        body = (self.out / "clips.jsonl").read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), m["clips_sha256"])
        rows = [json.loads(line) for line in body.decode().splitlines()]
        for r in rows:
            self.assertTrue(r["label"].startswith("affect:"))
            self.assertFalse(Path(r["source_rel"]).is_absolute())
            self.assertNotIn(":", r["source_rel"])
        by_actor = {}
        for r in rows:
            by_actor.setdefault(r["actor"], set()).add(r["split"])
        self.assertTrue(all(len(s) == 1 for s in by_actor.values()))
        self.assertTrue(all(r.get("age_band") for r in rows if r["dataset"] == "crema_d"))

    def test_build_refuses_unapproved_datasets(self):
        for rec in self.reg["datasets"]:
            if rec["id"] == "crema_d":
                rec["review_status"] = "metadata_pending"
        with self.assertRaises(gov.GovernanceError):
            sc.build(self.data, self.out, registry=self.reg)

    def test_no_label_leaves_the_affect_namespace(self):
        m = sc.build(self.data, self.out, registry=self.reg)
        labels = {k.split("|")[1] for d in m["datasets"].values() for k in d["clips_by_split_and_label"]}
        self.assertTrue(labels <= {f"affect:{a}" for a in sc.AFFECT})
        keys = json.dumps(sorted(m) + sorted(k for d in m["datasets"].values() for k in d)).lower()
        for word in ("crisis", "danger", "distress", "svi", "d4"):
            self.assertNotIn(word, keys)
        self.assertEqual(m["datasets_root"], str(self.data.resolve()))


class TestPreprocessHelpers(unittest.TestCase):
    def test_trim_window(self):
        self.assertEqual(pp.trim_window([(0.5, 1.0), (1.5, 2.0)], 3.0), (0.4, 2.1))
        self.assertEqual(pp.trim_window([(0.05, 2.98)], 3.0), (0.0, 3.0))
        self.assertIsNone(pp.trim_window([], 3.0))

    def test_shift_intervals(self):
        self.assertEqual(pp.shift_intervals([(0.5, 1.0), (1.5, 2.0)], 0.4, 1.7), [(0.1, 0.6), (1.1, 1.6)])

    def test_whisper_valid_frames(self):
        self.assertEqual(pp.whisper_valid_frames(16000), 50)
        self.assertEqual(pp.whisper_valid_frames(1), 1)
        self.assertEqual(pp.whisper_valid_frames(16000 * 45), 1500)

    def test_output_paths_are_confined(self):
        self.assertEqual(pp.output_rel("crema_d:1001_DFA_ANG_XX"), "audio16k/crema_d/1001_DFA_ANG_XX.wav")
        for bad in ("crema_d:../x", "crema_d:a/b", "crema_d:", "crema_d:.hidden"):
            with self.assertRaises(pp.PreprocessError):
                pp.output_rel(bad)

    def test_source_paths_are_confined(self):
        root = Path(tempfile.gettempdir()).resolve()
        for bad in ("../x.wav", "C:/x.wav", "/etc/x", ""):
            with self.assertRaises(pp.PreprocessError):
                pp.resolve_under(root, bad)

    def test_clip_list_must_match_its_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "clips.jsonl").write_bytes(b'{"clip_id": "x:y"}\n')
            (d / "manifest.json").write_text(json.dumps({"clips_sha256": "0" * 64}))
            with self.assertRaises(pp.PreprocessError):
                pp.read_clips(d)


class TestEmotion2vecScores(unittest.TestCase):
    def test_native_order_and_prefixes(self):
        labels = ["生气/angry", "厌恶/disgusted", "恐惧/fearful", "开心/happy", "中立/neutral", "其他/other",
                  "难过/sad", "吃惊/surprised", "<unk>"]
        scores = [0.1 * i for i in range(9)]
        self.assertEqual(ef.native_scores(list(reversed(labels)), list(reversed(scores))), scores)

    def test_unexpected_labels_refused(self):
        with self.assertRaises(ef.FeatureError):
            ef.native_scores(["angry"] * 9, [0.0] * 9)


if __name__ == "__main__":
    unittest.main()
