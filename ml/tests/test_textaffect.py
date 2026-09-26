"""Transliteration, text-affect corpus rules and text-affect training helpers (plan M12e-f).

Standard library only. Every text below is a short fictional phrase or synthetic data.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from ml.data import affect_corpus as ac
from ml.nlp import transliterate as tr
from ml.textaffect import train as tt

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent


class TestTransliteration(unittest.TestCase):
    CASES = {
        "करना": "karna", "रहता": "rahta", "मेरा": "mera", "आप": "aap", "नहीं": "nahin", "क्या": "kya",
        "मुझे": "mujhe", "डर": "dar", "कमल": "kamal", "शिकायत": "shikaayat", "लड़का": "ladka",
        "पढ़ाई": "padhaai", "ज़मीन": "zamin", "न": "na", "बच्चे": "bachche",
    }

    def test_common_words(self):
        for hi, expected in self.CASES.items():
            self.assertEqual(tr.to_hinglish(hi), expected, hi)

    def test_sentence_and_mixed_text(self):
        self.assertEqual(tr.to_hinglish("मुझे बहुत डर लग रहा है"), "mujhe bahut dar lag raha hai")
        self.assertEqual(tr.to_hinglish("FIR नहीं लिखी।"), "FIR nahin likhi.")

    def test_share_and_maybe(self):
        self.assertIsNone(tr.maybe_hinglish("only english here"))
        self.assertEqual(tr.maybe_hinglish("घर"), "ghar")
        self.assertEqual(tr.devanagari_share(""), 0.0)


class TestAffectLabels(unittest.TestCase):
    def test_single_and_ignored_labels(self):
        self.assertEqual(ac.emoinhindi_turn_label("confident,fear", "1,2"), ("fearful", "single"))
        self.assertEqual(ac.emoinhindi_turn_label("apprehensive", "1"), ("fearful", "single"))
        self.assertEqual(ac.emoinhindi_turn_label("confident,anticipation", "1,1"), (None, "no_mapped_emotion"))

    def test_intensity_breaks_multi_class_and_ties_drop(self):
        self.assertEqual(ac.emoinhindi_turn_label("joy,sad", "1,3"), ("sad", "highest_intensity"))
        self.assertEqual(ac.emoinhindi_turn_label("joy,sad", "2,2"), (None, "tied_classes"))
        self.assertEqual(ac.emoinhindi_turn_label("anger,disgusted", "1,3"), ("angry", "single"))

    def test_goemotions_single_label_only(self):
        names = ["admiration", "anger", "fear", "joy", "nervousness", "neutral", "sadness"]
        self.assertEqual(ac.goemotions_label("1", names), ("angry", "single"))
        self.assertEqual(ac.goemotions_label("4", names), ("fearful", "single"))
        self.assertEqual(ac.goemotions_label("1,3", names), (None, "multi_label"))
        self.assertEqual(ac.goemotions_label("0", names), (None, "unmapped_emotion"))
        self.assertEqual(ac.goemotions_label("99", names), (None, "bad_label_id"))

    def test_only_affect_classes(self):
        self.assertEqual(set(ac.EMOINHINDI_MAP.values()), set(ac.AFFECT))
        self.assertEqual(set(ac.GOEMOTIONS_MAP.values()), set(ac.AFFECT))


class TestAffectRows(unittest.TestCase):
    def _record(self, rid, turns):
        return {"record_id": rid, "turns": [{"turn_index": i, "speaker": "user", "text": t,
                                              "raw_source_label": l, "raw_source_intensity": "1"}
                                             for i, (t, l) in enumerate(turns)]}

    def test_hinglish_copy_shares_label_and_split(self):
        rows, dropped = ac.emoinhindi_rows([self._record("d1", [("मुझे डर लग रहा है", "fear"),
                                                                 ("ठीक है", "confident")])])
        self.assertEqual(dropped, {"no_mapped_emotion": 1})
        hi, hg = rows
        self.assertEqual((hi["language"], hg["language"]), ("hi", "hinglish"))
        self.assertEqual((hi["label"], hi["split"]), (hg["label"], hg["split"]))
        self.assertEqual(hg["text"], "mujhe dar lag raha hai")
        self.assertEqual(hg["derivation"], "transliterated")

    def test_text_split_is_deterministic(self):
        splits = {ac.text_split(f"sentence {i}") for i in range(300)}
        self.assertEqual(splits, {"train", "val", "test"})
        self.assertEqual(ac.text_split("abc"), ac.text_split("abc"))

    def test_duplicates_collapse_with_majority_and_conflicts_drop(self):
        recs = [self._record("d1", [("मुझे डर लग रहा है", "fear")]),
                self._record("d2", [("मुझे डर लग रहा है।", "fear")]),        # same after normalisation
                self._record("d3", [("मुझे डर लग रहा है", "sad")]),
                self._record("d4", [("वो आ गए", "anger"), ("वो आ गए", "joy")])]  # 1 vs 1: conflict
        rows, dropped = ac.emoinhindi_rows(recs)
        hi = [r for r in rows if r["language"] == "hi"]
        self.assertEqual(len(hi), 1)
        self.assertEqual((hi[0]["label"], hi[0]["copies"], hi[0]["label_rule"]), ("affect:fearful", 3, "majority"))
        self.assertEqual(dropped["collapsed_duplicates"], 2)
        self.assertEqual(dropped["conflicting_labels"], 2)

    def test_near_duplicates_share_a_group(self):
        keys = ["they came to my house again last night", "they came to my house again last evening",
                "the water was cut off"]
        groups = ac.near_duplicate_groups(keys, threshold=0.7)
        self.assertEqual(groups[keys[0]], groups[keys[1]])
        self.assertNotEqual(groups[keys[0]], groups[keys[2]])

    def test_no_validation_or_test_text_survives_in_training(self):
        rows = [{"language": "en", "split": "train", "text": "I am scared"},
                {"language": "en", "split": "test", "text": "i am scared!"},
                {"language": "en", "split": "val", "text": "something else"},
                {"language": "hi", "split": "test", "text": "I am scared"}]
        kept, dropped = ac.enforce_split_disjoint(rows)
        self.assertEqual(dropped, 1)
        self.assertEqual([(r["language"], r["split"]) for r in kept], [("en", "train"), ("en", "val"), ("hi", "test")])

    def test_neutral_cap_keeps_test_complete(self):
        rows = ([{"id": f"n{i}", "split": s, "label": "affect:neutral"} for s in ("train", "test") for i in range(10)]
                + [{"id": "a1", "split": "train", "label": "affect:angry"}])
        kept, dropped = ac.cap_neutral(rows, {})
        self.assertEqual(sum(1 for r in kept if r["split"] == "train" and r["label"] == "affect:neutral"), 2)
        self.assertEqual(sum(1 for r in kept if r["split"] == "test"), 10)
        self.assertEqual(dropped, {"neutral_capped_train": 8})

    def test_goemotions_requires_verified_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(ac.verify_goemotions(root, strict=False)["result"], "not_fetched")
            with self.assertRaises(ac.AffectCorpusError):
                ac.goemotions_rows(root)
            base = root / ac.GOEMOTIONS["relative_dir"]
            base.mkdir(parents=True)
            files = {"emotions.txt": "anger\nneutral\n", "train.tsv": "I am so cross\t0\tc1\nfine\t1\tc2\n",
                     "dev.tsv": "", "test.tsv": "all good here\t1\tc3\n"}
            pins = {}
            for name, body in files.items():
                (base / name).write_text(body, encoding="utf-8")
                data = (base / name).read_bytes()
                pins[name] = {"bytes": len(data), "sha256": ac._sha256(data), "expected_bytes": len(data)}
            (base / ac.GOEMOTIONS["pin_file"]).write_text(json.dumps(pins), encoding="utf-8")
            rows, dropped = ac.goemotions_rows(root)
            self.assertEqual([(r["label"], r["split"]) for r in rows],
                             [("affect:angry", "train"), ("affect:neutral", "train"), ("affect:neutral", "test")])
            (base / "test.tsv").write_text("tampered\t1\tc9\n", encoding="utf-8")
            with self.assertRaises(ac.AffectCorpusError):
                ac.goemotions_rows(root)


class TestTrainingHelpers(unittest.TestCase):
    def test_eval_sets(self):
        rows = [{"split": s, "language": l, "speaker": sp} for s, l, sp in
                (("train", "hi", "user"), ("val", "hi", "bot"), ("test", "hi", "user"), ("test", "hinglish", "user"))]
        sets = tt.eval_sets(rows)
        self.assertEqual(sets["test:hi"], [2])
        self.assertEqual(sets["test:hi_user_turns"], [2])
        self.assertEqual(sets["test:hinglish"], [3])
        with self.assertRaises(tt.TextAffectError):
            tt.eval_sets([{"split": "test", "language": "hi", "speaker": "user"}])

    def test_selection_averages_languages(self):
        rows = [{"affect": a} for a in ("sad", "sad", "angry", "angry")]
        sets = {"val:hi": [0, 1], "val:en": [2, 3]}
        preds = {0: "sad", 1: "sad", 2: "sad", 3: "sad"}   # hi perfect (1.0), en all wrong (0.0)
        self.assertEqual(tt.selection_uar(rows, sets, preds), 0.5)

    def test_hinglish_scores_are_labelled_as_augmentation(self):
        self.assertEqual(tt.EVIDENCE["hinglish"], "transliterated_augmentation")

    def test_no_product_code_references_textaffect(self):
        pattern = re.compile(r"ml\.textaffect\b|ml/textaffect\b")
        for base in ("backend", "frontend", "mobile", "docs/contracts"):
            root = REPO / base
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if any(part in ("node_modules", ".venv", "__pycache__", "dist", ".expo") for part in path.parts):
                    continue
                if path.is_file() and path.suffix in (".py", ".ts", ".tsx", ".js", ".json", ".md"):
                    self.assertIsNone(pattern.search(path.read_text(encoding="utf-8", errors="ignore")), str(path))


if __name__ == "__main__":
    unittest.main()
