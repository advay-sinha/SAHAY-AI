"""Evaluation table (plan M14): pending is never zero, evidence is labelled, output is aggregate-only."""

import json
import tempfile
import unittest
from pathlib import Path

from ml import ser, textaffect
from ml.eval import table

ML = Path(__file__).resolve().parents[1]
BASELINE = ML / "eval" / "results" / "eval-baseline-2026-09-11.json"


def _block(tp, fp, fn, tn):
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": tp + fp + fn + tn,
            "recall": tp / (tp + fn) if tp + fn else None, "recall_denominator": tp + fn,
            "precision": tp / (tp + fp) if tp + fp else None, "precision_denominator": tp + fp}


def _eval_report(locked_samples=0):
    result = {
        "routing": {"critical_event_miss_rate": {"critical_events": 10, "missed": 1, "miss_rate": 0.1},
                    "critical_routing": _block(9, 1, 1, 9), "crisis_precheck": _block(5, 0, 0, 15),
                    "false_escalations": [{"id": "DEV-X"}]},
        "detectors": {"medical_need": _block(3, 0, 1, 16), "legal_status": _block(0, 0, 0, 20)},
        "abstention": {"expected_abstain": 2, "abstained_when_expected": 2},
        "bands": {"band_specified": 4, "band_agreement": 3},
        "predictions": [{"id": "DEV-X", "text": "fictional utterance"}],
    }
    return {
        "splits": {"dev": {"result": result}, "candidate": {"result": result}, "locked": {"result": None}},
        "official_locked_metrics": {"locked_samples": locked_samples},
        "redteam": {"cases": 5, "passed": 5, "failures_by_severity": {"critical": 0}},
        "versions": {"pipeline": "test"}, "timestamp": "2026-09-27T00:00:00+00:00", "git": {"commit": "abc"},
    }


def _write_private_root(root: Path, reported_uar: float) -> None:
    run = root / "ser" / "runs" / "toy-both-s1"
    run.mkdir(parents=True)
    gold = ["neutral", "happy", "sad", "angry", "fearful"] * 4
    preds = [{"clip_id": f"c{i}", "split": "test", "dataset": "toy", "gold": g,
              "probs": [1.0 if c == g else 0.0 for c in table.AFFECT_CLASSES]} for i, g in enumerate(gold)]
    (run / "predictions-default.jsonl").write_text("\n".join(json.dumps(p) for p in preds), encoding="utf-8")
    (run / "report.json").write_text(json.dumps({"variants": {"default": {"scores": {
        "test:toy": {"uar": reported_uar, "n": 20, "evidence_class": "acted_corpus_actor_disjoint"},
        "val": {"uar": 0.5, "n": 3}}}}}), encoding="utf-8")


class TestRows(unittest.TestCase):
    def test_measured_needs_a_value_and_pending_has_none(self):
        with self.assertRaises(ValueError):
            table.row("M1", "x", scope="s", status="measured", evidence_class="e", source="f")
        with self.assertRaises(ValueError):
            table.row("M2", "x", scope="s", status="pending", evidence_class="e", source="f", value=0.0)
        with self.assertRaises(ValueError):
            table.row("M2", "x", scope="s", status="guessed", evidence_class="e", source="f")

    def test_unmeasured_handover_metrics_are_pending_not_zero(self):
        built = table.build(None, "none", None)
        by_id = {r["metric_id"]: r for r in built["rows"]}
        for mid in ("M1", "M2", "M3", "M4", "M5", "M6", "M9"):
            self.assertEqual(by_id[mid]["status"], "pending", mid)
            self.assertIsNone(by_id[mid]["value"], mid)
        self.assertEqual(by_id["M8"]["status"], "test_enforced")
        self.assertIsNone(by_id["M8"]["value"])
        self.assertEqual(by_id["D4"]["status"], "unvalidated")
        self.assertIn("**pending**", table.render_markdown(built))

    def test_every_row_names_its_source_and_evidence(self):
        for r in table.build(_eval_report(), "eval.json", None)["rows"]:
            self.assertTrue(r["source"], r)
            self.assertTrue(r["evidence_class"], r)


