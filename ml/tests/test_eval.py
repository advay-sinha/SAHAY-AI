"""Evaluation framework tests. Standard library unittest; fast (no report files).

Covers the label schema, the corpora, split discipline, metric arithmetic
(including undefined metrics), slicing, evidence links, critical-miss and
false-escalation counting, abstention, D4 handling, SVI sensitivity,
determinism, replay, LLM-off completion, guardrail coverage, prompt-injection
resistance and the no-model/no-network default path.
"""

import copy
import json
import unittest
from pathlib import Path

from ml.assessment import assess
from ml.eval import checks, redteam, svi_sensitivity
from ml.eval.build_corpus import main as build_corpus_main
from ml.eval.evaluate import evaluate
from ml.eval.metrics import binary_metrics, confusion, critical_event_miss_rate, fmt, precision_recall_f1
from ml.eval.schema import (
    CATEGORIES,
    disjoint,
    identifying_data,
    lock_eligible,
    real_approvals,
    validate_corpus,
    validate_sample,
)
from ml.svi import compute

CORPUS = Path(__file__).resolve().parents[1] / "eval" / "corpus"


def load(name):
    return json.loads((CORPUS / name).read_text(encoding="utf-8"))


DEV, CAND, LOCKED, RT = load("dev.json"), load("candidates.json"), load("locked.json"), load("redteam.json")

#: The recorded red-team failures (fixture ids). A NEW failure fails this suite;
#: fixing one means removing it here in the same change, with the evidence.
#: 2026-09-11 safety hardening: all 19 baseline failures (ml/eval/contamination.py
#: REDTEAM_KNOWN_FAILURES) now pass as REGRESSIONS; see
#: ml/eval/results/safety-hardening-2026-09-11.md for before/after.
KNOWN_REDTEAM_FAILURES = set()


def sample(text="They threatened us.", **over):
    s = copy.deepcopy(DEV["samples"][0])
    s.update({"id": "DEV-EN-900", "turns": [{"id": "t1", "speaker": "victim", "state": "S1", "text": text}]})
    s["labels"] = {c: False for c in CATEGORIES}
    s["expected_evidence"] = {}
    s["expected"] = {"crisis_precheck": False, "routed_critical": False, "abstain": None, "band": None}
    s["review"] = {"status": "author_draft", "required_reviews": 1,
                   "reviewers": [{"reviewer": "TODO-reviewer-1", "decision": "pending", "date": None}]}
    s.update(over)
    return s


class TestLabelSchema(unittest.TestCase):
    def test_committed_corpora_are_valid(self):
        for corpus in (DEV, CAND, LOCKED):
            self.assertEqual(validate_corpus(corpus), [], corpus["split"])

    def test_committed_corpora_are_not_stale(self):
        self.assertEqual(build_corpus_main(["--check"]), 0)

    def test_missing_and_unknown_keys_are_errors(self):
        s = sample()
        del s["notes"]
        self.assertTrue(any("missing keys" in e for e in validate_sample(s)))
        s = sample(extra=1)
        self.assertTrue(any("unknown keys" in e for e in validate_sample(s)))

    def test_evidence_must_name_a_victim_turn_of_a_positive_label(self):
        s = sample()
        s["labels"]["continuing_threat"] = True
        s["expected_evidence"] = {"continuing_threat": ["t9"]}
        self.assertTrue(any("not a victim turn" in e for e in validate_sample(s)))
        s["expected_evidence"] = {}
        self.assertTrue(any("needs expected_evidence" in e for e in validate_sample(s)))

    def test_a_critical_label_must_expect_critical_routing(self):
        s = sample("I want to die.")
        s["labels"]["crisis_self_harm"] = True
        s["expected_evidence"] = {"crisis_self_harm": ["t1"]}
        errs = validate_sample(s)
        self.assertTrue(any("pre-check to fire" in e for e in errs))
        self.assertTrue(any("routed_critical" in e for e in errs))

    def test_languages_and_ids_are_checked(self):
        self.assertTrue(validate_sample(sample(language="fr")))
        self.assertTrue(any("id language code" in e for e in validate_sample(sample(language="hi"))))


