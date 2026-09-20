"""Task 7B: targeted fictional corpus, pre-training freeze, predeclared experiments and promotion gates.

Offline, model-free and GPU-free. Corpora are built in temporary roots; models are tiny fakes.
"""

import hashlib
import inspect
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ml.eval.blind import leakage as lk, normalize as nz
from ml.eval.schema import DETECTOR_CATEGORIES
from ml.guardrails import crisis_check
from ml.runtime.offline import network_blocked
from ml.shadow import classifier as sc, demo, model as sm
from ml.training import fictional, hardening as hx, metrics, paths, stage_c7b as s7

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent


def _digest(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = hx.generate()


class TestGeneration(Corpus):
    def test_generation_is_deterministic(self):
        self.assertEqual(_digest(hx.generate()), _digest(self.records))

    def test_size_languages_and_allocation(self):
        n = len(self.records)
        self.assertTrue(9000 <= n <= 15000, n)
        for lang in hx.LANGUAGES:
            share = sum(r["language"] == lang for r in self.records) / n
            self.assertTrue(0.22 <= share <= 0.45, (lang, share))
        crisis = sum(hx.area_of(r) == "crisis" for r in self.records) / n
        self.assertGreaterEqual(crisis, 0.30)

    def test_labels_are_the_frozen_schema_order(self):
        self.assertEqual(hx.LABELS, tuple(DETECTOR_CATEGORIES))
        for r in self.records[:100]:
            self.assertEqual(list(r["labels"]), list(DETECTOR_CATEGORIES))
            self.assertEqual(r["positive_labels"], [n for n in DETECTOR_CATEGORIES if r["labels"][n]])

    def test_coverage_every_priority_label_in_every_language_and_split(self):
        cov = hx.coverage(self.records)
        self.assertEqual(cov["problems"], [])
        for split in hx.SPLITS:
            for n in ("crisis_self_harm", "legal_urgency", "communication_safety_coercion"):
                for lang in hx.LANGUAGES:
                    self.assertGreater(cov["splits"][split][f"label_lang:{n}:{lang}"], 10, (split, n, lang))

    def test_required_metadata_on_every_record(self):
        for r in self.records[::97]:
            for key in ("family", "language", "script", "positive_labels", "negative_labels", "challenge_slices",
                        "contrast_group", "generator_version", "seed", "lineage", "content_hash", "review_status"):
                self.assertIn(key, r)
            self.assertEqual(r["review_status"], "unreviewed")
            self.assertEqual({t["speaker"] for t in r["turns"]}, {"victim"})  # no assistant responses

    def test_multi_label_records_carry_a_reason(self):
        multi = [r for r in self.records if sum(r["labels"].values()) > 1]
        self.assertTrue(multi)
        for r in multi:
            if r["family"].startswith("combo:"):
                self.assertTrue(r["multi_label_reason"].startswith("turn composition"))


class TestContrastFamilies(Corpus):
    def test_near_miss_members_negate_the_core_risk_label(self):
        for r in self.records:
            frame = r["lineage"].get("frame", "")
            if frame.startswith(("quoted", "reported", "past", "negated")):
                self.assertFalse(any(r["labels"].values()), r["id"])
                self.assertTrue(r["negative_labels"], r["id"])
                self.assertIn("contrast", r["challenge_slices"])

    def test_direct_members_keep_the_core_labels(self):
        cores = {c[0]: c for c in hx.CORES}
        for r in self.records:
            if r["lineage"].get("frame", "").startswith("direct") and cores[r["family"]][2]:
                self.assertEqual(r["labels"], hx.labels_of(cores[r["family"]][2]), r["id"])

    def test_every_contrast_type_is_present(self):
        slices = {s for r in self.records for s in r["challenge_slices"]}
        for s in ("quotation", "attribution", "historical", "negation", "figurative", "ordinary_disagreement",
                  "general_legal", "discouraged_help", "conditional", "disappear", "indirect",
                  "romanized_spelling_variant", "hindi_spelling_variant", "unicode_variant", "code_switching",
                  "multi_turn_combo"):
            self.assertIn(s, slices)

    def test_families_never_cross_splits(self):
        owner = {}
        for r in self.records:
            self.assertEqual(owner.setdefault(r["family"], r["split"]), r["split"], r["family"])
            for core in (r["lineage"].get("cores") or [r["lineage"].get("core")]):
                self.assertEqual(hx.assign_splits()[core], r["split"])

    def test_bank_carries_no_identifier_identity_or_procedure(self):
        banned = re.compile(r"\d{3,}|@|https?://|\bcaste\b|\breligio|\bdalit\b|\bmuslim\b|\bhindu\b|जाति|धर्म|"
                            r"\b(rope|poison|pills?|overdose|hang|knife|blade|gun|kerosene|acid|jump off)\b", re.I)
        for core in hx.CORES:
            for text in core[4].values():
                self.assertIsNone(banned.search(text), core[0])


class TestContamination(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = lk.build_index(files=hx.ALL_EXPOSED_FILES)

    def _record(self, text, family="fx", split="train"):
        return hx._record(f"T-{family}-{hashlib.md5(text.encode()).hexdigest()[:6]}", family, family, split, "en",
                          [text], hx.labels_of(""), [], (), {"core": family})

    def test_exposed_fixture_copies_are_blocked_by_family(self):
        dev = json.loads((lk.CORPUS_DIR / "dev.json").read_text(encoding="utf-8"))["samples"]
        victim = next(t["text"] for s in dev for t in s["turns"] if t["speaker"] == "victim" and len(t["text"]) > 40)
        recs = [self._record(victim, "bad"), self._record("A fresh fictional line about the ration queue.", "bad"),
                self._record("An unrelated fictional line about the weekly bus timetable.", "ok")]
        result = hx.contamination(recs, [], None, self.index)
        self.assertIn("bad", result["blocked_families"])
        self.assertEqual([r["family"] for r in result["kept"]], ["ok"])
        self.assertNotIn(victim, json.dumps({k: v for k, v in result.items() if k != "kept"}))

    def test_task7_external_and_cross_split_duplicates_are_blocked(self):
        t7 = [{"turns": [{"speaker": "victim", "text": "A task seven fictional sentence about a form."}]}]
        ext = {hashlib.sha256(nz.compare("An external looking line for the guard test.").encode()).hexdigest()}
        recs = [self._record("A task seven fictional sentence about a form.", "t7"),
                self._record("An external looking line for the guard test.", "ext"),
                self._record("The same sentence twice across splits.", "one", "train"),
                self._record("The same sentence twice across splits.", "two", "validation")]
        result = hx.contamination(recs, t7, ext, self.index)
        self.assertEqual(set(result["blocked_families"]), {"t7", "ext", "two"})
        self.assertIn("unavailable", result["blind_corpus"])

    def test_the_committed_bank_does_not_reproduce_exposed_fixtures_or_task7(self):
        t7_turns = {nz.compare(t["text"]) for r in fictional.generate() for t in r["turns"] if t["speaker"] == "victim"}
        for core in hx.CORES:
            for text in core[4].values():
                c = nz.compare(text)
                self.assertNotIn(c, self.index["scenarios"], core[0])
                self.assertNotIn(c, self.index["turns"], core[0])
                self.assertNotIn(c, t7_turns, core[0])


class BuiltRoot(unittest.TestCase):
    """A small build (clean variants only) in a temporary root, with the slow screen stubbed."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name).resolve()
        t7 = cls.root / "corpora" / "fictional-sahay-v1"
        t7.mkdir(parents=True)
        (t7 / "records.jsonl").write_text("", encoding="utf-8")
        full = hx.generate()
        small = [r for r in full if r["lineage"].get("variant", 0) in (0, 1)]
        with mock.patch.object(hx, "generate", lambda: small), \
                mock.patch.object(hx, "contamination", lambda recs, t7_, keys, index=None: {
                    "kept": list(recs), "blocked_families": {}, "blocked_records": 0, "warnings": {},
                    "blind_corpus": "unavailable"}), network_blocked() as net:
            cls.report = hx.build(cls.root)
        cls.attempts = net["attempts"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestFreeze(BuiltRoot):
    def test_the_freeze_verifies_and_used_no_network(self):
        self.assertEqual(self.attempts, 0)
        self.assertEqual(self.report["freeze"]["state"], "frozen_before_training")
        self.assertTrue(hx.verify_freeze(self.root)["ok"])

    def test_a_frozen_version_cannot_be_regenerated(self):
        with self.assertRaises(RuntimeError):
            hx.build(self.root)

    def test_tampering_with_the_holdout_breaks_verification(self):
        path = paths.confined(self.root, *hx.CORPUS_DIR, "synthetic_hardening_holdout.jsonl")
        original = path.read_bytes()
        try:
            path.write_bytes(original.replace(b'"crisis_self_harm": true', b'"crisis_self_harm": false', 1))
            self.assertFalse(hx.verify_freeze(self.root)["ok"])
        finally:
            path.write_bytes(original)
        self.assertTrue(hx.verify_freeze(self.root)["ok"])

    def test_the_holdout_note_states_its_limits(self):
        self.assertIn("not independent, official, blind, human-authored or clinically validated", hx.HOLDOUT_NOTE)


class TestReviewPacket(BuiltRoot):
    def test_packet_covers_families_labels_and_languages(self):
        packet = [json.loads(line) for line in paths.confined(self.root, *hx.REVIEW_DIR, "review-packet.jsonl")
                  .read_text(encoding="utf-8").splitlines()]
        built = [r for s in hx.SPLITS for r in hx.load_split(self.root, s)]
        self.assertEqual({r["template_family"] for r in packet}, {r["family"] for r in built})
        self.assertEqual({r["language"] for r in packet}, set(hx.LANGUAGES))
        for n in DETECTOR_CATEGORIES:
            if any(n in r["positive_labels"] for r in built):
                self.assertTrue(any(n in r["labels"] for r in packet), n)

    def test_no_review_is_invented(self):
        packet = [json.loads(line) for line in paths.confined(self.root, *hx.REVIEW_DIR, "review-packet.jsonl")
                  .read_text(encoding="utf-8").splitlines()]
        for row in packet:
            for f in hx.REVIEW_FIELDS:
                self.assertIsNone(row[f], f)
            self.assertEqual(row["review_state"], "pending_human_review")
        summary = json.loads(paths.confined(self.root, *hx.REVIEW_DIR, "review-summary.json").read_text("utf-8"))
        self.assertEqual(summary["completed_reviews"], 0)


class TestPlanAndSelection(BuiltRoot):
    def test_predeclared_configurations_and_fixed_threshold(self):
        self.assertEqual(set(s7.CONFIGS), {"A", "B", "C"})
        self.assertEqual(s7.CONFIGS["B"]["pos_weight_bounds"], [1.0, 8.0])
        self.assertEqual(s7.CONFIGS["C"]["gamma"], 2.0)
        self.assertEqual(s7.HYPER["threshold"], 0.5)
        self.assertEqual(s7.SCHEDULE["phase1"]["configs"], ["A", "B", "C"])

    def test_the_plan_cannot_change_after_recording(self):
        s7.write_plan(self.root)
        self.assertEqual(s7.write_plan(self.root)["plan_sha256"], s7.plan_hash(s7.plan()))
        with mock.patch.dict(s7.GATES, {"holdout_crisis_recall_min": 0.5}):
            with self.assertRaises(RuntimeError):
                s7.check_plan(self.root)
            with self.assertRaises(RuntimeError):
                s7.write_plan(self.root)

    def test_gate_values_are_the_declared_ones(self):
        self.assertEqual(s7.GATES, {"holdout_crisis_recall_min": 0.80, "per_language_crisis_recall_min": 0.70,
                                    "legal_urgency_recall_min": 0.70, "coercion_recall_min": 0.70, "macro_f1_min": 0.70,
                                    "no_alert_specificity_min": 0.90, "repeat_agreement": 1.0})

    def test_selection_uses_validation_only(self):
        def run(config, seed, crisis, weak, f1, spec, loss, holdout_crisis):
            return {"config": config, "seed": seed, "selected_epoch": 4, "validation_loss": loss,
                    "checkpoint": f"task7b/checkpoints/{config}-seed-{seed}", "phase": 1,
                    "validation": {"crisis_recall": crisis, "min_weak_recall": weak, "macro": {"f1": f1},
                                   "no_alert_specificity": spec},
                    "synthetic_hardening_holdout": {"crisis_recall": holdout_crisis}}
        runs = [run("A", 13, 0.9, 0.6, 0.7, 0.9, 0.2, 0.1), run("B", 13, 0.9, 0.7, 0.6, 0.8, 0.3, 0.99),
                run("C", 13, 0.8, 0.9, 0.9, 0.99, 0.1, 0.99)]
        paths.write_json(paths.confined(self.root, "task7b", "reports", "runs.json"), {"runs": runs})
        selection = s7.select(self.root)
        self.assertEqual(selection["selected"]["config"], "B")
        self.assertEqual(s7.phase1_winner(runs), "B")

    def test_training_and_selection_code_never_touch_the_holdout(self):
        for fn in (s7.run_phase, s7.train_run, s7.select, s7.phase1_winner, s7.selection_key):
            self.assertNotIn("holdout", inspect.getsource(fn).replace("hardening_holdout_note", ""), fn.__name__)
        self.assertIn("synthetic_hardening_holdout", inspect.getsource(s7.evaluate))

    def test_the_holdout_is_evaluated_once(self):
        out = paths.confined(self.root, "task7b", "reports", "holdout-evaluation.json")
        paths.write_json(out, {"evaluated_once": True})
        try:
            with self.assertRaises(RuntimeError):
                s7.evaluate(self.root)
        finally:
            out.unlink()


FULL_COVERAGE = {"full_label_coverage": True, "promotion_metrics_fully_evaluable": True,
                 "labels_missing_positive_support": [], "labels_missing_negative_support": []}


class TestGates(unittest.TestCase):
    def holdout(self, crisis=0.9, lang=0.8, legal=0.8, coercion=0.8, f1=0.8, spec=0.95, coverage=FULL_COVERAGE):
        return {"crisis_recall": crisis, "crisis_recall_by_language": {"en": lang, "hi": lang, "hinglish": lang},
                "per_label": {"legal_urgency": {"recall": legal}, "communication_safety_coercion": {"recall": coercion}},
                "macro": {"f1": f1, "f1_labels_included": list(DETECTOR_CATEGORIES), "f1_defined_labels": 8,
                          "f1_labels_excluded_undefined": []},
                "no_alert_specificity": spec, "coverage": coverage}

    def test_all_gates_pass_gives_only_candidate_for_human_review(self):
        gates = s7.gate_results(self.holdout(), 1.0, True, True, True)
        self.assertEqual(s7.status_from(gates), "candidate_for_human_review")

    def test_incomplete_label_coverage_prevents_candidate(self):
        partial = {"full_label_coverage": False, "promotion_metrics_fully_evaluable": False,
                   "labels_missing_positive_support": ["immediate_danger"], "labels_missing_negative_support": []}
        for cov in (partial, None, {}):
            gates = s7.gate_results(self.holdout(coverage=cov), 1.0, True, True, True)
            self.assertFalse(gates["full_label_coverage"]["passed"])
            self.assertEqual(s7.status_from(gates), "rejected_for_product_integration")
        legacy = s7.gate_results(self.holdout(), 1.0, True, True, True)
        legacy.pop("full_label_coverage")
        self.assertEqual(s7.status_from(legacy), "rejected_for_product_integration")

    def test_numeric_thresholds_are_unchanged_by_the_correction(self):
        gates = s7.gate_results(self.holdout(), 1.0, True, True, True)
        self.assertEqual(gates["macro_f1"]["required"], 0.70)
        self.assertEqual(gates["holdout_crisis_recall"]["required"], 0.80)
        self.assertEqual(gates["no_alert_specificity"]["required"], 0.90)
        self.assertEqual(gates["macro_f1"]["labels_included"], list(DETECTOR_CATEGORIES))

    def test_any_failure_keeps_rejected(self):
        for kw in ({"crisis": 0.79}, {"lang": 0.69}, {"legal": 0.5}, {"coercion": 0.69}, {"f1": 0.69}, {"spec": 0.89}):
            gates = s7.gate_results(self.holdout(**kw), 1.0, True, True, True)
            self.assertEqual(s7.status_from(gates), "rejected_for_product_integration", kw)
        for args in ((0.99, True, True, True), (1.0, False, True, True), (1.0, True, False, True), (1.0, True, True, False)):
            self.assertEqual(s7.status_from(s7.gate_results(self.holdout(), *args)), "rejected_for_product_integration")
        missing = self.holdout()
        missing["crisis_recall_by_language"]["hi"] = None
        self.assertEqual(s7.status_from(s7.gate_results(missing, 1.0, True, True, True)),
                         "rejected_for_product_integration")


class TestMetricValidity(unittest.TestCase):
    """Undefined metrics are null with a reason; macro averages state their label sets."""

    LABELS = ("a", "b", "c")

    def test_missing_positive_support_gives_null_recall_and_f1(self):
        m = metrics.label_metrics(tp=0, fp=3, fn=0, tn=10)
        self.assertIsNone(m["recall"])
        self.assertIsNone(m["f1"])
        self.assertEqual(m["precision"], 0.0)  # defined: TP+FP = 3
        self.assertEqual(m["denominators"], {"precision": 3, "recall": 0, "specificity": 13})
        self.assertIn("no positive support", m["undefined"]["recall"])
        self.assertIn("no positive support", m["undefined"]["f1"])
        self.assertFalse(m["f1_defined"])

    def test_missing_negative_support_gives_null_specificity(self):
        m = metrics.label_metrics(tp=5, fp=0, fn=1, tn=0)
        self.assertIsNone(m["specificity"])
        self.assertIn("no negative support", m["undefined"]["specificity"])
        self.assertEqual(m["recall"], round(5 / 6, 4))

    def test_no_predicted_positives_keeps_precision_null_but_f1_zero_when_positives_exist(self):
        m = metrics.label_metrics(tp=0, fp=0, fn=4, tn=6)
        self.assertIsNone(m["precision"])
        self.assertEqual(m["recall"], 0.0)
        self.assertEqual(m["f1"], 0.0)  # positives exist and none was found: F1 is exactly 0
        self.assertIn("no predicted positives", m["undefined"]["precision"])

    def test_undefined_metrics_never_become_zero_in_a_macro(self):
        gold = [{"a": True, "b": False, "c": False}, {"a": False, "b": False, "c": False}]
        pred = [{"a": True, "b": False, "c": True}, {"a": False, "b": False, "c": False}]
        s = metrics.summary(gold, pred, self.LABELS)
        self.assertEqual(s["macro"]["f1"], 1.0)  # only "a" is defined; b and c are excluded, not zero-filled
        self.assertEqual(s["macro"]["f1_labels_included"], ["a"])
        self.assertEqual(s["macro"]["f1_defined_labels"], 1)
        self.assertEqual(s["macro"]["f1_labels_excluded_undefined"], ["b", "c"])
        self.assertIsNone(s["per_label"]["b"]["f1"])
        self.assertEqual(s["macro_detail"]["precision"]["labels_excluded_undefined"], ["b"])

    def test_coverage_fields_in_frozen_order(self):
        gold = [{"a": True, "b": False, "c": True}, {"a": True, "b": False, "c": False}]
        s = metrics.summary(gold, gold, self.LABELS)
        cov = s["coverage"]
        self.assertEqual(cov["labels"], list(self.LABELS))
        self.assertEqual(cov["support"]["a"], {"positive": 2, "negative": 0})
        self.assertEqual(cov["labels_missing_positive_support"], ["b"])
        self.assertEqual(cov["labels_missing_negative_support"], ["a"])
        self.assertFalse(cov["full_label_coverage"])
        self.assertFalse(cov["promotion_metrics_fully_evaluable"])

    @staticmethod
    def fixture_rows():
        """Fictional, model-free holdout rows: every label positive once per language (24 records)
        plus 12 all-negative records (4 per language). Text is never needed by the evaluator."""
        labels = tuple(DETECTOR_CATEGORIES)
        rows = []
        for lang in hx.LANGUAGES:
            for name in labels:
                gold = {n: n == name for n in labels}
                rows.append({"id": f"FX-{lang}-{name}", "language": lang, "gold": gold,
                             "labels": [float(gold[n]) for n in labels], "group": f"g-{name}", "negatives": [],
                             "slices": []})
            for i in range(4):
                gold = {n: False for n in labels}
                rows.append({"id": f"FX-{lang}-none-{i}", "language": lang, "gold": gold,
                             "labels": [0.0] * len(labels), "group": f"g-none-{lang}-{i}", "negatives": [],
                             "slices": []})
        return labels, rows

    def test_all_eight_labels_supported_fixture_returns_candidate_for_human_review(self):
        labels, rows = self.fixture_rows()
        coercion = labels.index("communication_safety_coercion")
        probs = []
        for r in rows:  # perfect firings except one false coercion firing on one all-negative record
            p = [0.99 if v else 0.01 for v in r["labels"]]
            if r["id"] == "FX-en-none-0":
                p[coercion] = 0.99
            probs.append(p)
        holdout = s7.evaluate_rows(rows, probs)
        cov = holdout["coverage"]
        self.assertTrue(cov["full_label_coverage"])
        self.assertTrue(cov["promotion_metrics_fully_evaluable"])
        self.assertEqual({n: cov["support"][n] for n in labels},
                         {n: {"positive": 3, "negative": 33} for n in labels})
        gates = s7.gate_results(holdout, 1.0, True, True, True)
        values = {k: g["value"] for k, g in gates.items()}
        self.assertEqual(values["holdout_crisis_recall"], 1.0)
        self.assertEqual((values["crisis_recall_en"], values["crisis_recall_hi"], values["crisis_recall_hinglish"]),
                         (1.0, 1.0, 1.0))
        self.assertEqual(values["legal_urgency_recall"], 1.0)
        self.assertEqual(values["coercion_recall"], 1.0)
        self.assertEqual(values["macro_f1"], 0.9821)  # (7 x 1.0 + coercion 0.8571) / 8 defined labels
        self.assertEqual(gates["macro_f1"]["defined_labels"], 8)
        self.assertEqual(values["no_alert_specificity"], 0.9167)  # 11 of 12 all-negative records silent
        self.assertEqual(values["repeat_agreement"], 1.0)
        self.assertTrue(all(g["passed"] for g in gates.values()), {k: g["passed"] for k, g in gates.items()})
        status = s7.status_from(gates)
        self.assertEqual(status, "candidate_for_human_review")
        record = s7.status_record(status, gates, "fixture")
        for flag in ("backend_integration_allowed", "frontend_integration_allowed", "mobile_integration_allowed",
                     "victim_facing_allowed"):
            self.assertIs(record[flag], False, flag)
        self.assertTrue(record["shadow_local_demo_only"])
        self.assertEqual(demo.product_line({"deployment_status": status, "promotion_gates_passed": True}),
                         "Candidate for human review only; not approved for product integration")

    def test_missing_positive_support_blocks_promotion(self):
        labels, rows = self.fixture_rows()
        rows = [r for r in rows if not r["gold"]["medical_urgency"]]
        probs = [[0.99 if v else 0.01 for v in r["labels"]] for r in rows]
        holdout = s7.evaluate_rows(rows, probs)
        self.assertEqual(holdout["coverage"]["labels_missing_positive_support"], ["medical_urgency"])
        self.assertIsNone(holdout["per_label"]["medical_urgency"]["recall"])
        self.assertIn("medical_urgency", holdout["macro"]["f1_labels_excluded_undefined"])
        gates = s7.gate_results(holdout, 1.0, True, True, True)
        self.assertFalse(gates["full_label_coverage"]["passed"])
        self.assertEqual(s7.status_from(gates), "rejected_for_product_integration")

    def test_missing_negative_support_blocks_promotion(self):
        labels, rows = self.fixture_rows()
        for r in rows:  # make every record positive for continuing_threat: no negative support remains
            r["gold"]["continuing_threat"] = True
            r["labels"][labels.index("continuing_threat")] = 1.0
        probs = [[0.99 if v else 0.01 for v in r["labels"]] for r in rows]
        holdout = s7.evaluate_rows(rows, probs)
        self.assertEqual(holdout["coverage"]["labels_missing_negative_support"], ["continuing_threat"])
        self.assertIsNone(holdout["per_label"]["continuing_threat"]["specificity"])
        gates = s7.gate_results(holdout, 1.0, True, True, True)
        self.assertFalse(gates["full_label_coverage"]["passed"])
        self.assertEqual(s7.status_from(gates), "rejected_for_product_integration")

    def test_undefined_metrics_cannot_pass_a_gate(self):
        labels, rows = self.fixture_rows()
        probs = [[0.99 if v else 0.01 for v in r["labels"]] for r in rows]
        holdout = s7.evaluate_rows(rows, probs)
        for key, path in (("macro_f1", ("macro", "f1")), ("holdout_crisis_recall", ("crisis_recall",)),
                          ("no_alert_specificity", ("no_alert_specificity",))):
            broken = json.loads(json.dumps(holdout))
            target = broken
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = None
            gates = s7.gate_results(broken, 1.0, True, True, True)
            self.assertFalse(gates[key]["passed"], key)
            self.assertEqual(s7.status_from(gates), "rejected_for_product_integration", key)

    #: Aggregate per-label counts [TP, FP, FN, TN] of the once-only Task 7B holdout evaluation (no text).
    TASK7B_COUNTS = {"crisis_self_harm": [298, 66, 0, 826], "immediate_danger": [0, 0, 0, 1190],
                     "continuing_threat": [14, 51, 118, 1007], "medical_urgency": [0, 0, 0, 1190],
                     "isolation_boycott_displacement": [0, 0, 0, 1190], "legal_urgency": [152, 0, 57, 981],
                     "communication_safety_coercion": [216, 162, 0, 812], "explicit_human_request": [80, 12, 38, 1060]}

    def test_task7b_real_counts_remain_rejected(self):
        labels = tuple(DETECTOR_CATEGORIES)
        rows = {n: metrics.label_metrics(*self.TASK7B_COUNTS[n]) for n in labels}
        holdout = metrics.summary_from_rows(rows, labels, 1190)
        holdout.update(crisis_recall=1.0, crisis_recall_by_language={"en": 1.0, "hi": 1.0, "hinglish": 1.0},
                       no_alert_specificity=0.9248)
        gates = s7.gate_results(holdout, 1.0, True, True, True)
        self.assertEqual(holdout["macro"]["f1"], 0.6747)
        self.assertEqual(holdout["macro"]["f1_defined_labels"], 5)
        self.assertEqual(holdout["coverage"]["labels_missing_positive_support"],
                         ["immediate_danger", "medical_urgency", "isolation_boycott_displacement"])
        self.assertFalse(holdout["coverage"]["full_label_coverage"])
        self.assertFalse(holdout["coverage"]["promotion_metrics_fully_evaluable"])
        self.assertFalse(gates["macro_f1"]["passed"])
        self.assertFalse(gates["full_label_coverage"]["passed"])
        self.assertEqual(rows["continuing_threat"]["recall"], 0.1061)
        self.assertEqual(s7.status_from(gates), "rejected_for_product_integration")
        self.assertEqual(s7.TASK7B_CHECKPOINT_STATUS, "rejected_for_product_integration")

    def test_the_task7b_holdout_generator_and_hashes_are_unchanged(self):
        self.assertEqual(hx.VERSION, "7b-v1")
        records = hx.generate()
        frozen = hx.freeze_payload(records, hx.coverage(records))
        self.assertEqual(frozen["bank_sha256"], "43ac65f98e9f3b29b980ca5b19a546c635aba90cdfc9b0b11912c44c5ff8bb43")
        self.assertEqual(frozen["split_record_sha256"]["synthetic_hardening_holdout"],
                         "069ff9906f223fc56356b709fb4a68195b0d99123a2c0c4004cd4f0f52a2c7e3")
        self.assertEqual(frozen["split_family_sha256"]["synthetic_hardening_holdout"],
                         "32a47c87eb942df38268cd6c4c1a3e366f8d9215f7cb225791b7fc3eeaa69eaa")
        self.assertEqual(frozen["records"], {"synthetic_hardening_holdout": 1190, "train": 7492, "validation": 1242})

    def test_the_correction_statement_and_model_card(self):
        self.assertEqual(s7.PROMOTION_STATEMENT,
                         "The checkpoint remains rejected for product integration. It missed the macro-F1 gate, and "
                         "full eight-label promotion evaluation was not possible because three labels had no positive "
                         "holdout support.")
        card = (ML / "shadow" / "MODEL_CARD.md").read_text(encoding="utf-8")
        self.assertNotIn("Every other gate passed", card)
        self.assertIn("full eight-label promotion evaluation was not possible", card)
        self.assertIn("`promotion_metrics_fully_evaluable` | `false`", card)
        readme = (ML / "training" / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("passed every", readme.lower())

    def test_the_task7b_correction_pins_only_its_own_permanent_status(self):
        src = inspect.getsource(s7.correct_holdout_report)
        self.assertIn("TASK7B_CHECKPOINT_STATUS", src)
        self.assertNotIn("may never promote", src)  # the reusable evaluator can still reach a candidate
        self.assertNotIn("predict", src.replace("re-predicted", ""))
        self.assertIn("return CANDIDATE", inspect.getsource(s7.status_from))


class TestStatusAndIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        ck = self.root / "task7b" / "checkpoints" / "A-seed-13"
        (ck / sm.ENCODER_DIR).mkdir(parents=True)
        (ck / sm.HEAD_FILE).write_bytes(b"fake-head")
        (ck / sm.CONFIG_FILE).write_text("{}", encoding="utf-8")
        (self.root / "task7b" / "checkpoints" / "SELECTED.json").write_text(
            json.dumps({"checkpoint": "task7b/checkpoints/A-seed-13"}), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def clf(self, infer, **kw):
        return sc.ShadowClassifier(str(self.root), "cpu", loader=lambda d, dev: {"infer_logits": infer},
                                   checkpoint_set="task7b", **kw)

    def test_unevaluated_or_unknown_status_is_rejected(self):
        self.assertEqual(sc.checkpoint_status(self.root, "task7")["deployment_status"], sc.REJECTED)
        self.assertEqual(sc.checkpoint_status(self.root, "task7b")["deployment_status"], sc.REJECTED)
        (self.root / "task7b" / "STATUS.json").write_text(json.dumps({"deployment_status": "production"}), "utf-8")
        self.assertEqual(sc.checkpoint_status(self.root, "task7b")["deployment_status"], sc.REJECTED)

    def test_output_has_logits_hash_and_status_but_no_decision(self):
        r = self.clf(lambda t: [[2.0, -2.0, 0.0, -1.0, -3.0, 1.0, -0.5, 3.0] for _ in t]).classify(
            [{"speaker": "victim", "text": "fictional"}])
        self.assertEqual(r.status, sc.LOADED)
        self.assertEqual(list(r.logits), list(sm.LABELS))
        self.assertEqual(r.checkpoint_sha256, hashlib.sha256(b"fake-head").hexdigest())
        self.assertTrue(r.development_firings["crisis_self_harm"])
        self.assertEqual(r.deployment_status, sc.REJECTED)
        self.assertEqual(r.product_integration, "Not approved for product integration")
        self.assertFalse(set(r.as_dict()) & sc.FORBIDDEN_KEYS)

    def test_malformed_and_timed_out_output_fail_closed(self):
        for infer in (lambda t: [[float("nan")] * 8 for _ in t], lambda t: [[1.0] * 3 for _ in t],
                      lambda t: [["x"] * 8 for _ in t], lambda t: "garbage"):
            self.assertEqual(self.clf(infer).classify([{"speaker": "victim", "text": "a"}]).status, sc.FAILED)

        def slow(texts):
            time.sleep(0.02)
            return [[0.0] * 8 for _ in texts]
        r = self.clf(slow, timeout_s=0.001).classify([{"speaker": "victim", "text": "a"}])
        self.assertEqual((r.status, r.reason), (sc.FAILED, "inference timed out"))

    def test_crisis_handling_is_identical_whatever_the_model_does(self):
        texts = ["I do not want to live anymore and I have decided tonight.", "Where is the ration office?",
                 "Mujhe kisi insaan se baat karni hai."]

        def raise_(exc):
            raise exc
        variants = [self.clf(lambda t: [[9.0] * 8 for _ in t]), self.clf(lambda t: [[-9.0] * 8 for _ in t]),
                    self.clf(lambda t: raise_(RuntimeError("x"))), self.clf(lambda t: raise_(TimeoutError())),
                    self.clf(lambda t: [[float("nan")] for _ in t]),
                    sc.ShadowClassifier(str(self.root / "missing"), "cpu", checkpoint_set="task7b")]
        for text in texts:
            turns = [{"id": "t1", "speaker": "victim", "text": text, "state": "S2"}]
            before = crisis_check(text)
            outs = [demo.side_by_side(turns, "mobile_chat", v)["authoritative_deterministic"] for v in variants]
            self.assertTrue(all(o == outs[0] for o in outs), text)
            self.assertEqual(crisis_check(text), before)

    def test_demo_product_line(self):
        self.assertEqual(demo.product_line({"deployment_status": sc.REJECTED}), "Not approved for product integration")
        self.assertEqual(demo.product_line({"deployment_status": "candidate_for_human_review",
                                            "promotion_gates_passed": False}), "Not approved for product integration")
        self.assertIn("not approved for product integration",
                      demo.product_line({"deployment_status": "candidate_for_human_review",
                                         "promotion_gates_passed": True}))

    def test_task7_status_can_never_be_weakened(self):
        card = (ML / "shadow" / "MODEL_CARD.md").read_text(encoding="utf-8")
        self.assertIn("`rejected_for_product_integration`", card)
        for word in ("approved_for_backend", "production_ready", "clinically_validated"):
            self.assertNotIn(word, (ML / "shadow" / "classifier.py").read_text(encoding="utf-8"))

    def test_unknown_checkpoint_set_is_refused(self):
        with self.assertRaises(ValueError):
            sc.ShadowClassifier(checkpoint_set="production")


class TestTask7BFirewall(unittest.TestCase):
    def test_no_application_module_imports_the_new_modules(self):
        pattern = re.compile(r"^\s*(from|import)\s+\S*(hardening|stage_c7b|error_analysis)\b", re.M)
        for path in ML.rglob("*.py"):
            rel = path.relative_to(ML).as_posix()
            if rel.startswith(("training/", "tests/")):
                continue
            self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), rel)

    def test_new_modules_read_no_dataset_and_hold_no_machine_path(self):
        for name in ("hardening.py", "stage_c7b.py", "error_analysis.py"):
            text = (ML / "training" / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(from|import)\s+(ml\.data|\.\.data)\b")
            for marker in ("SAHAY_DATASETS_ROOT", "dreaddit", "emoinhindi", "normalized/", "sih-dataset"):
                self.assertNotIn(marker, text, (name, marker))
            self.assertIsNone(re.search(r"[A-Za-z]:[\\/]+(Code|Users)[\\/]|hf_[A-Za-z0-9]{8,}", text), name)

    def test_task7b_artefacts_are_never_tracked(self):
        import subprocess
        tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
        self.assertNotIn("task7b/", tracked)
        self.assertTrue(s7.nothing_committed())


if __name__ == "__main__":
    unittest.main()