class TestEvalRows(unittest.TestCase):
    def setUp(self):
        self.rows = table.build(_eval_report(), "eval.json", None)["rows"]

    def test_exposed_splits_are_labelled_exposed(self):
        m1 = [r for r in self.rows if r["metric_id"] == "M1"]
        self.assertEqual({r["scope"]: r["evidence_class"] for r in m1},
                         {"dev": "exposed_development", "candidate": "exposed_candidate", "locked": "locked"})
        rt = next(r for r in self.rows if r["metric_id"] == "M5")
        self.assertEqual(rt["evidence_class"], "exposed_redteam")

    def test_locked_is_pending_while_empty(self):
        locked = next(r for r in self.rows if r["metric_id"] == "M1" and r["scope"] == "locked")
        self.assertEqual(locked["status"], "pending")
        self.assertIsNone(locked["value"])

    def test_miss_rate_and_interval(self):
        dev = next(r for r in self.rows if r["metric_id"] == "M1" and r["scope"] == "dev")
        self.assertEqual(dev["value"], 0.1)
        self.assertEqual(dev["n"], 10)
        lo, hi = dev["ci95"]
        self.assertLess(lo, 0.1)
        self.assertGreater(hi, 0.1)

    def test_detector_without_positives_is_pending(self):
        legal = [r for r in self.rows if r["metric"].endswith("legal_status") and r["scope"] == "dev"]
        self.assertEqual({r["status"] for r in legal}, {"pending"})
        self.assertTrue(all(r["value"] is None for r in legal))

    def test_no_row_level_content_reaches_the_output(self):
        built = table.build(_eval_report(), "eval.json", None)
        dumped = json.dumps(built) + table.render_markdown(built)
        self.assertNotIn("fictional utterance", dumped)
        self.assertNotIn("DEV-X", dumped)
        with self.assertRaises(ValueError):
            table.check_aggregate_only({"rows": [{"text": "x"}]})


class TestWording(unittest.TestCase):
    def test_banned_claims_are_refused(self):
        for phrase in ("Clinically validated model", "production accuracy 0.9", "state-of-the-art"):
            with self.assertRaises(table.WordingError):
                table.check_wording(phrase, 5)

    def test_official_only_with_a_locked_set(self):
        with self.assertRaises(table.WordingError):
            table.check_wording("Official miss rate", 0)
        table.check_wording("Official miss rate", 3)

    def test_rendered_table_passes_the_guard(self):
        built = table.build(_eval_report(), "eval.json", None)
        table.check_wording(table.render_markdown(built), built["locked_samples"])


class TestStatistics(unittest.TestCase):
    def test_wilson_bounds(self):
        self.assertIsNone(table.wilson(0, 0))
        lo, hi = table.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=3)

    def test_uar_and_bootstrap_are_deterministic(self):
        gold = ["neutral", "sad", "sad", "angry"] * 5
        pred = ["neutral", "sad", "neutral", "angry"] * 5
        self.assertAlmostEqual(table.uar(gold, pred), (1 + 0.5 + 1) / 3)
        a = table.bootstrap_uar(gold, pred, 200, 13)
        self.assertEqual(a, table.bootstrap_uar(gold, pred, 200, 13))
        self.assertLessEqual(a[0], a[1])

    def test_class_order_matches_the_model_packages(self):
        self.assertEqual(table.AFFECT_CLASSES, ser.AFFECT_CLASSES)
        self.assertEqual(table.AFFECT_CLASSES, textaffect.AFFECT_CLASSES)