class TestReviewRules(unittest.TestCase):
    def crisis(self, reviewers, status="approved", split="locked"):
        s = sample("I want to die.", split=split, id="LOCK-EN-900" if split == "locked" else "CAND-EN-900")
        s["labels"]["crisis_self_harm"] = True
        s["expected_evidence"] = {"crisis_self_harm": ["t1"]}
        s["expected"] = {"crisis_precheck": True, "routed_critical": True, "abstain": None, "band": "Critical"}
        s["review"] = {"status": status, "required_reviews": 2, "reviewers": reviewers}
        return s

    def test_placeholders_never_count_as_approvals(self):
        s = self.crisis([{"reviewer": "TODO-reviewer-1", "decision": "pending", "date": None},
                         {"reviewer": "TODO-reviewer-2", "decision": "pending", "date": None}])
        self.assertEqual(real_approvals(s), 0)
        self.assertFalse(lock_eligible(s))
        self.assertTrue(any("not lock-eligible" in e for e in validate_sample(s)))

    def test_a_placeholder_cannot_approve(self):
        s = self.crisis([{"reviewer": "TODO-reviewer-1", "decision": "approve", "date": "2026-09-11"}])
        self.assertTrue(any("placeholder reviewer can only be pending" in e for e in validate_sample(s)))

    def test_critical_samples_need_two_distinct_real_approvals(self):
        one = [{"reviewer": "reviewer-a", "decision": "approve", "date": "2026-09-11"}]
        self.assertFalse(lock_eligible(self.crisis(one)))
        same_twice = one + [{"reviewer": "reviewer-a", "decision": "approve", "date": "2026-09-12"}]
        self.assertFalse(lock_eligible(self.crisis(same_twice)))
        two = one + [{"reviewer": "reviewer-b", "decision": "approve", "date": "2026-09-12"}]
        self.assertTrue(lock_eligible(self.crisis(two)))
        self.assertEqual(validate_sample(self.crisis(two)), [])

    def test_critical_candidates_are_pending_review_and_none_are_locked(self):
        self.assertEqual(LOCKED["samples"], [])
        for s in CAND["samples"]:
            self.assertEqual(s["review"]["status"], "pending_review", s["id"])
            self.assertEqual(real_approvals(s), 0, s["id"])


class TestCorpusSafety(unittest.TestCase):
    def test_splits_are_disjoint(self):
        self.assertEqual(disjoint([DEV, CAND, LOCKED]), [])
        dup = copy.deepcopy(CAND)
        dup["samples"][0]["turns"][0]["text"] = DEV["samples"][0]["turns"][0]["text"]
        self.assertTrue(disjoint([DEV, dup]))

    def test_no_identifying_data_in_any_fixture(self):
        self.assertEqual(identifying_data(DEV["samples"] + CAND["samples"]), [])
        planted = [sample("Call me on 9876543210 or mail a@b.in"), sample("PIN 110001, FIR no 123")]
        hits = identifying_data(planted)
        self.assertTrue(any(h.endswith(":phone") for h in hits))
        self.assertTrue(any(h.endswith(":email") for h in hits))
        self.assertTrue(any(h.endswith(":fir_number") for h in hits))

    def test_every_language_and_required_scenario_is_covered(self):
        tags = {t for s in DEV["samples"] + CAND["samples"] for t in s["tags"]}
        for tag in ("immediate_danger", "crisis", "threat_after_complaint", "medical", "boycott_displacement",
                    "coercion", "legal_question", "low_distress", "negated_crisis", "quoted_crisis",
                    "human_request", "code_switch", "misspelling", "regional_variant", "weak_indicators",
                    "conflicting_reassurance", "advice_seeking", "diagnosis_request", "minimising_blaming",
                    "roleplay", "embedded_instruction", "prompt_injection"):
            self.assertIn(tag, tags)
        for corpus in (DEV, CAND):
            self.assertEqual({s["language"] for s in corpus["samples"]}, {"hi", "en", "hinglish"})


