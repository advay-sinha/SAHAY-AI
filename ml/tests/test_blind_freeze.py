"""Freeze gate, prediction firewall and evaluation-refusal tests. Stdlib only; offline.

As in ``test_blind_corpus.py``, every scenario and person here is a temporary
fixture for the TOOLING, written into a temporary directory. The miniature
corpus that this file freezes exists to prove that the gate can pass at all;
it is measured against a TEST coverage plan injected into the store, never
against the committed 180-sample plan, and it is destroyed at the end of the
test. Nothing here is, or may become, evaluation data.

The firewall tests run each command in a clean subprocess and inspect
``sys.modules`` afterwards, because this test process legitimately has the
pipeline imported by other test modules.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ml.eval.blind import firewall
from ml.eval.blind import freeze as fz
from ml.eval.blind import plan as pl
from ml.eval.blind.exit_codes import (EXIT_FREEZE_REFUSED, EXIT_NO_FROZEN_CORPUS, EXIT_OK, EXIT_SCHEMA,
                                      EXIT_USAGE)
from ml.eval.blind.store import Store
from ml.eval import blind_corpus, blind_evaluation
from ml.tests.test_blind_corpus import TEXT, TS, make_review, make_submission, person, roster

REPO = Path(__file__).resolve().parents[2]

#: A TEST plan: the same shape as the committed plan, four samples wide. It
#: exists so the gate can be driven to success in a unit test. The command line
#: never injects a plan, so a real freeze is always measured against
#: ml/eval/blind/coverage_plan_v1.json.
TEST_PLAN = {
    "schema": pl.PLAN_SCHEMA,
    "plan_version": "test-0",
    "corpus_version": "v1",
    "description": "TEST ONLY. Not a corpus target.",
    "total_min": 3,
    "no_stereotype_rule": "test",
    "languages": [{"language": "en", "script": ["latin"], "min": 3, "why": "test plan"},
                  {"language": "hi", "script": ["devanagari"], "min": 0, "why": "test plan"},
                  {"language": "hinglish", "script": ["latin"], "min": 0, "why": "test plan"}],
    "categories": [{"category": c, "min_total": 0, "min_per_language": 0, "why": "test plan"}
                   for c in pl.CATEGORY_NAMES],
    "slices": [{"slice": s, "min_total": 0, "min_per_language": 0, "why": "test plan"}
               for s in pl.SLICE_NAMES],
    "notes": ["test plan"],
}

TEXTS = [
    "I filled the form at the counter and the clerk asked me to return on Tuesday.",
    "The office was closed so I waited near the bus stop until the evening.",
    "I would like to know which window accepts the completed application form.",
    "The notice board listed three counters but only one of them was open today.",
]


def build_corpus(root, samples=3, agree=True, plan=TEST_PLAN):
    """A miniature, fully reviewed temporary corpus inside ``root``."""
    store = Store(root, "v1", plan=plan)
    store.init()
    (root / "assignments" / "v1" / "roster.json").write_text(json.dumps(roster()), encoding="utf-8")
    owner = person("person-902")
    records = []
    for i in range(samples):
        record = make_submission(i + 1, texts=[TEXTS[i % len(TEXTS)]], author="person-901")
        store.submit(record, owner, TS)
        records.append(record)
    allocation = store.save_assignment(owner, TS)
    for record in records:
        reviewers = [e["person_id"] for e in
                     next(r for r in allocation["assignments"]
                          if r["submission_id"] == record["submission_id"])["reviewers"]]
        store.import_review(make_review(record, reviewers[0]), owner, TS)
        second = make_review(record, reviewers[1]) if agree else make_review(
            record, reviewers[1], routing="Moderate", labels={"legal_urgency": True},
            evidence={"legal_urgency": ["t1"]},
            reasoning="I read this as an open procedural problem that still needs follow-up.")
        store.import_review(second, owner, TS)
    for record in records:
        if store.state_of(record["submission_id"]) == "review_complete":
            store.move(record["submission_id"], "eligible", owner, "every gate passed",
                       {"submission_id": record["submission_id"]}, TS)
    return store, records, owner


class TempRootCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


# --- freeze refusals ---------------------------------------------------------------------


class TestFreezeRefusals(TempRootCase):
    def test_freeze_refuses_with_zero_samples_and_writes_nothing(self):
        store = Store(self.root, "v1", plan=TEST_PLAN)
        store.init()
        (self.root / "assignments" / "v1" / "roster.json").write_text(json.dumps(roster()), encoding="utf-8")
        gate = fz.preconditions(store)
        self.assertFalse(gate["ok"])
        self.assertIn("coverage_plan_satisfied", {r["condition"] for r in gate["refusals"]})
        with self.assertRaises(fz.FreezeError):
            fz.freeze(store, person("person-902"), TS)
        self.assertIsNone(store.frozen_manifest())
        self.assertFalse((self.root / "frozen" / "v1" / "corpus.json").exists())

    def test_freeze_refuses_when_coverage_is_incomplete(self):
        store, _, owner = build_corpus(self.root, samples=1)
        gate = fz.preconditions(store)
        self.assertFalse(gate["ok"])
        self.assertIn("coverage_plan_satisfied", {r["condition"] for r in gate["refusals"]})

    def test_freeze_refuses_when_a_review_is_missing(self):
        store = Store(self.root, "v1", plan=TEST_PLAN)
        store.init()
        (self.root / "assignments" / "v1" / "roster.json").write_text(json.dumps(roster()), encoding="utf-8")
        owner = person("person-902")
        record = make_submission(1, texts=[TEXTS[0]], author="person-901")
        store.submit(record, owner, TS)
        allocation = store.save_assignment(owner, TS)
        first = allocation["assignments"][0]["reviewers"][0]["person_id"]
        store.import_review(make_review(record, first), owner, TS)
        gate = fz.preconditions(store)
        self.assertIn("required_reviews_exist", {r["condition"] for r in gate["refusals"]})

    def test_freeze_refuses_with_an_unresolved_conflict(self):
        store, _, _ = build_corpus(self.root, samples=3, agree=False)
        conditions = {r["condition"] for r in fz.preconditions(store)["refusals"]}
        self.assertIn("conflicts_adjudicated", conditions)

    def test_freeze_refuses_with_an_open_privacy_flag(self):
        store = Store(self.root, "v1", plan=TEST_PLAN)
        store.init()
        (self.root / "assignments" / "v1" / "roster.json").write_text(json.dumps(roster()), encoding="utf-8")
        owner = person("person-902")
        record = make_submission(1, texts=["Please call 9876543210 about the form at the counter."],
                                 author="person-901")
        store.submit(record, owner, TS)
        conditions = {r["condition"] for r in fz.preconditions(store)["refusals"]}
        self.assertIn("flags_resolved", conditions)

    def test_freeze_refuses_when_a_prediction_has_already_been_run(self):
        store, _, owner = build_corpus(self.root, samples=3)
        reports = store.path("reports")
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "evaluation-2026-09-12.json").write_text("{}", encoding="utf-8")
        conditions = {r["condition"] for r in fz.preconditions(store)["refusals"]}
        self.assertIn("no_predictions_before_freeze", conditions)

    def test_freeze_refuses_when_a_ledger_is_broken(self):
        store, _, _ = build_corpus(self.root, samples=3)
        path = store.ledger("reviews")
        lines = path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["record"]["routing"] = "Critical"
        lines[0] = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        conditions = {r["condition"] for r in fz.preconditions(store)["refusals"]}
        self.assertIn("ledgers_verify", conditions)

    def test_freeze_refuses_a_second_time_for_the_same_version(self):
        store, _, owner = build_corpus(self.root, samples=3)
        fz.freeze(store, owner, TS)
        with self.assertRaises(fz.FreezeError):
            fz.freeze(store, owner, TS)


# --- freeze success ----------------------------------------------------------------------


class TestFreezeSuccess(TempRootCase):
    def setUp(self):
        super().setUp()
        self.store, self.records, self.owner = build_corpus(self.root, samples=3)
        self.result = fz.freeze(self.store, self.owner, TS)

    def test_freeze_writes_the_five_artefacts_outside_git(self):
        for name in ("corpus", "labels", "review_manifest", "coverage_report", "freeze_manifest"):
            path = self.store.path("frozen", f"{name}.json")
            self.assertTrue(path.is_file(), name)
            self.assertTrue(str(path).startswith(str(self.root.resolve())))
        self.assertFalse((REPO / "ml" / "eval" / "blind" / "freeze_manifests" / "v1.json").exists())

    def test_the_manifest_records_hashes_counts_and_ledger_heads(self):
        manifest = self.store.frozen_manifest()
        self.assertEqual(manifest["samples"], 3)
        self.assertEqual(len(manifest["corpus_sha256"]), 64)
        self.assertEqual(set(manifest["file_sha256"]),
                         {"corpus", "labels", "review_manifest", "coverage_report"})
        self.assertEqual(set(manifest["ledger_heads"]),
                         {"submissions", "reviews", "adjudications", "states"})
        self.assertEqual(manifest["reviewers"]["reviews_total"], 6)
        self.assertFalse(manifest["exposed"])
        self.assertFalse(manifest["predictions_run"])

    def test_every_sample_moves_to_frozen(self):
        for record in self.records:
            self.assertEqual(self.store.state_of(record["submission_id"]), "frozen")

    def test_a_frozen_corpus_verifies(self):
        self.assertEqual(fz.verify_frozen(self.store), [])

    def test_a_tampered_frozen_file_fails_verification(self):
        path = self.store.path("frozen", "labels.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload[0]["routing"] = "Critical"
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")
        problems = fz.verify_frozen(self.store)
        self.assertTrue(any("labels.json" in p for p in problems))

    def test_a_truncated_ledger_fails_verification_against_the_recorded_head(self):
        path = self.store.ledger("reviews")
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        self.assertTrue(any("reviews ledger" in p for p in fz.verify_frozen(self.store)))

    def test_the_public_manifest_is_content_free(self):
        public = fz.public_manifest(self.store.frozen_manifest())
        # the explanatory note names the things it excludes, so search the data
        blob = json.dumps({k: v for k, v in public.items() if k != "note"}, ensure_ascii=False)
        for text in TEXTS:
            self.assertNotIn(text[:25], blob)
        for leak in ("person-90", "fictional-", "reasoning", "turns", "submission_id",
                     "expected_evidence", "reviews_per_human"):
            self.assertNotIn(leak, blob, f"a public manifest must not carry {leak}")
        self.assertEqual(public["samples"], 3)

    def test_the_frozen_corpus_carries_the_scenarios_and_the_labels_separately(self):
        corpus = self.store.read_frozen("corpus")
        labels = self.store.read_frozen("labels")
        self.assertEqual(len(corpus), len(labels))
        self.assertTrue(all("turns" in row for row in corpus))
        self.assertTrue(all("turns" not in row for row in labels))


# --- the prediction firewall --------------------------------------------------------------


def run_subprocess(script):
    """Run a snippet in a clean interpreter rooted at the repository."""
    return subprocess.run([sys.executable, "-c", script], cwd=str(REPO), capture_output=True,
                          text=True, timeout=180)


class TestPredictionFirewall(unittest.TestCase):
    def test_the_forbidden_list_names_the_pipeline(self):
        for name in ("ml.assessment", "ml.nlp.detectors", "ml.guardrails.crisis_precheck",
                     "ml.guardrails.validator", "ml.svi.engine", "ml.nlp.recommend", "ml.eval.predict"):
            self.assertIn(name, firewall.FORBIDDEN_MODULES)

    def test_importing_the_tooling_loads_no_prediction_module(self):
        result = run_subprocess(
            "import ml.eval.blind_corpus, ml.eval.blind_evaluation\n"
            "from ml.eval.blind import firewall\n"
            "print('LOADED:' + ','.join(firewall.loaded()))\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOADED:\n", result.stdout.replace("\r\n", "\n"))

    def test_the_authoring_commands_load_no_prediction_module(self):
        script = (
            "import json, tempfile, sys\n"
            "from pathlib import Path\n"
            "from ml.eval import blind_corpus\n"
            "from ml.eval.blind import firewall\n"
            "sys.path.insert(0, '.')\n"
            "from ml.tests.test_blind_corpus import make_submission, make_review, person, roster, TS\n"
            "tmp = tempfile.mkdtemp()\n"
            "root = Path(tmp)\n"
            "blind_corpus.main(['--root', tmp, 'init'])\n"
            "(root / 'assignments' / 'v1' / 'roster.json').write_text(json.dumps(roster()),"
            " encoding='utf-8')\n"
            "s = make_submission(1)\n"
            "f = root / 'sub.json'\n"
            "f.write_text(json.dumps(s), encoding='utf-8')\n"
            "blind_corpus.main(['--root', tmp, 'validate-submission', str(f)])\n"
            "blind_corpus.main(['--root', tmp, 'submit', str(f), '--actor', 'person-902'])\n"
            "blind_corpus.main(['--root', tmp, 'assign', '--actor', 'person-902'])\n"
            "blind_corpus.main(['--root', tmp, 'export-review', '--actor', 'person-902'])\n"
            "blind_corpus.main(['--root', tmp, 'status'])\n"
            "blind_corpus.main(['--root', tmp, 'coverage'])\n"
            "blind_corpus.main(['--root', tmp, 'verify-ledgers'])\n"
            "blind_corpus.main(['--root', tmp, 'freeze', '--actor', 'person-902', '--dry-run'])\n"
            "print('LOADED:' + ','.join(firewall.loaded()))\n")
        result = run_subprocess(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LOADED:\n", result.stdout.replace("\r\n", "\n"))

    def test_the_evaluation_refusal_loads_no_prediction_module(self):
        script = (
            "import tempfile, json, sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, '.')\n"
            "from ml.eval import blind_corpus, blind_evaluation\n"
            "from ml.eval.blind import firewall\n"
            "from ml.tests.test_blind_corpus import roster\n"
            "tmp = tempfile.mkdtemp()\n"
            "blind_corpus.main(['--root', tmp, 'init'])\n"
            "(Path(tmp) / 'assignments' / 'v1' / 'roster.json').write_text("
            "json.dumps(roster()), encoding='utf-8')\n"
            "code = blind_evaluation.main(['--root', tmp, '--actor', 'person-902', 'run'])\n"
            "print('CODE:%d' % code)\n"
            "print('LOADED:' + ','.join(firewall.loaded()))\n")
        result = run_subprocess(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout.replace("\r\n", "\n")
        self.assertIn(f"CODE:{EXIT_NO_FROZEN_CORPUS}", out)
        self.assertIn("LOADED:\n", out)

    def test_assert_clean_raises_when_the_pipeline_is_loaded(self):
        result = run_subprocess(
            "import ml.assessment\n"
            "from ml.eval.blind import firewall\n"
            "try:\n"
            "    firewall.assert_clean('test')\n"
            "    print('NOT RAISED')\n"
            "except firewall.FirewallError as exc:\n"
            "    print('RAISED')\n")
        self.assertIn("RAISED", result.stdout)
        self.assertNotIn("NOT RAISED", result.stdout)

    def test_no_blind_module_imports_a_prediction_module_in_its_source(self):
        blind = REPO / "ml" / "eval" / "blind"
        offenders = []
        for path in sorted(blind.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped.startswith(("import ", "from ")):
                    continue
                for bad in ("assessment", "detectors", "crisis_precheck", "validator",
                            "svi", "recommend", "predict"):
                    if bad in stripped and "firewall" not in path.name:
                        offenders.append(f"{path.name}: {stripped}")
        self.assertEqual(offenders, [])


# --- evaluation --------------------------------------------------------------------------


class TestEvaluationRefusal(TempRootCase):
    """The refusals that matter before a corpus exists.

    The measurement path itself, and every post-freeze behaviour, is covered by
    ``ml/tests/test_blind_evaluation.py``.
    """

    def with_roster(self):
        store = Store(self.root, "v1")
        store.init()
        (self.root / "assignments" / "v1" / "roster.json").write_text(
            json.dumps(roster()), encoding="utf-8")
        return store

    def test_run_refuses_without_a_frozen_corpus(self):
        self.with_roster()
        code = blind_evaluation.main(["--root", str(self.root), "--actor", "person-902", "run"])
        self.assertEqual(code, EXIT_NO_FROZEN_CORPUS)

    def test_run_refuses_without_a_named_actor(self):
        self.with_roster()
        self.assertEqual(blind_evaluation.main(["--root", str(self.root), "run"]), EXIT_USAGE)

    def test_status_reports_no_official_metrics(self):
        Store(self.root, "v1").init()
        code = blind_evaluation.main(["--root", str(self.root), "status"])
        self.assertEqual(code, EXIT_NO_FROZEN_CORPUS)

    def test_the_report_sections_are_fixed_in_advance(self):
        for section in ("detector_metrics", "by_language", "by_category", "by_challenge_slice",
                        "label_slices", "critical_misses", "false_escalations", "abstention",
                        "evidence_link_validity", "svi_distribution", "determinism",
                        "scenario_replay", "guardrail_prohibition_coverage"):
            self.assertIn(section, blind_evaluation.REQUIRED_SECTIONS)

    def test_a_frozen_corpus_can_be_evaluated(self):
        store, _, owner = build_corpus(self.root, samples=3)
        fz.freeze(store, owner, TS)
        code = blind_evaluation.main(["--root", str(self.root), "--actor", "person-902", "run"])
        self.assertEqual(code, EXIT_OK)


# --- command line ------------------------------------------------------------------------


class TestCommandLine(TempRootCase):
    def setUp(self):
        super().setUp()
        Store(self.root, "v1").init()
        (self.root / "assignments" / "v1" / "roster.json").write_text(json.dumps(roster()), encoding="utf-8")

    def write(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_exit_codes_are_documented_and_distinct(self):
        self.assertEqual(blind_corpus.main(["exit-codes"]), EXIT_OK)

    def test_an_unset_root_is_a_configuration_error(self):
        self.assertEqual(blind_corpus.main(["--root", "", "--version", "v1", "status"]), EXIT_USAGE)

    def test_a_schema_failure_returns_the_schema_code(self):
        broken = make_submission()
        broken["turns"][0]["text"] = TEXT["en2"]
        code = blind_corpus.main(["--root", str(self.root), "validate-submission",
                                  self.write("broken.json", broken)])
        self.assertEqual(code, EXIT_SCHEMA)

    def test_a_clean_submission_validates_with_success(self):
        code = blind_corpus.main(["--root", str(self.root), "validate-submission",
                                  self.write("ok.json", make_submission(texts=[TEXTS[0]]))])
        self.assertEqual(code, EXIT_OK)

    def test_freeze_dry_run_refuses_on_an_empty_corpus(self):
        code = blind_corpus.main(["--root", str(self.root), "freeze", "--actor", "person-902", "--dry-run"])
        self.assertEqual(code, EXIT_FREEZE_REFUSED)

    def test_a_path_outside_the_root_is_refused(self):
        store = Store(self.root, "v1")
        with self.assertRaises(Exception):
            store.path("frozen", "..", "..", "escape.json")


if __name__ == "__main__":
    unittest.main()