class TestPrivateReports(unittest.TestCase):
    def test_missing_root_is_not_available(self):
        rows = table.private_rows(None, 10, 1) + table.private_rows("Z:/does/not/exist", 10, 1)
        self.assertEqual({r["status"] for r in rows}, {"not_available"})
        self.assertTrue(all(r["value"] is None for r in rows))

    def test_interval_when_predictions_reproduce_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_private_root(Path(tmp), 1.0)
            rows = [r for r in table.private_rows(tmp, 50, 1) if r["metric_id"] == "SER"]
        self.assertEqual(len(rows), 1)  # validation scores are not reported
        self.assertEqual(rows[0]["scope"], "test:toy")
        self.assertEqual(rows[0]["ci95"], [1.0, 1.0])
        self.assertEqual(rows[0]["evidence_class"], "acted_corpus_actor_disjoint")

    def test_interval_omitted_when_predictions_disagree(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_private_root(Path(tmp), 0.61)
            row = next(r for r in table.private_rows(tmp, 50, 1) if r["metric_id"] == "SER")
        self.assertIsNone(row["ci95"])
        self.assertEqual(row["value"], 0.61)
        self.assertIn("does not reproduce", row["note"])


class TestStageWRows(unittest.TestCase):
    def _report(self):
        weak = {"tp": 8, "fn": 2, "fp": 1, "tn": 9, "precision": 0.889, "recall": 0.8, "auroc": 0.9}
        rules = {"tp": 1, "fn": 9, "fp": 0, "tn": 10, "precision": 1.0, "recall": 0.1}
        exposed = {"samples": 57, "model": {"micro_f1": 0.6}, "rules": {"micro_f1": 0.93},
                   "caught_by_model_only": ["DEV-X:crisis_self_harm"], "model_false_positives": ["DEV-Y:legal_urgency"]}
        run = {"arm": "W2", "seed": 13,
               "holdout": {"records": 100, "macro": {"f1": 0.7, "f1_labels_excluded_undefined": []},
                           "crisis_recall_by_language": {"en": 0.9, "hi": None}},
               "weak_test": {"crisis_self_harm": {"model": weak, "rules": rules}},
               "exposed": {"dev": exposed, "candidates": exposed},
               "probes": {"rows": [{"indirect_by_author": True, "model_fires": True, "crisis_precheck_fires": False},
                                   {"indirect_by_author": False, "model_fires": True, "crisis_precheck_fires": False}]}}
        return {"selected": {"arm": "W2", "seed": 13}, "runs": [run, dict(run, seed=42)]}

    def test_selected_run_rows_carry_their_evidence_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stage-w" / "reports" / "evaluation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self._report()), encoding="utf-8")
            rows = table.stage_w_rows(Path(tmp))
        classes = {r["evidence_class"] for r in rows}
        self.assertEqual(classes, {"synthetic_development", "weak_supervision_from_source_label",
                                   "exposed_development", "exposed_candidate", "descriptive_probe"})
        self.assertTrue(all("W2 seed 13" in r["metric"] for r in rows))
        self.assertEqual(len([r for r in rows if "crisis recall" in r["metric"]]), 1)  # hi is None: no row, no zero
        self.assertIn("none", rows[0]["note"])
        dumped = json.dumps(rows)
        self.assertNotIn("DEV-X", dumped)

    def test_missing_report_is_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            (row,) = table.stage_w_rows(Path(tmp))
        self.assertEqual(row["status"], "not_available")
        self.assertIsNone(row["value"])


class TestCommittedBaseline(unittest.TestCase):
    def test_builds_from_a_real_run_eval_report(self):
        report = json.loads(BASELINE.read_text(encoding="utf-8"))
        built = table.build(report, BASELINE.name, None)
        markdown = table.render_markdown(built)
        dev = next(r for r in built["rows"] if r["metric_id"] == "M1" and r["scope"] == "dev")
        miss = report["splits"]["dev"]["result"]["routing"]["critical_event_miss_rate"]
        self.assertEqual(dev["n"], miss["critical_events"])
        self.assertIn("Locked-set metrics: **pending**", markdown)