class TestMetrics(unittest.TestCase):
    def test_confusion_and_rates(self):
        c = confusion([(True, True), (True, False), (False, True), (False, False), (False, False)])
        self.assertEqual((c["tp"], c["fn"], c["fp"], c["tn"], c["n"]), (1, 1, 1, 2, 5))
        m = binary_metrics(c)
        self.assertEqual((m["precision"], m["recall"], m["f1"]), (0.5, 0.5, 0.5))
        self.assertEqual(m["specificity"], round(2 / 3, 4))

    def test_zero_denominators_are_undefined_not_perfect(self):
        m = binary_metrics(confusion([(False, False), (False, False)]))
        self.assertIsNone(m["precision"])
        self.assertIsNone(m["recall"])
        self.assertIsNone(m["f1"])
        self.assertEqual(m["recall_denominator"], 0)
        self.assertEqual(fmt(m["recall"]), "n/a")
        self.assertEqual(precision_recall_f1(0, 0, 0), {"precision": None, "recall": None, "f1": None})

    def test_defined_zero_is_a_real_zero(self):
        m = binary_metrics(confusion([(True, False), (False, True)]))
        self.assertEqual((m["precision"], m["recall"], m["f1"]), (0.0, 0.0, 0.0))

    def test_critical_miss_rate(self):
        self.assertIsNone(critical_event_miss_rate([(False, False)])["miss_rate"])
        r = critical_event_miss_rate([(True, True), (True, False), (False, True)])
        self.assertEqual((r["critical_events"], r["missed"], r["miss_rate"]), (2, 1, 0.5))


class TestEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = evaluate(DEV["samples"])

    def test_counts_and_language_slices(self):
        self.assertEqual(self.dev["sample_count"], len(DEV["samples"]))
        self.assertEqual(sum(self.dev["language_counts"].values()), len(DEV["samples"]))
        for lang, block in self.dev["per_language"].items():
            self.assertEqual(block["n"], self.dev["language_counts"][lang])
        self.assertGreater(self.dev["per_language"]["hinglish"]["n"], 0)

    def test_negation_and_quotation_slices(self):
        n = sum(s["labels"]["negated_risk_language"] for s in DEV["samples"])
        q = sum(s["labels"]["quoted_attributed_risk"] for s in DEV["samples"])
        self.assertEqual(self.dev["slices"]["negation"]["n"], n)
        self.assertEqual(self.dev["slices"]["quotation_attribution"]["n"], q)
        # No negated-only sample may be routed Critical.
        self.assertEqual(self.dev["slices"]["negation"]["routing"]["false_escalations"], [])

    def test_every_positive_cites_valid_evidence(self):
        ev = self.dev["evidence"]
        self.assertEqual(ev["invalid"], [])
        self.assertEqual(ev["cited_validity"], 1.0)
        self.assertEqual(ev["positive_evidence_validity"], 1.0)

    def test_not_implemented_detector_is_excluded_not_scored(self):
        self.assertIn("excluded", self.dev["detectors"]["explicit_human_request"])

    def test_critical_misses_and_false_escalations_are_counted(self):
        miss = sample("I want to disappear forever.", labels=dict({c: False for c in CATEGORIES}, crisis_self_harm=True),
                      expected_evidence={"crisis_self_harm": ["t1"]},
                      expected={"crisis_precheck": True, "routed_critical": True, "abstain": None, "band": "Critical"})
        escalate = sample('The actor said "I want to die" in the film.', id="DEV-EN-901")
        r = evaluate([miss, escalate])["routing"]
        self.assertEqual([m["id"] for m in r["critical_misses"]], ["DEV-EN-900"])
        self.assertEqual(len(r["false_escalations"]), 1)
        self.assertEqual(r["critical_event_miss_rate"]["miss_rate"], 1.0)

    def test_abstention_coverage(self):
        ab = self.dev["abstention"]
        self.assertEqual(ab["missed_abstentions"], [])
        self.assertIsNotNone(ab["abstention_coverage"])

    def test_d4_is_never_a_value_and_voice_abstains(self):
        self.assertEqual(self.dev["d4"]["problems"], [])
        voice = [s for s in DEV["samples"] if s["channel"] == "mobile_voice"]
        self.assertTrue(voice)
        for s in voice:
            self.assertTrue(self.dev["predictions"][s["id"]]["abstained"], s["id"])

    def test_no_diagnostic_vocabulary_in_anything_the_system_writes(self):
        """System-authored strings only: the victim's own words (kept verbatim in
        the structured record and matched terms) may contain anything."""
        banned = ("ptsd", "depress", "disorder", "diagnos", "psychiatric", "mentally ill", "anxiety")
        for s in DEV["samples"] + CAND["samples"]:
            r = assess(s["turns"], True, channel=s["channel"])
            written = [r["cause"], json.dumps(r["uncertainty"], ensure_ascii=False)]
            written += [str(b["label"]) for b in r["breakdown"]]
            written += [str(d.get("basis")) for d in r["dims"].values()]
            written += [f"{x['label']} {x['rationale']}" for x in r["recommendations"]]
            written += [a["type"] for a in r["alerts"]] + list(r["abstention_reasons"])
            blob = " ".join(written).casefold()
            for word in banned:
                self.assertNotIn(word, blob, s["id"])


