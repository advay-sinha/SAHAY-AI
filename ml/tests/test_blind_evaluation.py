"""Post-freeze blind-evaluation tests. Stdlib only; offline; no dependencies.

Everything here is a TEMPORARY TOOLING FIXTURE in a temporary directory that is
deleted when the test ends. The scenarios are short invented sentences written
to exercise the metric code — a critical one, a control, a multi-turn one —
with `person-9xx` / `fictional-*` people. They are not, and may not become,
evaluation data: they never leave the temp directory, they are never written
under `ml/eval/corpus/`, and the corpus they form is measured against a TEST
coverage plan, never the committed 180-sample plan.

The prediction-firewall tests run in clean subprocesses, because this test
process legitimately has the pipeline imported by other test modules.
"""

import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.eval import blind_evaluation as be
from ml.eval.blind import adapter
from ml.eval.blind import freeze as fz
from ml.eval.blind import plan as pl
from ml.eval.blind import results as rs
from ml.eval.blind.exit_codes import (EXIT_LEDGER, EXIT_NO_FROZEN_CORPUS, EXIT_OK, EXIT_STATE,
                                      EXIT_USAGE)
from ml.eval.blind.store import Store
from ml.eval import schema as ml_schema
from ml.eval.schema import CATEGORIES
from ml.tests.test_blind_corpus import TS, make_review, make_submission, person, roster

REPO = Path(__file__).resolve().parents[2]
ML = REPO / "ml"

#: A TEST plan sized for the miniature corpus below. The command line never
#: injects a plan, so a real freeze is always measured against the committed one.
TEST_PLAN = {
    "schema": pl.PLAN_SCHEMA,
    "plan_version": "test-eval-0",
    "corpus_version": "v1",
    "description": "TEST ONLY. Not a corpus target.",
    "total_min": 6,
    "no_stereotype_rule": "test",
    "languages": [{"language": "en", "script": ["latin"], "min": 2, "why": "test plan"},
                  {"language": "hi", "script": ["devanagari"], "min": 2, "why": "test plan"},
                  {"language": "hinglish", "script": ["latin"], "min": 2, "why": "test plan"}],
    "categories": [{"category": c, "min_total": 0, "min_per_language": 0, "why": "test plan"}
                   for c in pl.CATEGORY_NAMES],
    "slices": [{"slice": s, "min_total": 0, "min_per_language": 0, "why": "test plan"}
               for s in pl.SLICE_NAMES],
    "notes": ["test plan"],
}

#: Six temporary scenarios. Flat, invented, and chosen so that the metric code
#: has a denominator for each thing it measures: one crisis, one immediate
#: danger, one multi-turn threat, two controls and one safe near miss.
FIXTURES = [
    {
        "n": 1, "language": "en",
        "texts": ["I do not want to be alive any more and I have decided to end it tonight."],
        "labels": {"crisis_self_harm": True}, "routing": "Critical",
        "evidence": {"crisis_self_harm": ["t1"]},
        "slices": ["indirect_language"], "abstain": False,
    },
    {
        "n": 2, "language": "en",
        "texts": ["I would like to know which window accepts the completed application form."],
        "labels": {}, "routing": "Low", "evidence": {},
        "slices": ["safe_near_miss"], "abstain": False,
    },
    {
        "n": 3, "language": "hi",
        "texts": ["\u091a\u093e\u0930 \u0932\u094b\u0917 \u0905\u092d\u0940 \u092e\u0947\u0930\u0947 \u0917\u0947\u091f \u0915\u0947 \u092c\u093e\u0939\u0930 \u0916\u0921\u093c\u0947 \u0939\u0948\u0902 \u0914\u0930 \u0924\u093e\u0932\u093e \u0924\u094b\u0921\u093c \u0930\u0939\u0947 \u0939\u0948\u0902\u0964"],
        "labels": {"immediate_danger": True, "continuing_threat": True}, "routing": "Critical",
        "evidence": {"immediate_danger": ["t1"], "continuing_threat": ["t1"]},
        "slices": ["polite_understated_danger"], "abstain": False,
    },
    {
        "n": 4, "language": "hi",
        "texts": ["\u0936\u093f\u0915\u093e\u092f\u0924 \u0915\u0947 \u092c\u093e\u0926 \u0938\u0947 \u0935\u0947 \u0930\u094b\u095b \u0927\u092e\u0915\u0940 \u0926\u0947 \u0930\u0939\u0947 \u0939\u0948\u0902\u0964",
                  "\u0915\u0932 \u0909\u0928\u094d\u0939\u094b\u0902\u0928\u0947 \u0915\u0939\u093e \u0915\u093f \u0915\u0947\u0938 \u0935\u093e\u092a\u0938 \u0932\u094b \u0935\u0930\u0928\u093e \u0905\u091a\u094d\u091b\u093e \u0928\u0939\u0940\u0902 \u0939\u094b\u0917\u093e\u0964"],
        "labels": {"continuing_threat": True}, "routing": "High",
        "evidence": {"continuing_threat": ["t1", "t2"]},
        "slices": ["multi_turn_evidence", "later_turn_evidence"], "abstain": False,
    },
    {
        "n": 5, "language": "hinglish",
        "texts": ["Wo mera phone check karte hain isliye main khul kar baat nahi kar sakti."],
        "labels": {"communication_safety_coercion": True}, "routing": "High",
        "evidence": {"communication_safety_coercion": ["t1"]},
        "slices": ["romanised_hindi", "code_switching"], "abstain": False,
    },
    {
        "n": 6, "language": "hinglish",
        "texts": ["Maine kabhi apne aap ko nuksan pahunchane ka socha bhi nahi hai, bas form ka "
                  "status poochna tha."],
        "labels": {"negated_risk_language": True}, "routing": "Low", "evidence": {},
        "slices": ["explicit_negation", "safe_near_miss"], "abstain": False,
    },
]