if __name__ == "__main__":
    unittest.main()


class TestBaselineRows(unittest.TestCase):
    def test_missing_report_is_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            (row,) = table.baseline_rows(Path(tmp))
        self.assertEqual(row["status"], "not_available")

    def test_rows_per_arm(self):
        exposed = {"samples": 57, "model": {"micro_f1": 0.5}, "rules": {"micro_f1": 0.93}}
        run = {"arm": "LR-W0", "holdout": {"records": 10, "macro": {"f1": 0.4}},
               "weak_test": {"D5": {"n": 9, "model": {"auroc": None, "recall": 1.0}},
                             "crisis_self_harm": {"n": 9, "model": {"auroc": 0.8, "recall": 0.5}}},
               "exposed": {"dev": exposed, "candidates": exposed}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline-lr" / "reports" / "evaluation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"runs": [run]}), encoding="utf-8")
            rows = table.baseline_rows(Path(tmp))
        self.assertEqual(len(rows), 4)  # holdout, one defined AUROC, dev, candidates
        self.assertEqual({r["evidence_class"] for r in rows},
                         {"synthetic_development", "weak_supervision_from_source_label", "exposed_development",
                          "exposed_candidate"})


class TestLatencyRows(unittest.TestCase):
    REPORT = {"asr": "local_service", "server_path_p95_plus_configured_endpoint_ms": 1281.0,
              "stages_ms": {"request_total": {"n": 70, "p50": 475.7, "p95": 581.0},
                            "asr_request": {"n": 70, "p50": 463.3, "p95": 572.1},
                            "reply_path": {"n": 0}}}

    def test_measured_server_rows_and_a_pending_phone_row(self):
        rows = table.latency_rows(self.REPORT, "latency.json")
        measured = [r for r in rows if r["status"] == "measured"]
        self.assertEqual(len(measured), 5)  # 2 stages x p50/p95 + the budget line; reply_path has n = 0
        self.assertTrue(all(r["evidence_class"] == "synthetic_speech_server_side" for r in measured))
        pending = [r for r in rows if r["status"] == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertIsNone(pending[0]["value"])

    def test_build_replaces_the_static_m2_row(self):
        built = table.build(None, "none", None, latency_report=self.REPORT, latency_source="latency.json")
        m2 = [r for r in built["rows"] if r["metric_id"] == "M2"]
        self.assertTrue(any(r["status"] == "measured" for r in m2))
        self.assertFalse(any("not instrumented" in r["note"] for r in m2))
        table.check_wording(table.render_markdown(built), 0)


class TestCorpusVersions(unittest.TestCase):
    def test_v2_rows_are_tagged_and_turn_split_rows_appear(self):
        exposed = {"samples": 57, "model": {"micro_f1": 0.5}, "rules": {"micro_f1": 0.93}}
        run = {"arm": "LR-W2", "holdout": {"records": 10, "macro": {"f1": 0.4},
                                            "by_turns": {"single_turn": {"records": 8, "macro_f1": 0.5,
                                                                         "any_positive_rate": 0.6},
                                                         "multi_turn": {"records": 2, "macro_f1": 0.2,
                                                                        "any_positive_rate": 0.5}}},
               "weak_test": {}, "exposed": {"dev": exposed, "candidates": exposed}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline-lr-7b-v2" / "reports" / "evaluation.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"runs": [run]}), encoding="utf-8")
            rows = table.baseline_rows(Path(tmp), "baseline-lr-7b-v2", "7b-v2")
            all_rows = table.private_rows(tmp, 10, 1)
        self.assertTrue(all("corpus 7b-v2" in r["metric"] for r in rows))
        self.assertEqual(len([r for r in rows if "-turn records" in r["metric"]]), 2)
        self.assertTrue(any("corpus 7b-v2" in r["metric"] for r in all_rows))
