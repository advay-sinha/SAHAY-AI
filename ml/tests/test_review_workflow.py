"""Fixture review workflow and contamination-lineage tests. Stdlib only; offline.

Every record here is a TEST record written into a temporary ledger with
fictional reviewer names; nothing touches the committed ledger or locked.json.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ml.eval import contamination as ct
from ml.eval import review_workflow as rw
from ml.eval.schema import is_critical

ML = Path(__file__).resolve().parents[1]
CANDS = rw.load_candidates()
NON_CRITICAL = next(s for s in CANDS.values() if not is_critical(s))
CRITICAL = next(s for s in CANDS.values() if is_critical(s))


def rec(sample, reviewer="fictional-reviewer-a", decision="approve", **over):
    r = rw.blank_record(sample)
    r.update(reviewer=reviewer, reviewer_role="Helpline safety lead (test)", attestation=rw.ATTESTATION,
             decision=decision, timestamp="2026-09-11T10:00:00+05:30",
             reasoning="" if decision == "approve" else "Needs a closer look at the negation clause scope.")
    r.update(over)
    return r


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "fixture_reviews.jsonl"

    def tearDown(self):
        self.tmp.cleanup()


class TestExport(LedgerCase):
    def test_packets_preserve_ids_and_carry_everything_a_reviewer_needs(self):
        paths = rw.export(Path(self.tmp.name) / "packets", CANDS)
        self.assertEqual(len(paths), len(CANDS))
        p = json.loads((Path(self.tmp.name) / "packets" / f"{CRITICAL['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(p["fixture_id"], CRITICAL["id"])
        for key in ("turns", "proposed_labels", "expected", "expected_evidence", "contamination", "required_reviews"):
            self.assertIn(key, p)
        self.assertEqual(p["required_reviews"], 2)
        self.assertFalse(p["independent_evidence_possible"])
        blank = p["record_template"]
        self.assertEqual((blank["reviewer"], blank["decision"], blank["attestation"]), ("", "", ""))


class TestRecords(LedgerCase):
    def test_valid_human_record_imports_once(self):
        r = rec(NON_CRITICAL)
        rid = rw.import_record(r, self.ledger, CANDS)
        self.assertEqual(len(rw.read_ledger(self.ledger)), 1)
        with self.assertRaises(rw.ReviewError):
            rw.import_record(r, self.ledger, CANDS)
        self.assertEqual(rw.read_ledger(self.ledger)[0]["record_id"], rid)

    def test_modified_record_is_detected(self):
        rw.import_record(rec(NON_CRITICAL), self.ledger, CANDS)
        rw.import_record(rec(NON_CRITICAL, reviewer="fictional-reviewer-b"), self.ledger, CANDS)
        lines = self.ledger.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        entry = json.loads(lines[0])
        entry["record"]["decision"] = "reject"
        self.ledger.write_text(json.dumps(entry) + "\n" + lines[1] + "\n", encoding="utf-8")
        with self.assertRaisesRegex(rw.ReviewError, "record modified"):
            rw.read_ledger(self.ledger)


class TestLedgerChain(LedgerCase):
    """The ledger is a SHA-256 hash chain; every structural edit to existing entries is detected."""

    def setUp(self):
        super().setUp()
        for reviewer in ("fictional-reviewer-a", "fictional-reviewer-b", "fictional-reviewer-c"):
            rw.import_record(rec(NON_CRITICAL, reviewer=reviewer), self.ledger, CANDS)
        self.lines = self.ledger.read_text(encoding="utf-8").splitlines()
        self.head = rw.ledger_head(self.ledger)

    def write(self, lines):
        self.ledger.write_text("".join(line + "\n" for line in lines), encoding="utf-8")

    def assert_broken(self, lines, pattern):
        self.write(lines)
        with self.assertRaisesRegex(rw.ReviewError, pattern):
            rw.read_ledger(self.ledger)

    def test_chain_links_and_head(self):
        entries = rw.read_ledger(self.ledger)
        self.assertEqual([e["seq"] for e in entries], [1, 2, 3])
        self.assertEqual(entries[0]["prev_hash"], rw.GENESIS)
        for prev, cur in zip(entries, entries[1:]):
            self.assertEqual(cur["prev_hash"], prev["entry_hash"])
        self.assertEqual(self.head, f"3:{entries[-1]['entry_hash']}")

    def test_empty_and_absent_ledgers_validate(self):
        absent = Path(self.tmp.name) / "absent.jsonl"
        empty = Path(self.tmp.name) / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        for path in (absent, empty):
            self.assertEqual(rw.read_ledger(path), [])
            self.assertEqual(rw.ledger_head(path), "0:" + rw.GENESIS)
            rw.verify_head(path, "0:" + rw.GENESIS)

    def test_modification_with_recomputed_hashes_breaks_the_next_link(self):
        entry = json.loads(self.lines[0])
        entry["record"]["decision"] = "reject"
        entry["record"]["reasoning"] = "Needs a closer look at the negation clause scope."
        entry["record_id"] = rw.record_id(entry["record"])
        self.assert_broken([json.dumps(entry)] + self.lines[1:], "entry_hash")
        entry["entry_hash"] = rw.entry_hash(entry)
        self.assert_broken([json.dumps(entry)] + self.lines[1:], "prev_hash")

    def test_deletion_is_detected(self):
        self.assert_broken(self.lines[1:], "seq")                    # first entry
        self.assert_broken([self.lines[0], self.lines[2]], "seq")    # middle entry

    def test_reordering_is_detected(self):
        self.assert_broken([self.lines[1], self.lines[0], self.lines[2]], "seq")
        self.assert_broken([self.lines[0], self.lines[2], self.lines[1]], "seq")

    def test_insertion_is_detected(self):
        forged = rec(NON_CRITICAL, reviewer="fictional-reviewer-d")
        first = json.loads(self.lines[0])
        entry = {"seq": 2, "prev_hash": first["entry_hash"], "record_id": rw.record_id(forged), "record": forged}
        entry["entry_hash"] = rw.entry_hash(entry)
        self.assert_broken([self.lines[0], json.dumps(entry)] + self.lines[1:], "seq|prev_hash")
        self.assert_broken([self.lines[0], self.lines[0]] + self.lines[1:], "seq")  # replayed line

    def test_malformed_entries_are_rejected(self):
        self.assert_broken(self.lines + ["{not json"], "not valid JSON")
        legacy = json.loads(self.lines[0])
        legacy = {"record_id": legacy["record_id"], "record": legacy["record"]}
        self.assert_broken([json.dumps(legacy)], "entry fields")

    def test_import_refuses_to_extend_a_broken_chain(self):
        self.write(self.lines[1:])
        with self.assertRaises(rw.ReviewError):
            rw.import_record(rec(NON_CRITICAL, reviewer="fictional-reviewer-d"), self.ledger, CANDS)
        self.assertEqual(self.ledger.read_text(encoding="utf-8").splitlines(), self.lines[1:])

    def test_duplicate_import_remains_rejected(self):
        with self.assertRaisesRegex(rw.ReviewError, "already been imported"):
            rw.import_record(rec(NON_CRITICAL), self.ledger, CANDS)
        self.assertEqual(len(rw.read_ledger(self.ledger)), 3)

    def test_tail_truncation_needs_the_recorded_head(self):
        self.write(self.lines[:2])
        self.assertEqual(len(rw.read_ledger(self.ledger)), 2)  # a valid shorter chain, by design
        with self.assertRaisesRegex(rw.ReviewError, "truncated"):
            rw.verify_head(self.ledger, self.head)

    def test_recomputed_rewrite_needs_the_recorded_head(self):
        other = Path(self.tmp.name) / "rewritten.jsonl"
        for reviewer in ("fictional-reviewer-a", "fictional-reviewer-b", "fictional-reviewer-e"):
            rw.import_record(rec(NON_CRITICAL, reviewer=reviewer), other, CANDS)
        rw.read_ledger(other)  # internally consistent
        with self.assertRaisesRegex(rw.ReviewError, "rewritten"):
            rw.verify_head(other, self.head)
        rw.verify_head(self.ledger, self.head)
        rw.import_record(rec(NON_CRITICAL, reviewer="fictional-reviewer-f"), self.ledger, CANDS)
        rw.verify_head(self.ledger, self.head)  # appending keeps an older head valid

    def test_cli_validate_ledger_exit_codes(self):
        self.assertEqual(rw.main(["validate-ledger", "--ledger", str(self.ledger), "--expect-head", self.head]), 0)
        self.write(self.lines[:2])
        self.assertEqual(rw.main(["validate-ledger", "--ledger", str(self.ledger), "--expect-head", self.head]), 2)
        self.write([self.lines[1]])
        self.assertEqual(rw.main(["validate-ledger", "--ledger", str(self.ledger)]), 2)

    def test_placeholder_bot_and_ai_identities_are_refused(self):
        for reviewer in ("TODO-reviewer-1", "claude", "ai-assistant", "copilot", "review-bot", "gpt-helper"):
            errs = rw.validate_record(rec(NON_CRITICAL, reviewer=reviewer), CANDS)
            self.assertTrue(errs, reviewer)
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, reviewer_kind="ai"), CANDS))
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, attestation=""), CANDS))
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, reviewer_role=""), CANDS))

    def test_record_must_match_current_fixture_content_and_schema(self):
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, fixture_sha256="0" * 64), CANDS))
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, schema_version="0.9.0"), CANDS))
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, fixture_id="CAND-EN-999"), CANDS))
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, timestamp="yesterday"), CANDS))
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, decision="lgtm"), CANDS))

    def test_label_changes_need_reasoning_and_never_approve_as_is(self):
        cat = next(c for c, v in NON_CRITICAL["labels"].items() if not v)
        no_reason = rec(NON_CRITICAL, decision="needs_discussion", label_changes={cat: True}, reasoning="")
        self.assertTrue(any("reasoning" in e for e in rw.validate_record(no_reason, CANDS)))
        approve_change = rec(NON_CRITICAL, label_changes={cat: True},
                             reasoning="The label should be positive because of turn t1.")
        self.assertTrue(rw.validate_record(approve_change, CANDS))
        self.assertTrue(rw.validate_record(rec(NON_CRITICAL, decision="needs_discussion",
                                               label_changes={"not_a_category": True},
                                               reasoning="Unknown category proposed on purpose."), CANDS))
        ok = rec(NON_CRITICAL, decision="needs_discussion", label_changes={cat: True},
                 reasoning="Turn t1 meets the definition; propose a new fixture version.")
        self.assertEqual(rw.validate_record(ok, CANDS), [])

    def test_the_candidate_fixture_is_never_rewritten(self):
        before = (ML / "eval" / "corpus" / "candidates.json").read_bytes()
        cat = next(c for c, v in NON_CRITICAL["labels"].items() if not v)
        rw.import_record(rec(NON_CRITICAL, decision="needs_discussion", label_changes={cat: True},
                             reasoning="Turn t1 meets the definition; propose a new fixture version."),
                         self.ledger, CANDS)
        self.assertEqual((ML / "eval" / "corpus" / "candidates.json").read_bytes(), before)


class TestEligibility(LedgerCase):
    def status_for(self, sid):
        return rw.status(self.ledger, CANDS)["fixtures"][sid]

    def test_critical_fixture_needs_two_distinct_human_approvals(self):
        rw.import_record(rec(CRITICAL), self.ledger, CANDS)
        self.assertFalse(self.status_for(CRITICAL["id"])["review_complete"])
        rw.import_record(rec(CRITICAL, timestamp="2026-09-11T11:00:00+05:30"), self.ledger, CANDS)  # same reviewer
        self.assertEqual(self.status_for(CRITICAL["id"])["approvals"], 1)
        rw.import_record(rec(CRITICAL, reviewer="fictional-reviewer-b"), self.ledger, CANDS)
        self.assertTrue(self.status_for(CRITICAL["id"])["review_complete"])

    def test_unresolved_records_block_completion(self):
        rw.import_record(rec(NON_CRITICAL), self.ledger, CANDS)
        self.assertTrue(self.status_for(NON_CRITICAL["id"])["review_complete"])
        rw.import_record(rec(NON_CRITICAL, reviewer="fictional-reviewer-b", decision="reject"), self.ledger, CANDS)
        st = self.status_for(NON_CRITICAL["id"])
        self.assertFalse(st["review_complete"])
        self.assertTrue(any("unresolved" in r for r in st["reasons"]))

    def test_exposed_candidates_are_never_lock_eligible_even_when_reviewed(self):
        rw.import_record(rec(NON_CRITICAL), self.ledger, CANDS)
        st = self.status_for(NON_CRITICAL["id"])
        self.assertTrue(st["review_complete"])
        self.assertFalse(st["lock_eligible"])
        self.assertTrue(any("independent locked evidence" in r for r in st["reasons"]))
        self.assertEqual(rw.status(self.ledger, CANDS)["lock_eligible"], [])

    def test_workflow_never_writes_the_locked_set(self):
        locked = ML / "eval" / "corpus" / "locked.json"
        before = locked.read_bytes()
        rw.import_record(rec(CRITICAL), self.ledger, CANDS)
        rw.import_record(rec(CRITICAL, reviewer="fictional-reviewer-b"), self.ledger, CANDS)
        rw.status(self.ledger, CANDS)
        self.assertEqual(locked.read_bytes(), before)
        self.assertEqual(json.loads(before)["samples"], [])

    def test_committed_ledger_holds_no_invented_approval(self):
        self.assertEqual(rw.read_ledger(rw.LEDGER), [])


class TestContaminationLineage(unittest.TestCase):
    def test_classes(self):
        self.assertIn("author_dev", ct.classify("DEV-EN-001")["classes"])
        self.assertEqual(ct.classify("CAND-EN-019")["classes"], ["published_candidate", "regression_only"])
        self.assertIn("published_redteam", ct.classify("RTU-EN-U01")["classes"])
        self.assertTrue(ct.classify("RTU-EN-U01")["viewed_during_rule_development"])
        self.assertTrue(ct.classify("LOCK-EN-001")["independent_evidence"])
        self.assertEqual(ct.classify("EXT:dreaddit:test:7")["classes"], ["external_test"])
        with self.assertRaises(ct.ContaminationError):
            ct.classify("EXT:dreaddit:holdout:7")

    def test_derived_samples_need_lineage(self):
        self.assertTrue(ct.validate_lineage({"id": "LOCK-HI-001", "derived": True}))
        self.assertTrue(ct.validate_lineage({"id": "LOCK-HI-001", "lineage": {"derived_from": "X", "relation": "vibes"}}))
        self.assertEqual(ct.validate_lineage({"id": "LOCK-HI-001",
                                              "lineage": {"derived_from": "LOCK-EN-001", "relation": "translation"}}), [])

    def test_split_rules(self):
        v = ct.check_assignments({"training": ["LOCK-EN-002"], "locked": ["LOCK-EN-002"]})
        self.assertTrue(any("both training and locked" in x for x in v))
        v = ct.check_assignments({"external_train": ["EXT:dreaddit:train:1"], "locked": ["LOCK-HI-005"]},
                                 {"LOCK-HI-005": "LOCK-EN-009", "LOCK-EN-009": "EXT:dreaddit:train:1"})
        self.assertTrue(any("derived" in x for x in v))  # transitive translation
        self.assertTrue(ct.check_assignments({"locked": ["CAND-EN-019"]}))  # fixed published failure
        self.assertTrue(any("not holdout" in x for x in ct.check_assignments({"locked": ["EXT:emoinhindi:test:3"]})))
        self.assertEqual(ct.check_assignments({"locked": ["LOCK-EN-100"]}), [])

    def test_no_tuning_on_locked(self):
        with self.assertRaises(ct.ContaminationError):
            ct.forbid_tuning("locked")
        ct.forbid_tuning("dev")


if __name__ == "__main__":
    unittest.main()