def build_rich_corpus(root, plan=TEST_PLAN, freeze=True):
    """A complete, fully reviewed, frozen miniature corpus in a temp directory."""
    store = Store(root, "v1", plan=plan)
    store.init()
    (root / "assignments" / "v1" / "roster.json").write_text(json.dumps(roster()), encoding="utf-8")
    owner = person("person-902")
    records = []
    for spec in FIXTURES:
        record = make_submission(spec["n"], language=spec["language"], texts=spec["texts"],
                                 author="person-901", slices=tuple(spec["slices"]))
        store.submit(record, owner, TS)
        records.append((record, spec))
    allocation = store.save_assignment(owner, TS)
    for record, spec in records:
        row = next(r for r in allocation["assignments"]
                   if r["submission_id"] == record["submission_id"])
        for entry in row["reviewers"]:
            review = make_review(record, entry["person_id"], labels=spec["labels"],
                                 routing=spec["routing"], evidence=spec["evidence"],
                                 abstain=spec["abstain"],
                                 reasoning="Temporary tooling fixture; the reading is the plain one.")
            store.import_review(review, owner, TS)
    for record, _ in records:
        if store.state_of(record["submission_id"]) == "review_complete":
            store.move(record["submission_id"], "eligible", owner, "every gate passed",
                       {"submission_id": record["submission_id"]}, TS)
    if freeze:
        fz.freeze(store, owner, TS)
    return store, [r for r, _ in records], owner


class TempCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store, self.records, self.owner = build_rich_corpus(self.root)
        self.actor = person("person-902")

    def tearDown(self):
        self.tmp.cleanup()

    def evaluate(self, regression=False):
        return be.run(self.store, self.actor, regression=regression)

    def manifest_path(self):
        return self.store.path("frozen", "freeze_manifest.json")

    def rewrite_manifest(self, mutate):
        path = self.manifest_path()
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")


# --- the adapter -------------------------------------------------------------------------


class TestAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, _, _ = build_rich_corpus(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_frozen_corpus_adapts_and_validates(self):
        samples = adapter.adapt_all(self.store.read_frozen("corpus"), self.store.read_frozen("labels"))
        self.assertEqual(len(samples), len(FIXTURES))
        self.assertEqual(adapter.validate_all(samples), [])

    def test_every_derivation_is_declared(self):
        for key in ("channel", "expected.crisis_precheck", "expected.band",
                    "expected.routed_critical", "tags"):
            self.assertIn(key, adapter.DERIVED_EXPECTATIONS)

    def test_the_text_channel_is_fixed_and_documented(self):
        samples = adapter.adapt_all(self.store.read_frozen("corpus"), self.store.read_frozen("labels"))
        self.assertTrue(all(s["channel"] == adapter.CHANNEL for s in samples))
        self.assertIn("D4", adapter.DERIVED_EXPECTATIONS["channel"])

    def test_expectations_come_from_the_human_labels(self):
        samples = {s["id"]: s for s in adapter.adapt_all(self.store.read_frozen("corpus"),
                                                         self.store.read_frozen("labels"))}
        crisis = samples["SUB-V1-EN-0001"]
        self.assertTrue(crisis["labels"]["crisis_self_harm"])
        self.assertTrue(crisis["expected"]["crisis_precheck"])
        self.assertTrue(crisis["expected"]["routed_critical"])
        self.assertEqual(crisis["human_routing_label"], "Critical")
        control = samples["SUB-V1-EN-0002"]
        self.assertFalse(control["expected"]["routed_critical"])
        self.assertEqual(control["human_routing_label"], "Low")
        # and no band ground truth is invented for either of them
        self.assertIsNone(crisis["expected"]["band"])
        self.assertIsNone(control["expected"]["band"])

    def test_a_mismatched_label_row_is_refused(self):
        corpus = self.store.read_frozen("corpus")
        labels = self.store.read_frozen("labels")
        with self.assertRaises(adapter.AdapterError):
            adapter.adapt_all(corpus, labels[:-1])
        with self.assertRaises(adapter.AdapterError):
            adapter.adapt(corpus[0], labels[1])

    def test_validation_catches_a_broken_adapted_sample(self):
        samples = adapter.adapt_all(self.store.read_frozen("corpus"), self.store.read_frozen("labels"))
        broken = dict(samples[0])
        broken["expected"] = dict(broken["expected"])
        broken["expected"]["routed_critical"] = False
        self.assertTrue(adapter.validate_adapted(broken))


# --- the canonical channel ------------------------------------------------------------------


def frozen_enum(name):
    """One line of the frozen enum block in docs/contracts/CONTRACTS.md section 9."""
    text = (REPO / "docs" / "contracts" / "CONTRACTS.md").read_text(encoding="utf-8")
    block = text.split("<!-- enums:begin -->")[1].split("<!-- enums:end -->")[0]
    for line in block.splitlines():
        if line.strip().startswith(name + " "):
            return tuple(part.strip() for part in line.split(None, 1)[1].split("|"))
    raise AssertionError(f"{name} is not in the frozen enum block")


class TestCanonicalChannel(unittest.TestCase):
    """The adapter may only emit a channel the frozen contract already defines."""

    def test_the_adapter_channel_is_a_canonical_session_channel(self):
        self.assertIn(adapter.CHANNEL, frozen_enum("session_channel"))
        self.assertIn(adapter.CHANNEL, ml_schema.CHANNELS)

    def test_the_adapter_channel_is_a_canonical_text_channel(self):
        self.assertIn(adapter.CHANNEL, frozen_enum("text_channel"))
        self.assertIn(adapter.CHANNEL, adapter.TEXT_CHANNELS)

    def test_the_local_text_channel_copy_matches_the_frozen_contract(self):
        self.assertEqual(adapter.TEXT_CHANNELS, frozen_enum("text_channel"))

    def test_the_local_text_channel_copy_matches_the_backend_enum(self):
        enums = (REPO / "backend" / "app" / "core" / "enums.py").read_text(encoding="utf-8")
        line = next(x for x in enums.splitlines() if x.startswith("TEXT_CHANNELS"))
        declared = tuple(part.strip().strip('"\'')
                         for part in line.split("(", 1)[1].rsplit(")", 1)[0].split(",")
                         if part.strip())
        self.assertEqual(adapter.TEXT_CHANNELS, declared)

    def test_the_text_channel_keeps_d4_structurally_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _, _ = build_rich_corpus(Path(tmp))
            outcome = be.run(store, person("person-902"))
        d4 = outcome["result"]["sections"]["svi_distribution"]["d4_structurally_unavailable"]
        self.assertEqual(d4["problems"], [])
        self.assertEqual(d4["checked"], len(FIXTURES))

    def test_an_unsupported_channel_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _, _ = build_rich_corpus(Path(tmp), freeze=False)
            sample = adapter.adapt_all(
                [{"submission_id": "SUB-V1-EN-0001", "language": "en", "script": "latin",
                  "turns": [{"id": "t1", "speaker": "victim", "state": "S1", "text": "a form question"}]}],
                [{"submission_id": "SUB-V1-EN-0001", "labels": {c: False for c in CATEGORIES},
                  "routing": "Low", "expected_evidence": {}, "expected_abstention": False,
                  "declared_slices": []}])[0]
        for bad, reason in (("mobile_voice", "not a text channel"),
                            ("upload", "not a text channel"),
                            ("sms", "not a canonical session_channel"),
                            ("", "not a canonical session_channel")):
            broken = dict(sample)
            broken["channel"] = bad
            errs = adapter.validate_adapted(broken)
            self.assertTrue(any(reason in e for e in errs), f"{bad}: {errs}")

    def test_portal_chat_would_also_be_acceptable_but_is_not_what_we_emit(self):
        self.assertIn("portal_chat", adapter.TEXT_CHANNELS)
        self.assertNotEqual(adapter.CHANNEL, "portal_chat")


# --- routing label is not an SVI band ---------------------------------------------------------


class TestRoutingIsNotABand(TempCorpus):
    def test_the_adapter_never_sets_a_band(self):
        samples = adapter.adapt_all(self.store.read_frozen("corpus"), self.store.read_frozen("labels"))
        self.assertTrue(all(s["expected"]["band"] is None for s in samples))
        self.assertTrue(all(s["human_routing_label"] in ("Low", "Moderate", "High", "Critical")
                            for s in samples))

    def test_a_band_taken_from_the_routing_label_is_refused(self):
        samples = adapter.adapt_all(self.store.read_frozen("corpus"), self.store.read_frozen("labels"))
        for sample in samples:
            substituted = dict(sample)
            substituted["expected"] = dict(sample["expected"])
            substituted["expected"]["band"] = sample["human_routing_label"]
            errs = adapter.validate_adapted(substituted)
            self.assertTrue(any("must be null" in e for e in errs), errs)
            self.assertTrue(any("never be substituted" in e or "cannot be substituted" in e
                                for e in errs), errs)

    def test_routed_critical_must_follow_the_routing_label(self):
        samples = adapter.adapt_all(self.store.read_frozen("corpus"), self.store.read_frozen("labels"))
        broken = dict(samples[1])
        broken["expected"] = dict(broken["expected"])
        broken["expected"]["routed_critical"] = True
        self.assertTrue(any("does not match the human routing label" in e
                            for e in adapter.validate_adapted(broken)))

    def test_the_svi_distribution_works_without_any_band_label(self):
        sections = self.evaluate()["result"]["sections"]
        block = sections["svi_distribution"]
        self.assertFalse(block["band_ground_truth"]["available"])
        self.assertIn("routing label", block["band_ground_truth"]["reason"])
        self.assertEqual(sum(block["scored_bands"].values()) + block["needs_human_assessment"],
                         len(FIXTURES))

    def test_no_band_accuracy_metric_is_emitted(self):
        sections = self.evaluate()["result"]["sections"]
        blob = json.dumps(sections["svi_distribution"], ensure_ascii=False)
        for forbidden in ("band_agreement", "band_agreement_rate", "band_disagreements",
                          "band_specified", "band_accuracy"):
            self.assertNotIn(forbidden, blob, f"a band metric leaked: {forbidden}")
        self.assertNotIn("band_agreement", json.dumps(sections, ensure_ascii=False))

    def test_needs_human_assessment_is_never_counted_as_a_band(self):
        block = self.evaluate()["result"]["sections"]["svi_distribution"]
        self.assertNotIn("Needs Human Assessment", block["scored_bands"])
        self.assertEqual(block["needs_human_assessment"], len(FIXTURES))  # this fixture set abstains
        self.assertIn("abstention, not a band", block["not_scored_note"])

    def test_coverage_categories_are_cut_on_the_routing_label(self):
        sections = self.evaluate()["result"]["sections"]
        controls = sections["by_category"]["no_alert_control"]["sample_ids"]
        self.assertIn("SUB-V1-EN-0002", controls)
        self.assertNotIn("SUB-V1-EN-0001", controls)

    def test_the_report_declares_the_derived_expectations(self):
        result = self.evaluate()["result"]
        derived = result["derived_expectations"]
        self.assertIn("DERIVED PROXY", derived["expected.crisis_precheck"])
        self.assertIn("not a\nseparately annotated ground truth".replace("\n", " "),
                      derived["expected.crisis_precheck"].replace("\n", " "))
        self.assertIn("always null", derived["expected.band"])
        self.assertIn("routing label", derived["expected.routed_critical"])

    def test_existing_evaluator_metrics_are_unchanged_by_a_blind_run(self):
        """A blind run must not perturb the shared pipeline for anything else."""
        from ml.eval.evaluate import evaluate as evaluate_corpus, headline
        dev = json.loads((ML / "eval" / "corpus" / "dev.json").read_text(encoding="utf-8"))["samples"]
        before = headline(evaluate_corpus(dev[:12]))
        self.evaluate()
        after = headline(evaluate_corpus(dev[:12]))
        self.assertEqual(before, after)


# --- refusals ------------------------------------------------------------------------------


class TestRefusals(TempCorpus):
    def test_no_frozen_corpus(self):
        with tempfile.TemporaryDirectory() as empty:
            store = Store(Path(empty), "v1")
            store.init()
            self.assertEqual(be.main(["--root", empty, "--actor", "", "status"]),
                             EXIT_NO_FROZEN_CORPUS)
            with self.assertRaises(be.EvaluationError) as ctx:
                be.preflight(store, regression=False)
            self.assertEqual(ctx.exception.code, EXIT_NO_FROZEN_CORPUS)

    def test_incomplete_freeze_manifest(self):
        self.rewrite_manifest(lambda m: m.pop("corpus_sha256"))
        with self.assertRaises(be.EvaluationError) as ctx:
            be.preflight(self.store, regression=False)
        self.assertEqual(ctx.exception.code, EXIT_LEDGER)

    def test_zero_sample_manifest(self):
        self.rewrite_manifest(lambda m: m.__setitem__("samples", 0))
        with self.assertRaises(be.EvaluationError) as ctx:
            be.preflight(self.store, regression=False)
        self.assertEqual(ctx.exception.code, EXIT_LEDGER)

    def test_manifest_version_mismatch(self):
        self.rewrite_manifest(lambda m: m.__setitem__("corpus_version", "v9"))
        with self.assertRaises(be.EvaluationError) as ctx:
            be.preflight(self.store, regression=False)
        self.assertEqual(ctx.exception.code, EXIT_LEDGER)
        self.assertIn("corpus version", str(ctx.exception))

    def test_corpus_hash_mismatch(self):
        self.rewrite_manifest(lambda m: m.__setitem__("corpus_sha256", "0" * 64))
        with self.assertRaises(be.EvaluationError) as ctx:
            be.preflight(self.store, regression=False)
        self.assertEqual(ctx.exception.code, EXIT_LEDGER)

    def test_per_file_hash_mismatch(self):
        path = self.store.path("frozen", "labels.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload[0]["routing"] = "Moderate"
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")
        with self.assertRaises(be.EvaluationError) as ctx:
            be.preflight(self.store, regression=False)
        self.assertEqual(ctx.exception.code, EXIT_LEDGER)
        self.assertIn("labels.json", str(ctx.exception))

    def test_ledger_head_mismatch(self):
        path = self.store.ledger("reviews")
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        with self.assertRaises(be.EvaluationError) as ctx:
            be.preflight(self.store, regression=False)
        self.assertEqual(ctx.exception.code, EXIT_LEDGER)

    def test_invalid_sample_state(self):
        wrong = {r["submission_id"]: "eligible" for r in self.records}
        with mock.patch.object(Store, "current_states", return_value=wrong):
            with self.assertRaises(be.EvaluationError) as ctx:
                be.preflight(self.store, regression=False)
        self.assertEqual(ctx.exception.code, EXIT_STATE)

    def test_regression_without_an_independent_result_is_refused(self):
        with self.assertRaises(be.EvaluationError) as ctx:
            be.preflight(self.store, regression=True)
        self.assertEqual(ctx.exception.code, EXIT_USAGE)

    def test_run_requires_a_named_actor(self):
        self.assertEqual(be.main(["--root", str(self.root), "run"]), EXIT_USAGE)

    def test_a_failed_run_leaves_the_corpus_unexposed(self):
        self.rewrite_manifest(lambda m: m.__setitem__("corpus_sha256", "0" * 64))
        code = be.main(["--root", str(self.root), "--actor", "person-902", "run"])
        self.assertEqual(code, EXIT_LEDGER)
        self.assertIsNone(rs.published_independent(self.store))
        self.assertIsNone(rs.exposure_record(self.store))
        for record in self.records:
            self.assertEqual(self.store.state_of(record["submission_id"]), "frozen")


# --- a successful independent run -----------------------------------------------------------


class TestIndependentRun(TempCorpus):
    def setUp(self):
        super().setUp()
        self.outcome = self.evaluate()
        self.result = self.outcome["result"]
        self.sections = self.result["sections"]

    def test_the_run_is_labelled_independent(self):
        self.assertEqual(self.result["independence"], rs.INDEPENDENT)
        self.assertEqual(rs.published_independent(self.store)["independence"], rs.INDEPENDENT)

    def test_every_required_section_is_present_and_populated(self):
        for name in rs.REQUIRED_SECTIONS:
            self.assertIn(name, self.sections)
            self.assertNotIn(self.sections[name], (None, {}, []), name)
        self.assertEqual(rs.validate_result(rs.published_independent(self.store)), [])

    def test_per_detector_metrics_carry_denominators(self):
        table = self.sections["detector_metrics"]["per_detector"]
        for name, row in table.items():
            if "excluded" in row:
                continue
            for key in ("tp", "fp", "tn", "fn", "n", "precision_denominator",
                        "recall_denominator", "specificity_denominator"):
                self.assertIn(key, row, f"{name}.{key}")

    def test_an_undefined_metric_is_null_not_zero(self):
        table = self.sections["detector_metrics"]["per_detector"]
        undefined = [row for row in table.values()
                     if "excluded" not in row and row["recall_denominator"] == 0]
        for row in undefined:
            self.assertIsNone(row["recall"])
            self.assertIsNone(row["f1"])

    def test_the_undetectable_category_is_excluded_with_a_reason(self):
        excluded = self.sections["detector_metrics"]["excluded"]
        self.assertIn("explicit_human_request", excluded)
        self.assertTrue(excluded["explicit_human_request"])

    def test_per_language_results_cover_all_three_languages(self):
        self.assertEqual(sorted(self.sections["by_language"]), ["en", "hi", "hinglish"])
        self.assertEqual(self.sections["by_language"]["hinglish"]["n"], 2)
        for lang in ("en", "hi", "hinglish"):
            self.assertIn("routing", self.sections["by_language"][lang])
            self.assertIn("detectors", self.sections["by_language"][lang])

    def test_per_category_results_cover_the_whole_plan(self):
        self.assertEqual(sorted(self.sections["by_category"]), sorted(pl.CATEGORY_NAMES))
        self.assertGreaterEqual(self.sections["by_category"]["crisis_self_harm"]["n"], 1)
        self.assertGreaterEqual(self.sections["by_category"]["no_alert_control"]["n"], 1)

    def test_challenge_slice_results_cover_every_slice_in_the_plan(self):
        cuts = self.sections["by_challenge_slice"]
        self.assertEqual(sorted(cuts), sorted(pl.SLICE_NAMES))
        self.assertGreaterEqual(cuts["explicit_negation"]["n"], 1)
        self.assertGreaterEqual(cuts["romanised_hindi"]["n"], 1)
        self.assertGreaterEqual(cuts["multi_turn_evidence"]["n"], 1)
        self.assertGreaterEqual(cuts["safe_near_miss"]["n"], 2)

    def test_the_label_slices_are_reported_separately(self):
        label_slices = self.sections["label_slices"]
        self.assertEqual(sorted(label_slices), ["adversarial", "negation", "quotation_attribution"])
        self.assertGreaterEqual(label_slices["negation"]["n"], 1)

    def test_critical_misses_are_counted_and_named(self):
        block = self.sections["critical_misses"]
        self.assertIn("count", block)
        self.assertEqual(block["count"], len(block["sample_ids"]))
        self.assertEqual(block["critical_event_miss_rate"]["critical_events"], 2)
        self.assertTrue(all(sid.startswith("SUB-") for sid in block["sample_ids"]))

    def test_false_escalations_are_counted_and_named(self):
        block = self.sections["false_escalations"]
        self.assertEqual(block["count"], len(block["sample_ids"]))

    def test_abstention_is_reported_with_its_denominator(self):
        block = self.sections["abstention"]
        for key in ("expected_abstain", "abstained_when_expected", "abstention_coverage",
                    "abstained_total", "needs_human_assessment"):
            self.assertIn(key, block)

    def test_evidence_validity_and_exact_agreement_are_reported(self):
        block = self.sections["evidence_link_validity"]
        for key in ("cited_ids", "cited_validity", "positive_evidence_validity",
                    "true_positives_with_labels", "evidence_exact_rate", "evidence_overlap_rate"):
            self.assertIn(key, block)

    def test_the_svi_band_distribution_and_needs_human_count_are_reported(self):
        block = self.sections["svi_distribution"]
        self.assertEqual(sum(block["scored_bands"].values()) + block["needs_human_assessment"],
                         len(FIXTURES))
        self.assertEqual(sorted(block["svi_by_sample"]),
                         sorted(r["submission_id"] for r in self.records))

    def test_the_routing_label_section_compares_routing_with_routing(self):
        block = self.sections["routing_labels"]
        self.assertEqual(sum(block["human_label_distribution"].values()), len(FIXTURES))
        self.assertEqual(block["human_routed_critical"],
                         sum(1 for f in FIXTURES if f["routing"] == "Critical"))
        self.assertIn("critical_routing", block)
        self.assertIn("never", block["band_substitution"])

    def test_multi_turn_replay_is_checked(self):
        replay = self.sections["scenario_replay"]
        self.assertGreaterEqual(replay["multi_turn_samples"], 1)
        self.assertTrue(replay["consistent"])
        self.assertEqual(replay["inconsistent"], [])

    def test_determinism_is_proved_and_names_its_exclusions(self):
        determinism = self.sections["determinism"]
        self.assertTrue(determinism["identical"])
        self.assertTrue(determinism["reported_predictions_match"])
        self.assertEqual(determinism["runs"], 2)
        for key in ("run_id", "run_at", "run_by"):
            self.assertIn(key, determinism["excluded_metadata"])

    def test_guardrail_prohibition_coverage_is_reported(self):
        block = self.sections["guardrail_prohibition_coverage"]
        self.assertGreater(block["prohibitions"], 0)
        self.assertIn("applicable_to_corpus_output", block)

    def test_provenance_fields_are_recorded(self):
        corpus = self.result["corpus"]
        self.assertEqual(corpus["corpus_version"], "v1")
        self.assertEqual(len(corpus["corpus_sha256"]), 64)
        self.assertEqual(len(corpus["freeze_manifest_sha256"]), 64)
        self.assertEqual(set(self.result["ledger_heads"]),
                         {"submissions", "reviews", "adjudications", "states"})
        for key in ("pipeline_version", "scoring_version", "lexicon_version", "validator_version"):
            self.assertTrue(self.result["versions"][key])
        self.assertTrue(self.result["run_id"])
        self.assertTrue(self.result["run_at"])

    def test_the_corpus_is_exposed_and_the_samples_are_moved(self):
        self.assertTrue(rs.exposure_record(self.store)["exposed"])
        for record in self.records:
            self.assertEqual(self.store.state_of(record["submission_id"]),
                             "contaminated_after_evaluation")

    def test_no_narrative_appears_in_the_result_or_the_markdown(self):
        blob = json.dumps(self.result, ensure_ascii=False)
        markdown = self.outcome["paths"]["md"].read_text(encoding="utf-8")
        for spec in FIXTURES:
            for text in spec["texts"]:
                self.assertNotIn(text[:24], blob)
                self.assertNotIn(text[:24], markdown)
        self.assertIn("SUB-V1-EN-0001", blob)

    def test_the_result_is_written_outside_git_and_under_the_private_root(self):
        path = self.outcome["paths"]["json"]
        self.assertTrue(str(path).startswith(str(self.root.resolve())))
        self.assertFalse((REPO / "ml" / "eval" / "results" / path.name).exists())

    def test_no_temporary_artefact_is_left_behind(self):
        self.assertEqual(rs.pending_artefacts(self.store), [])


# --- determinism and regression ---------------------------------------------------------------


class TestDeterminismAndRegression(TempCorpus):
    def test_two_runs_produce_identical_substantive_results(self):
        first = self.evaluate()["result"]
        second = self.evaluate(regression=True)["result"]
        self.assertEqual(rs.substantive(first), rs.substantive(second))
        self.assertEqual(rs.result_sha256(first), rs.result_sha256(second))
        self.assertNotEqual(first["independence"], second["independence"])

    def test_a_second_run_is_refused_without_the_regression_flag(self):
        self.evaluate()
        code = be.main(["--root", str(self.root), "--actor", "person-902", "run"])
        self.assertEqual(code, EXIT_USAGE)

    def test_an_explicit_regression_run_is_labelled_and_compared(self):
        self.evaluate()
        outcome = self.evaluate(regression=True)
        self.assertEqual(outcome["result"]["independence"], rs.REGRESSION)
        self.assertTrue(outcome["comparison"]["identical"])
        self.assertEqual(outcome["comparison"]["changed_sections"], [])

    def test_the_independent_result_is_never_overwritten(self):
        first = self.evaluate()
        original = rs.published_independent(self.store)
        self.evaluate(regression=True)
        self.assertEqual(rs.published_independent(self.store), original)
        with self.assertRaises(rs.ResultError):
            rs.finalize(self.store, "someotherrun", first["result"], "x", independent=True)

    def test_each_regression_run_gets_its_own_file(self):
        self.evaluate()
        one = self.evaluate(regression=True)
        two = be.run(self.store, self.actor, regression=True, at="2026-09-13T09:00:00+05:30")
        self.assertNotEqual(one["paths"]["json"], two["paths"]["json"])
        files = sorted((self.root / "reports" / "v1" / "regression").glob("*.json"))
        self.assertEqual(len(files), 2)

    def test_a_regression_run_reports_a_behaviour_change(self):
        self.evaluate()
        original = rs.published_independent(self.store)
        altered = json.loads(json.dumps(original))
        altered["sections"]["critical_misses"]["count"] = 99
        comparison = rs.compare(original, altered)
        self.assertFalse(comparison["identical"])
        self.assertIn("critical_misses", comparison["changed_sections"])

    def test_the_command_exposes_no_tuning_option(self):
        actions = be.build_parser()._actions
        flags = {opt for action in actions for opt in action.option_strings}
        for banned in ("--threshold", "--weight", "--weights", "--lexicon", "--tune", "--band"):
            self.assertNotIn(banned, flags)


# --- atomicity and recovery ----------------------------------------------------------------


class TestAtomicityAndRecovery(TempCorpus):
    def test_an_incomplete_result_is_never_published(self):
        outcome = self.evaluate()
        broken = json.loads(json.dumps(outcome["result"]))
        broken["sections"].pop("determinism")
        with tempfile.TemporaryDirectory() as other:
            store, _, _ = build_rich_corpus(Path(other))
            with self.assertRaises(rs.ResultError):
                rs.finalize(store, "run1", broken, "x", independent=True)
            self.assertIsNone(rs.published_independent(store))
            self.assertEqual(rs.pending_artefacts(store), [])

    def test_a_non_deterministic_result_is_not_publishable(self):
        outcome = self.evaluate()
        broken = json.loads(json.dumps(outcome["result"]))
        broken["sections"]["determinism"]["identical"] = False
        self.assertTrue(any("deterministic" in e for e in rs.validate_result(broken)))

    def test_temporary_directories_are_cleaned_up(self):
        stray = self.store.path("reports") / f"{rs.TEMP_PREFIX}interrupted"
        stray.mkdir(parents=True, exist_ok=True)
        (stray / "partial.json").write_text("{}", encoding="utf-8")
        self.assertIn(f"{rs.TEMP_PREFIX}interrupted", rs.pending_artefacts(self.store))
        self.evaluate()
        self.assertEqual(rs.pending_artefacts(self.store), [])
        self.assertFalse(stray.exists())

    def test_an_orphaned_companion_is_reported_and_replaced(self):
        rs.independent_md(self.store).parent.mkdir(parents=True, exist_ok=True)
        rs.independent_md(self.store).write_text("# interrupted\n", encoding="utf-8")
        self.assertTrue(any("companion" in item for item in rs.pending_artefacts(self.store)))
        self.evaluate()
        self.assertEqual(rs.pending_artefacts(self.store), [])
        self.assertIn("Blind evaluation", rs.independent_md(self.store).read_text(encoding="utf-8"))

    def test_a_published_result_with_no_exposure_record_is_repaired_not_rerun(self):
        outcome = self.evaluate()
        original = rs.published_independent(self.store)
        rs.exposure_path(self.store).unlink()
        self.assertTrue(rs.unrecorded_publication(self.store))
        repaired = be.repair(self.store, self.actor, at=TS)
        self.assertIsNotNone(repaired)
        self.assertTrue(rs.exposure_record(self.store)["exposed"])
        self.assertEqual(rs.published_independent(self.store), original)
        self.assertEqual(rs.published_independent(self.store)["run_id"], outcome["result"]["run_id"])

    def test_repair_is_idempotent_and_does_not_break_the_state_ledger(self):
        self.evaluate()
        rs.exposure_path(self.store).unlink()
        be.repair(self.store, self.actor, at=TS)
        self.assertIsNone(be.repair(self.store, self.actor, at=TS))
        self.store.current_states()  # replays the whole ledger; raises if it is inconsistent

    def test_clean_temp_never_touches_a_finalized_result(self):
        self.evaluate()
        before = rs.independent_json(self.store).read_bytes()
        be.main(["--root", str(self.root), "--actor", "person-902", "clean-temp"])
        self.assertEqual(rs.independent_json(self.store).read_bytes(), before)


# --- isolation from the committed repository ---------------------------------------------------


class TestRepositoryIsolation(TempCorpus):
    def snapshot(self, directory):
        return {p.name: p.read_bytes() for p in sorted(Path(directory).glob("*.json"))}

    def test_the_public_corpora_stay_byte_identical(self):
        before = self.snapshot(ML / "eval" / "corpus")
        self.evaluate()
        self.assertEqual(before, self.snapshot(ML / "eval" / "corpus"))

    def test_the_published_evaluation_results_stay_byte_identical(self):
        before = self.snapshot(ML / "eval" / "results")
        self.evaluate()
        self.assertEqual(before, self.snapshot(ML / "eval" / "results"))

    def test_locked_json_remains_empty(self):
        self.evaluate()
        locked = json.loads((ML / "eval" / "corpus" / "locked.json").read_text(encoding="utf-8"))
        self.assertEqual(locked["samples"], [])

    def test_no_freeze_manifest_is_written_into_git(self):
        self.evaluate()
        manifests = ML / "eval" / "blind" / "freeze_manifests"
        self.assertEqual(sorted(p.name for p in manifests.iterdir()), ["README.md"])

    def test_the_run_makes_no_network_call(self):
        class Blocked(Exception):
            pass

        def deny(*args, **kwargs):
            raise Blocked("network access attempted")

        with mock.patch.object(socket, "socket", deny), \
                mock.patch.object(socket, "create_connection", deny), \
                mock.patch.object(socket, "getaddrinfo", deny):
            outcome = self.evaluate()
        self.assertEqual(outcome["result"]["independence"], rs.INDEPENDENT)


# --- the prediction firewall --------------------------------------------------------------------


SETUP = (
    "import json, sys, tempfile\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, '.')\n"
    "from ml.eval import blind_evaluation as be\n"
    "from ml.eval.blind import firewall\n"
)
BUILD = (
    "from ml.tests.test_blind_evaluation import build_rich_corpus\n"
    "tmp = tempfile.mkdtemp()\n"
    "root = Path(tmp)\n"
    "store, records, owner = build_rich_corpus(root)\n"
    "import ml.eval.blind.firewall as fw\n"
)
REPORT = "print('LOADED:' + ','.join(firewall.loaded()))\n"


def run_subprocess(script):
    return subprocess.run([sys.executable, "-c", script], cwd=str(REPO), capture_output=True,
                          text=True, timeout=300)


class TestPredictionFirewall(unittest.TestCase):
    def assert_clean_run(self, script, expect_code=None):
        result = run_subprocess(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout.replace("\r\n", "\n")
        self.assertIn("LOADED:\n", out, f"a prediction module was loaded:\n{out}")
        if expect_code is not None:
            self.assertIn(f"CODE:{expect_code}", out)
        return out

    def test_importing_the_module_loads_no_prediction_module(self):
        self.assert_clean_run(SETUP + REPORT)

    def test_configuration_failure_loads_no_prediction_module(self):
        self.assert_clean_run(
            SETUP + "print('CODE:%d' % be.main(['--root', 'C:/definitely/not/here', 'status']))\n"
            + REPORT, expect_code=EXIT_USAGE)

    def test_missing_root_loads_no_prediction_module(self):
        self.assert_clean_run(
            SETUP + "import os\n"
                    "os.environ.pop('SAHAY_EVAL_ROOT', None)\n"
                    "print('CODE:%d' % be.main(['status']))\n" + REPORT, expect_code=EXIT_USAGE)

    def test_missing_frozen_corpus_loads_no_prediction_module(self):
        self.assert_clean_run(
            SETUP + "from ml.eval.blind.store import Store\n"
                    "from ml.tests.test_blind_corpus import roster\n"
                    "tmp = tempfile.mkdtemp()\n"
                    "Store(Path(tmp), 'v1').init()\n"
                    "(Path(tmp) / 'assignments' / 'v1' / 'roster.json').write_text("
                    "json.dumps(roster()), encoding='utf-8')\n"
                    "print('CODE:%d' % be.main(['--root', tmp, '--actor', 'person-902', 'run']))\n"
            + REPORT, expect_code=EXIT_NO_FROZEN_CORPUS)

    def test_a_missing_actor_loads_no_prediction_module(self):
        self.assert_clean_run(
            SETUP + "from ml.eval.blind.store import Store\n"
                    "tmp = tempfile.mkdtemp()\n"
                    "Store(Path(tmp), 'v1').init()\n"
                    "print('CODE:%d' % be.main(['--root', tmp, 'run']))\n" + REPORT,
            expect_code=EXIT_USAGE)

    def test_hash_failure_loads_no_prediction_module(self):
        self.assert_clean_run(
            SETUP + BUILD +
            "p = store.path('frozen', 'freeze_manifest.json')\n"
            "m = json.loads(p.read_text(encoding='utf-8'))\n"
            "m['corpus_sha256'] = '0' * 64\n"
            "p.write_text(json.dumps(m), encoding='utf-8')\n"
            "print('CODE:%d' % be.main(['--root', tmp, '--actor', 'person-902', 'run']))\n" + REPORT,
            expect_code=EXIT_LEDGER)

    def test_ledger_head_failure_loads_no_prediction_module(self):
        self.assert_clean_run(
            SETUP + BUILD +
            "p = store.ledger('reviews')\n"
            "lines = p.read_text(encoding='utf-8').splitlines()\n"
            "p.write_text('\\n'.join(lines[:-1]) + '\\n', encoding='utf-8')\n"
            "print('CODE:%d' % be.main(['--root', tmp, '--actor', 'person-902', 'run']))\n" + REPORT,
            expect_code=EXIT_LEDGER)

    def test_state_failure_loads_no_prediction_module(self):
        self.assert_clean_run(
            SETUP + BUILD +
            "from unittest import mock\n"
            "from ml.eval.blind.store import Store\n"
            "wrong = {r['submission_id']: 'eligible' for r in records}\n"
            "with mock.patch.object(Store, 'current_states', return_value=wrong):\n"
            "    try:\n"
            "        be.preflight(store, regression=False)\n"
            "        print('CODE:0')\n"
            "    except be.EvaluationError as exc:\n"
            "        print('CODE:%d' % exc.code)\n" + REPORT, expect_code=EXIT_STATE)

    def test_only_a_verified_frozen_corpus_triggers_the_import(self):
        result = run_subprocess(
            SETUP + BUILD +
            "before = firewall.loaded()\n"
            "code = be.main(['--root', tmp, '--actor', 'person-902', 'run'])\n"
            "after = firewall.loaded()\n"
            "print('BEFORE:' + ','.join(before))\n"
            "print('CODE:%d' % code)\n"
            "print('AFTER:' + ','.join(after))\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout.replace("\r\n", "\n")
        self.assertIn("BEFORE:\n", out)
        self.assertIn(f"CODE:{EXIT_OK}", out)
        self.assertIn("ml.assessment", out.split("AFTER:")[1])

    def test_the_lazy_boundary_is_the_only_prediction_import(self):
        source = (REPO / "ml" / "eval" / "blind_evaluation.py").read_text(encoding="utf-8")
        module_level = []
        for line in source.splitlines():
            if line.startswith(("import ", "from ")):
                module_level.append(line)
        for line in module_level:
            for banned in ("assessment", "detectors", "crisis_precheck", "validator",
                           "svi", "recommend", "predict", "checks", "redteam", "evaluate"):
                self.assertNotIn(banned, line, f"module-level import of a prediction module: {line}")
        self.assertIn("def _pipeline()", source)

    def test_the_blind_package_still_has_no_prediction_import(self):
        for path in sorted((REPO / "ml" / "eval" / "blind").glob("*.py")):
            if path.name == "firewall.py":
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip().startswith(("import ", "from ")):
                    continue
                for banned in ("assessment", "detectors", "crisis_precheck", "validator",
                               "svi", "recommend", "predict"):
                    self.assertNotIn(banned, line, f"{path.name}: {line}")


if __name__ == "__main__":
    unittest.main()
