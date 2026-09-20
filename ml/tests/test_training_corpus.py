"""EXT-119 training-corpus builder (ml/data/training_corpus.py). Offline and model-free.

Uses tiny fictional records in temporary roots; no dataset, model or network is touched.
"""

import json
import os
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from ml.data import external_corpus as xc, governance as gov, training_corpus as tc

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent


def fake_record(dataset_id, n, text=None, turns=None, labels=(), dup_of=None, key=None, language="en"):
    rid = f"EXT:{dataset_id}:unsplit:{n:016d}"
    body = text if text is not None else " ".join(t["text"] for t in turns)
    return {"record_id": rid, "dataset_id": dataset_id, "text": text, "turns": turns, "language": language,
            "script": "latin", "exact_key": key or xc.exact_key(body), "duplicate_of": dup_of,
            "source_label_category": [xc.fw.source_category(dataset_id, v) for v in labels]}


class TestGovernanceGate(unittest.TestCase):
    def test_ext119_is_recorded_and_approved(self):
        decision = tc.verify_decision()
        self.assertEqual((decision["decision"], decision["status"]), ("EXT-119", "APPROVED"))
        block = tc.decision_block()
        self.assertIn("Invariant 8", block)
        self.assertIn("must not be", block)

    def test_a_missing_or_unapproved_decision_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "d.md"
            p.write_text("```text\nEXT-118\nDecision:        APPROVED\n```\n", encoding="utf-8")
            with self.assertRaises(tc.CorpusRefused):
                tc.verify_decision(p)
            p.write_text("```text\nEXT-119\nDecision:        PROPOSED\n```\n", encoding="utf-8")
            with self.assertRaises(tc.CorpusRefused):
                tc.verify_decision(p)

    def test_the_exact_acknowledgement_is_required(self):
        reg = gov.load_registry()
        for bad in (None, "", "yes", tc.EXT119_ACKNOWLEDGEMENT.lower()):
            with self.assertRaises(tc.CorpusRefused):
                tc.authorise(bad, reg)
        basis = tc.authorise(tc.EXT119_ACKNOWLEDGEMENT, reg)
        self.assertEqual(basis["basis"], "ext119_local_experimental_training")
        self.assertFalse(basis["licence_approved"])
        self.assertFalse(basis["privacy_approved"])
        self.assertEqual(basis["artifact_class"], "quarantined_research_artifact")

    def test_the_acknowledgement_states_the_limits(self):
        ack = tc.EXT119_ACKNOWLEDGEMENT.lower()
        for clause in ("ext-119", "local offline", "licence-pending", "licensing and privacy approval remain "
                       "unresolved", "never redistributed or published", "never official evaluation"):
            self.assertIn(clause, ack)

    def test_a_non_licence_pending_dataset_is_refused(self):
        reg = json.loads(json.dumps(gov.load_registry()))
        next(r for r in reg["datasets"] if r["id"] == "dreaddit")["review_status"] = "rejected"
        with self.assertRaises(tc.CorpusRefused):
            tc.authorise(tc.EXT119_ACKNOWLEDGEMENT, reg)

    def test_the_registry_still_says_licence_pending(self):
        reg = gov.load_registry()
        for d in tc.DATASETS:
            self.assertEqual(gov.get(reg, d)["review_status"], "licence_pending")

    def test_the_task5_override_still_refuses_training(self):
        self.assertIn("training", xc.OVERRIDE_REFUSED_PURPOSES)
        self.assertNotIn(tc.GOVERNANCE_BASIS, xc.OVERRIDE_PURPOSES)

    def test_the_training_root_is_required_and_confined(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(tc.TRAINING_ROOT_ENV, None)
            with self.assertRaises(tc.CorpusRefused):
                tc.training_root()
        with self.assertRaises(tc.CorpusRefused):
            tc.training_root(str(REPO / "ml"))


class TestWindows(unittest.TestCase):
    def test_text_windows_respect_the_limit_and_keep_every_word(self):
        text = " ".join(f"word{i}" for i in range(400))
        windows = tc.text_windows(text, 100)
        self.assertTrue(all(len(w) <= 100 for w in windows))
        self.assertEqual(" ".join(windows).split(), text.split())
        self.assertEqual(tc.text_windows("", 100), [])

    def test_an_unbroken_run_is_split_not_dropped(self):
        windows = tc.text_windows("x" * 250, 100)
        self.assertEqual("".join(windows), "x" * 250)

    def test_dialogue_windows_follow_turn_order_and_skip_blank_turns(self):
        turns = [{"text": f"turn {i} " + "a" * 30} for i in range(10)] + [{"text": "   "}]
        packed = tc.dialogue_windows(turns, 120)
        covered = [i for _, members in packed for i in members]
        self.assertEqual(sorted(set(covered)), list(range(10)))
        self.assertTrue(all(len(t) <= 120 for t, _ in packed))


class TestLabelsAndFamilies(unittest.TestCase):
    def test_only_the_own_namespace_is_accepted(self):
        ok = [xc.fw.source_category("dreaddit", "1")]
        self.assertEqual(tc.namespaced("dreaddit", ok), ok)
        for bad in ([xc.fw.source_category("emoinhindi", "fear")], ["crisis_self_harm"], ["source:dreaddit:"]):
            with self.assertRaises(tc.CorpusRefused, msg=bad):
                tc.namespaced("dreaddit", bad)

    def test_families_join_duplicate_links(self):
        f = tc.Families()
        f.union("b", "a")
        f.union("c", "b")
        f.find("d")
        self.assertEqual({f.find(x) for x in "abc"}, {"a"})
        self.assertEqual(f.find("d"), "d")

    def test_partitions_are_deterministic_and_family_level(self):
        seen = Counter(tc.partition_of(f"family-{i}") for i in range(20000))
        self.assertEqual(tc.partition_of("family-7"), tc.partition_of("family-7"))
        mlm_val = sum(v for (m, _), v in seen.items() if m == "mlm_validation") / 20000
        aux_test = sum(v for (_, a), v in seen.items() if a == "test") / 20000
        self.assertAlmostEqual(mlm_val, 0.005, delta=0.003)
        self.assertAlmostEqual(aux_test, 0.10, delta=0.02)


class TestCremaD(unittest.TestCase):
    def test_lfs_pointers_are_counted_never_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / tc.CREMA_TOP_LEVEL / "AudioWAV"
            base.mkdir(parents=True)
            for i in range(3):
                (base / f"clip{i}.wav").write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:x\n")
            status = tc.crema_status(Path(tmp))
        self.assertEqual((status["media_files"], status["git_lfs_pointer_stubs"], status["real_media_files"]), (3, 3, 0))
        self.assertFalse(status["available"])
        self.assertFalse(status["used"])


class TestBuild(unittest.TestCase):
    """A mocked end-to-end build over tiny fictional records in every dataset slot."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.data_root, self.training = base / "data", base / "training"
        self.data_root.mkdir()
        self.training.mkdir()
        shared = xc.exact_key("the same fictional sentence appears twice")
        self.records = {
            "reddit_suicide_detection": [fake_record("reddit_suicide_detection", 1, "alpha " * 200, labels=["suicide"]),
                                         fake_record("reddit_suicide_detection", 2, "the same fictional sentence "
                                                     "appears twice", labels=["non-suicide"], key=shared)],
            "dreaddit": [fake_record("dreaddit", 1, "a short fictional line", labels=["1"])],
            "emoinhindi": [fake_record("emoinhindi", 1, turns=[{"text": "pehla vakya", "source_label_category":
                                                                [xc.fw.source_category("emoinhindi", "joy")]},
                                                               {"text": "doosra vakya", "source_label_category":
                                                                [xc.fw.source_category("emoinhindi", "sad")]}],
                                       labels=["joy", "sad"], language="hi")],
            "hinglish_hate_speech_local_derivative": [
                fake_record("hinglish_hate_speech_local_derivative", 1, "the same fictional sentence appears twice",
                            labels=["0.0"], key=shared)],
            "hinglish_sentiment_kaggle": [fake_record("hinglish_sentiment_kaggle", 1, "ek fictional line",
                                                      labels=["2"], language="hinglish")],
        }
        self.files = {}
        for d, recs in self.records.items():
            p = base / f"{d}.jsonl"
            p.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
            self.files[d] = p

        def fake_verify(root, dataset_id, registry):
            return self.files[dataset_id], {"records": len(self.records[dataset_id]), "records_sha256": "0" * 64,
                                            "source_sha256": "1" * 64, "source_rows_read": 9, "excluded": {"x": 1},
                                            "unit": "row"}

        def fake_unlabelled(root, dataset_id, registry, manifest, counts):
            counts["blank_unlabelled_row"] += 1
            counts["unlabelled_rows_used"] += 1
            yield {"record_id": f"EXT:{dataset_id}:unlabelled:0001", "dataset_id": dataset_id,
                   "text": "an unlabelled fictional row", "language": "unknown", "script": "latin",
                   "exact_key": xc.exact_key("an unlabelled fictional row"), "duplicate_of": None,
                   "source_label_category": []}

        patches = [mock.patch.object(tc, "verify_normalized", fake_verify),
                   mock.patch.object(tc, "unlabelled_rows", fake_unlabelled),
                   mock.patch.object(tc, "crema_status", lambda root: {"dataset_id": "crema_d", "available": False,
                                                                        "used": False}),
                   mock.patch.object(tc.xc, "record_override_use", lambda root, entry: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.manifest = tc.build(self.data_root, self.training, tc.EXT119_ACKNOWLEDGEMENT)
        out = tc.corpus_dir(self.training)
        self.segments = [json.loads(line) for line in (out / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
        self.keys = (out / tc.EXACT_KEYS_FILE).read_text(encoding="utf-8").split()

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_usable_record_participates_and_blanks_are_not_invented(self):
        used = {s["record_id"] for s in self.segments}
        expected = {r["record_id"] for recs in self.records.values() for r in recs}
        self.assertTrue(expected <= used)
        self.assertIn("EXT:hinglish_hate_speech_local_derivative:unlabelled:0001", used)
        hate = self.manifest["datasets"]["hinglish_hate_speech_local_derivative"]
        self.assertEqual((hate["unlabelled_rows_used"], hate["blank_unlabelled_rows"]), (1, 1))
        self.assertEqual(hate["records"], 2)  # one labelled + one unlabelled; the blank row produced nothing
        for d, s in self.manifest["datasets"].items():
            self.assertEqual(s["records_with_text"], s["records"], d)

    def test_every_record_has_a_coverage_window(self):
        covered = {s["record_id"] for s in self.segments if s["coverage"]}
        self.assertEqual(covered, {s["record_id"] for s in self.segments})
        long = [s for s in self.segments if s["record_id"].startswith("EXT:reddit_suicide_detection") and
                s["windows"] > 1]
        self.assertTrue(long)
        self.assertEqual(sum(s["coverage"] for s in long), 1)  # only its first window in coverage

    def test_duplicates_share_a_family_and_are_down_weighted(self):
        dup = [s for s in self.segments if s["text"] == "the same fictional sentence appears twice"]
        self.assertEqual(len(dup), 2)
        self.assertEqual(len({s["family"] for s in dup}), 1)
        self.assertEqual([s["weight"] for s in dup], [0.5, 0.5])
        by_family = {}
        for s in self.segments:
            by_family.setdefault(s["family"], set()).add((s["mlm_partition"], s["aux_split"]))
        self.assertTrue(all(len(v) == 1 for v in by_family.values()))

    def test_labels_stay_namespaced_and_sentiment_is_opaque(self):
        for s in self.segments:
            for lab in s["source_labels"]:
                self.assertTrue(lab.startswith(f"source:{s['dataset_id']}:"))
            self.assertNotIn("sahay", json.dumps(s["source_labels"]).lower())
            if s["dataset_id"] == "hinglish_sentiment_kaggle":
                self.assertIsNone(s["aux_task"])
                self.assertTrue(s["opaque_labels"])
            self.assertEqual(s["artifact_class"], "quarantined_research_artifact")
        self.assertIsNone(self.manifest["datasets"]["hinglish_sentiment_kaggle"]["aux_task"])
        self.assertIn("none", self.manifest["sahay_mapping"])

    def test_outputs_carry_no_machine_path_and_keys_are_hashes(self):
        text = json.dumps(self.manifest)
        self.assertNotIn(str(self.training), text)
        self.assertNotIn(str(self.data_root), text)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", k) for k in self.keys))
        self.assertIn(xc.exact_key("a short fictional line"), self.keys)

    def test_the_build_is_deterministic(self):
        again = tc.build(self.data_root, self.training, tc.EXT119_ACKNOWLEDGEMENT)
        self.assertEqual(again["segments_sha256"], self.manifest["segments_sha256"])


class TestIsolation(unittest.TestCase):
    def test_only_ml_data_touches_datasets(self):
        for pkg in ("training", "shadow"):
            for path in (ML / pkg).glob("*.py"):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(from|import)\s+(ml\.data|\.\.data)\b", path.name)
                for marker in ("SAHAY_DATASETS_ROOT", "dreaddit", "emoinhindi", "normalized/"):
                    self.assertNotIn(marker, text, (path.name, marker))

    def test_the_builder_imports_no_prediction_or_scoring_module(self):
        text = (ML / "data" / "training_corpus.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(from|import)\s+\S*(assessment|detectors|svi|predict|runtime|training|"
                                    r"shadow)\b", text, re.M))


if __name__ == "__main__":
    unittest.main()