class TestSafetyInvariants(unittest.TestCase):
    def test_no_rescaling_after_runtime_or_quality_failure(self):
        s = {d: 60.0 for d in ("D1", "D2", "D3", "D5", "D6", "D7", "D8", "D9")}
        c = {d: 0.9 for d in s}
        for q in ({"acoustic_not_measured": True}, {"poor_audio": True}):
            r = compute(s, c, q)
            self.assertIsNone(r["band"], q)
            self.assertEqual(r["weight_denominator"], 1.0, q)
            self.assertEqual(r["structurally_unavailable"], [], q)

    def test_quoted_crisis_is_routed_but_recorded_as_attributed(self):
        turns = [{"id": "t1", "speaker": "victim", "state": "S1",
                  "text": "He told me to go kill myself if I don't take the complaint back."}]
        d2 = assess(turns, True, channel="mobile_chat")["dims"]["D2"]
        self.assertEqual(d2["score"], 100.0)  # recall first: a person sees it
        self.assertEqual(d2["basis"], "crisis_precheck_attributed")
        self.assertEqual(d2["attributed_turn_ids"], ["t1"])
        self.assertIn("kill myself", d2["matched_terms"])

    def test_first_person_crisis_elsewhere_is_not_marked_attributed(self):
        turns = [{"id": "t1", "speaker": "victim", "state": "S1", "text": "He said nothing to us."},
                 {"id": "t2", "speaker": "victim", "state": "S1", "text": "I want to die."}]
        d2 = assess(turns, True, channel="mobile_chat")["dims"]["D2"]
        self.assertEqual(d2["basis"], "crisis_precheck")
        self.assertEqual(d2["attributed_turn_ids"], [])


class TestSviSensitivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = svi_sensitivity.run()

    def test_boundaries_below_at_and_above(self):
        rows = self.r["band_boundaries"]
        by = {row["input"]: row["band"] for row in rows}
        self.assertEqual((by[29.99], by[30.0], by[30.01]), ("Low", "Moderate", "Moderate"))
        self.assertEqual((by[54.99], by[55.0]), ("Moderate", "High"))
        self.assertEqual((by[74.99], by[75.0]), ("High", "Critical"))

    def test_overrides_trigger_exactly_at_threshold_and_confidence(self):
        for row in self.r["hard_overrides"]:
            if "dimension" in row:
                fires = row["score"] >= 70.0 and row["confidence"] >= 0.6
                self.assertEqual(row["band"] == "Critical", fires, row)
            else:
                self.assertEqual(row["band"], "Critical", row)

    def test_four_kinds_of_missing_evidence_stay_distinct(self):
        rows = {row["case"].split(" ")[0]: row for row in self.r["evidence_kinds"]}
        self.assertEqual(rows["structurally_unavailable"]["weight_denominator"], 0.88)
        self.assertIsNone(rows["missing_by_failure"]["band"])
        self.assertIn("acoustic_not_measured", rows["missing_by_failure"]["abstention_reasons"])
        self.assertIsNone(rows["low_confidence"]["band"])
        self.assertEqual(rows["measured_low"]["weight_denominator"], 1.0)
        self.assertIsNotNone(rows["measured_low"]["band"])

    def test_future_threat_ceiling_and_floor(self):
        self.assertTrue(all(not row["reaches_override"] for row in self.r["future_threat_ceiling"]))
        floor = self.r["abstention_floor"]
        self.assertIsNone(floor[0]["band"])
        self.assertIsNotNone(floor[1]["band"])

    def test_weights_sensitivity_matches_the_normalised_weights(self):
        for row in self.r["weights"]:
            if row["dimension"] != "D4":
                self.assertAlmostEqual(row["text_delta_per_10_points"], 10 * row["weight"] / 0.88, places=1)

    def test_deterministic_and_explained(self):
        self.assertTrue(self.r["determinism"]["identical"])
        self.assertTrue(self.r["determinism"]["explanation_matches_svi"])


class TestReproducibility(unittest.TestCase):
    def test_evaluation_is_deterministic(self):
        small = DEV["samples"][:12]
        self.assertTrue(checks.determinism(lambda: evaluate(small))["identical"])

    def test_scenario_replay_is_consistent(self):
        r = checks.scenario_replay(DEV["samples"] + CAND["samples"])
        self.assertGreater(r["multi_turn_samples"], 0)
        self.assertEqual(r["inconsistent"], [])

    def test_dialogue_completes_with_the_llm_off(self):
        r = checks.llm_off()
        self.assertTrue(r["completed"], r["problems"])
        for path in r["walks"].values():
            self.assertTrue(path[-1].startswith("S9"))

    def test_default_path_needs_no_model_and_no_network(self):
        with checks.offline() as report:
            evaluate(DEV["samples"][:5])
            redteam.run(RT)
        self.assertTrue(report["ok"], report)
        self.assertEqual(checks.static_imports(Path(__file__).resolve().parents[1])["offenders"], [])

    def test_network_is_really_blocked_inside_the_guard(self):
        import socket

        with checks.offline() as report:
            with self.assertRaises(checks.NetworkBlocked):
                socket.create_connection(("example.invalid", 80))
        self.assertFalse(report["ok"])


class TestGuardrailRedTeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = redteam.run(RT)

    def test_every_prohibition_is_covered_in_both_languages(self):
        cov = redteam.prohibition_coverage()
        self.assertEqual(cov["with_both_languages"], cov["prohibitions"])
        for reason, row in cov["rows"].items():
            self.assertEqual(row["coverage"], 1.0, reason)

    def test_known_failures_are_exactly_the_recorded_ledger(self):
        failing = {f["id"] for f in self.r["failures"]}
        self.assertEqual(failing - KNOWN_REDTEAM_FAILURES, set(), "new red-team failure")
        self.assertEqual(KNOWN_REDTEAM_FAILURES - failing, set(),
                         "a recorded failure now passes: remove it from the ledger with the evidence")

    def test_victim_text_cannot_control_routing_or_the_dialogue(self):
        for res in self.r["results"]:
            if res["kind"] == "victim_input":
                self.assertTrue(res["passed"], f"{res['id']}: {res['actual']}")

    def test_every_failure_carries_id_expected_actual_and_severity(self):
        for f in self.r["failures"]:
            for key in ("id", "expected", "actual", "severity"):
                self.assertTrue(f[key], (f, key))


if __name__ == "__main__":
    unittest.main()
