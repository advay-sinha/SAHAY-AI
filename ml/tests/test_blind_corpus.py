"""Blind-corpus tooling tests. Standard library only; offline; no dependencies.

EVERY scenario, person and record in this file is a temporary fixture for the
TOOLING, written into a temporary directory that is deleted when the test ends.
None of it is, or may become, evaluation data:

  * the scenarios are flat, obviously synthetic sentences about forms and bus
    stops, chosen so that they carry no safety content to be labelled;
  * the people are ``person-9xx`` with ``fictional-*`` account names;
  * nothing is ever written under ``ml/eval/corpus/`` or committed anywhere.

The official corpus is written by humans. These tests only prove that the
machinery around them refuses the right things.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.eval.blind import adjudication as adj
from ml.eval.blind import annotation as ann
from ml.eval.blind import assignment as asg
from ml.eval.blind import leakage as lk
from ml.eval.blind import normalize as nz
from ml.eval.blind import plan as pl
from ml.eval.blind import states as st
from ml.eval.blind import submission as sub
from ml.eval.blind.identity import competent_for, validate_person
from ml.eval.blind.ledger import LedgerError, append, head, read, verify_head
from ml.eval.blind.paths import ROOT_ENV, RootError, eval_root, resolve_under, version_dirs
from ml.eval.blind.store import Store, StoreError
from ml.eval.schema import CATEGORIES, DETECTOR_CATEGORIES

ML = Path(__file__).resolve().parents[1]
CORPUS_DIR = ML / "eval" / "corpus"
TS = "2026-09-12T10:00:00+05:30"

#: Deliberately dull, safety-free sentences. They exist to be moved around by
#: the tooling, not to be annotated for risk.
TEXT = {
    "en1": "I filled the form at the counter and the clerk asked me to return on Tuesday.",
    "en2": "The office was closed so I waited near the bus stop until the evening.",
    "en3": "I would like to know which window accepts the completed application.",
    "hi1": "\u092e\u0948\u0902\u0928\u0947 \u0915\u093e\u0909\u0902\u091f\u0930 \u092a\u0930 \u092b\u093c\u0949\u0930\u094d\u092e \u092d\u0930\u093e \u0914\u0930 \u0915\u094d\u0932\u0930\u094d\u0915 \u0928\u0947 \u092e\u0902\u0917\u0932\u0935\u093e\u0930 \u0915\u094b \u0906\u0928\u0947 \u0915\u094b \u0915\u0939\u093e\u0964",
    "hg1": "Maine counter par form bhara aur clerk ne Tuesday ko aane ko kaha.",
}

PEOPLE = [
    {"person_id": "person-901", "identity": "fictional-author-one", "kind": "human",
     "role": "Intake trainer (fictional test persona)", "languages": ["en", "hi"],
     "code_switch_competent": True, "can_author": True, "can_review": True, "can_adjudicate": False},
    {"person_id": "person-902", "identity": "fictional-reviewer-two", "kind": "human",
     "role": "Helpline supervisor (fictional test persona)", "languages": ["en", "hi"],
     "code_switch_competent": True, "can_author": True, "can_review": True, "can_adjudicate": True},
    {"person_id": "person-903", "identity": "fictional-reviewer-three", "kind": "human",
     "role": "Counsellor (fictional test persona)", "languages": ["en", "hi"],
     "code_switch_competent": True, "can_author": False, "can_review": True, "can_adjudicate": True},
    {"person_id": "person-904", "identity": "fictional-adjudicator-four", "kind": "human",
     "role": "Safety lead (fictional test persona)", "languages": ["en", "hi"],
     "code_switch_competent": True, "can_author": False, "can_review": True, "can_adjudicate": True},
    {"person_id": "person-905", "identity": "fictional-reviewer-five", "kind": "human",
     "role": "Legal aid volunteer (fictional test persona)", "languages": ["en"],
     "code_switch_competent": False, "can_author": False, "can_review": True, "can_adjudicate": False},
]


def roster(version="v1", people=None):
    return {"roster_version": "1.0.0", "corpus_version": version,
            "people": [dict(p) for p in (people if people is not None else PEOPLE)]}


def person(pid):
    entry = next(p for p in PEOPLE if p["person_id"] == pid)
    return {k: entry[k] for k in ("person_id", "identity", "kind", "role",
                                  "languages", "code_switch_competent")}


def make_submission(number=1, language="en", texts=None, author="person-901", version="v1",
                    slices=("indirect_language",), derived=False, translated=False, lineage=None,
                    script=None):
    code = sub.LANG_CODE[language]
    record = sub.template(version, language)
    record["submission_id"] = f"SUB-{sub.version_token(version)}-{code}-{number:04d}"
    record["script"] = script or sub.LANG_SCRIPTS[language][0]
    record["author"] = person(author)
    record["created_at"] = TS
    record["turns"] = [{"id": f"t{i + 1}", "speaker": "victim", "state": "S1", "text": t}
                       for i, t in enumerate(texts or [TEXT["en1"]])]
    record["intended_slices"] = list(slices)
    record["derived"] = derived
    record["translated"] = translated
    record["lineage"] = lineage
    record["attestations"] = dict(sub.ATTESTATIONS)
    record["content_sha256"] = sub.content_sha256(record)
    return record


def make_review(submission, reviewer="person-902", labels=None, routing="Low", evidence=None,
                decision="accept", confidence="high", abstain=False, reasoning=None, flags=()):
    who = person(reviewer)
    record = ann.blank_record(submission, who)
    record["reviewer"] = who
    record["labels"] = {c: False for c in CATEGORIES}
    record["labels"].update(labels or {})
    record["routing"] = routing
    record["expected_evidence"] = dict(evidence or {})
    record["expected_abstention"] = abstain
    record["decision"] = decision
    record["confidence"] = confidence
    record["reasoning"] = reasoning or "Plain procedural question about a counter and a form; nothing urgent."
    record["ambiguity_flags"] = list(flags)
    record["timestamp"] = TS
    record["attestation"] = ann.ATTESTATION
    return ann.finish_record(record)


def make_adjudication(submission, reviews, adjudicator="person-904", labels=None, routing="Low",
                      evidence=None, basis="adjudicator_decision", conservative=False, resolved=False,
                      abstain=False):
    record = adj.blank_record(submission["submission_id"], submission["corpus_version"],
                              sub.narrative_sha256(submission), reviews)
    record["adjudicator"] = person(adjudicator)
    record["labels"] = {c: False for c in CATEGORIES}
    record["labels"].update(labels or {})
    record["routing"] = routing
    record["expected_evidence"] = dict(evidence or {})
    record["expected_abstention"] = abstain
    record["resolution_basis"] = basis
    record["conservative_routing_only"] = conservative
    record["critical_conflict_resolved"] = resolved
    record["reasoning"] = ("The two reviewers read the counter sentence differently; the plain reading is a "
                          "routine procedural question with no urgency.")
    record["timestamp"] = TS
    record["attestation"] = adj.ATTESTATION
    record["record_sha256"] = adj.record_sha256(record)
    return record


class TempRoot(unittest.TestCase):
    """A private evaluation root that exists only for the duration of a test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root, "v1")
        self.store.init()
        (self.root / "assignments" / "v1").mkdir(parents=True, exist_ok=True)
        (self.root / "assignments" / "v1" / "roster.json").write_text(
            json.dumps(roster()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, submission, actor="person-902"):
        return self.store.submit(submission, person(actor), TS)


# --- schema, hashes, attestations -------------------------------------------------------


class TestSubmissionSchema(unittest.TestCase):
    def test_a_filled_submission_validates(self):
        self.assertEqual(sub.validate(make_submission(), "v1"), [])

    def test_blank_template_never_validates(self):
        self.assertTrue(sub.validate(sub.template("v1", "en"), "v1"))

    def test_content_hash_is_stable_and_covers_the_turns(self):
        one, two = make_submission(), make_submission()
        self.assertEqual(sub.content_sha256(one), sub.content_sha256(two))
        two["turns"][0]["text"] = TEXT["en2"]
        self.assertNotEqual(sub.content_sha256(one), sub.content_sha256(two))

    def test_edited_text_invalidates_the_declared_hash(self):
        record = make_submission()
        record["turns"][0]["text"] = TEXT["en2"]
        self.assertIn("content_sha256 does not match the submission content", sub.validate(record, "v1"))

    def test_narrative_hash_excludes_slices_so_a_reviewer_can_recompute_it(self):
        one = make_submission(slices=("indirect_language",))
        two = make_submission(slices=("safe_near_miss",))
        self.assertEqual(sub.narrative_sha256(one), sub.narrative_sha256(two))
        self.assertNotEqual(sub.content_sha256(one), sub.content_sha256(two))

    def test_every_attestation_must_be_copied_exactly(self):
        record = make_submission()
        record["attestations"]["fictional"] = "I agree"
        record["content_sha256"] = sub.content_sha256(record)
        self.assertTrue(any("fictional" in e for e in sub.validate(record, "v1")))

    def test_missing_attestation_is_refused(self):
        record = make_submission()
        record["attestations"]["no_llm_authoring_or_translation"] = ""
        self.assertTrue(any("no_llm_authoring_or_translation" in e for e in sub.validate(record, "v1")))

    def test_hindi_must_be_devanagari_and_hinglish_may_not_be(self):
        latin_hindi = make_submission(language="hi", texts=[TEXT["en1"]])
        self.assertTrue(any("Devanagari" in e for e in sub.validate(latin_hindi, "v1")))
        devanagari_hinglish = make_submission(language="hinglish", texts=[TEXT["hi1"]])
        self.assertTrue(any("Devanagari in a latin-script sample" in e
                            for e in sub.validate(devanagari_hinglish, "v1")))

    def test_declared_slice_must_be_supported_by_the_turns(self):
        record = make_submission(slices=("multi_turn_evidence",))
        self.assertIn("multi_turn_evidence needs more than one turn", sub.validate(record, "v1"))

    def test_derived_submission_needs_lineage(self):
        record = make_submission(derived=True)
        self.assertTrue(any("lineage" in e for e in sub.validate(record, "v1")))


class TestIdentities(unittest.TestCase):
    def test_placeholder_bot_and_ai_identities_are_refused(self):
        for name in ("TODO-reviewer-1", "claude", "some-bot", "gpt-helper", "ai-annotator", "dependabot[bot]"):
            who = dict(person("person-901"))
            who["identity"] = name
            self.assertTrue(validate_person(who), f"{name} should be refused")

    def test_non_human_kind_is_refused(self):
        who = dict(person("person-901"))
        who["kind"] = "agent"
        self.assertTrue(any("kind must be 'human'" in e for e in validate_person(who)))

    def test_language_competency_rules(self):
        english_only = {"languages": ["en"], "code_switch_competent": False}
        self.assertTrue(competent_for(english_only, "en"))
        self.assertFalse(competent_for(english_only, "hi"))
        self.assertFalse(competent_for(english_only, "hinglish"))
        both_no_switch = {"languages": ["en", "hi"], "code_switch_competent": False}
        self.assertFalse(competent_for(both_no_switch, "hinglish"))
        self.assertTrue(competent_for({"languages": ["en", "hi"], "code_switch_competent": True}, "hinglish"))


# --- privacy screen ---------------------------------------------------------------------


class TestPersonalInformation(unittest.TestCase):
    def test_screen_flags_shapes_and_never_returns_the_text(self):
        record = make_submission(texts=["Please call me on 9876543210 or write to a.b@example.org today."])
        hits = sub.personal_information(record)
        self.assertTrue(hits)
        patterns = {h["pattern"] for h in hits}
        self.assertTrue({"phone", "email"} & patterns)
        blob = json.dumps(hits, ensure_ascii=False)
        self.assertNotIn("9876543210", blob)
        self.assertNotIn("example.org", blob)

    def test_clean_text_produces_no_flag(self):
        self.assertEqual(sub.personal_information(make_submission()), [])

    def test_self_introduction_and_identifier_keywords_are_flagged(self):
        record = make_submission(texts=["My name is on the ration card and the case number is with the clerk."])
        patterns = {h["pattern"] for h in sub.personal_information(record)}
        self.assertIn("self_introduction", patterns)
        self.assertIn("identifier_keyword", patterns)


# --- leakage ----------------------------------------------------------------------------


class TestLeakage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = lk.build_index()
        corpus = json.loads((CORPUS_DIR / "dev.json").read_text(encoding="utf-8"))
        cls.fixture = corpus["samples"][0]
        cls.fixture_text = [t["text"] for t in cls.fixture["turns"] if t["speaker"] == "victim"]

    def copy_of(self, transform=lambda t: t, **kwargs):
        return make_submission(texts=[transform(t) for t in self.fixture_text], **kwargs)

    def test_an_existing_fixture_cannot_be_copied_directly(self):
        findings = lk.check(self.copy_of(), self.index)
        self.assertEqual(lk.worst(findings), "block")
        self.assertIn("exact_normalized_match", {f["check"] for f in findings})

    def test_punctuation_only_changes_are_detected(self):
        findings = lk.check(self.copy_of(lambda t: t.replace(".", " !!!")), self.index)
        self.assertEqual(lk.worst(findings), "block")

    def test_case_only_changes_are_detected(self):
        self.assertEqual(lk.worst(lk.check(self.copy_of(str.upper), self.index)), "block")

    def test_whitespace_only_changes_are_detected(self):
        self.assertEqual(lk.worst(lk.check(self.copy_of(lambda t: "  ".join(t.split())), self.index)), "block")

    def test_unicode_and_nukta_normalisation_collapse_variants(self):
        self.assertEqual(nz.compare("\u091c\u093c\u0930\u093e"), nz.compare("\u091c\u0930\u093e"))
        self.assertEqual(nz.compare("\u0939\u0901"), nz.compare("\u0939\u0902"))

    def test_reordered_turns_are_detected(self):
        corpus = json.loads((CORPUS_DIR / "dev.json").read_text(encoding="utf-8"))
        multi = next(s for s in corpus["samples"]
                     if len([t for t in s["turns"] if t["speaker"] == "victim"]) > 1)
        texts = [t["text"] for t in multi["turns"] if t["speaker"] == "victim"]
        record = make_submission(texts=list(reversed(texts)))
        checks = {f["check"] for f in lk.check(record, self.index)}
        self.assertTrue({"reordered_turn_match", "turn_level_match"} & checks)

    def test_a_declared_translation_of_a_published_failure_is_blocked(self):
        record = make_submission(texts=[TEXT["en2"]], derived=True, translated=True,
                                 lineage={"parent_id": "CAND-EN-003", "relation": "translation"})
        findings = lk.check(record, self.index)
        self.assertEqual(lk.worst(findings), "block")
        self.assertIn("declared_derivation_from_exposed", {f["check"] for f in findings})

    def test_published_failures_are_all_ineligible_ids(self):
        exposed = lk.exposed_ids(self.index)
        for sid in ("CAND-EN-003", "CAND-HI-003", "RT-EN-016", "DEV-EN-022"):
            self.assertIn(sid, exposed)

    def test_common_short_safety_phrases_do_not_reject_on_their_own(self):
        for phrase in ("I need help", "please help me", "mujhe madad chahiye"):
            record = make_submission(texts=[phrase + " with the form at the counter today."])
            self.assertIsNone(lk.worst(lk.check(record, self.index)), phrase)
        bare = make_submission(texts=["I need help"])
        bare["turns"][0]["text"] = "I need help"
        self.assertNotEqual(lk.worst(lk.check(bare, self.index)), "block")

    def test_novel_text_produces_no_finding(self):
        self.assertEqual(lk.check(make_submission(texts=[TEXT["en3"]]), self.index), [])

    def test_findings_never_contain_scenario_text(self):
        blob = json.dumps(lk.check(self.copy_of(), self.index), ensure_ascii=False)
        for text in self.fixture_text:
            self.assertNotIn(text[:25], blob)

    def test_lineage_chain_follows_declared_parents(self):
        parent = make_submission(2, texts=[TEXT["en2"]])
        child = make_submission(3, texts=[TEXT["en3"]], derived=True,
                                lineage={"parent_id": parent["submission_id"], "relation": "paraphrase"})
        chain = lk.declared_lineage_chain(child, {parent["submission_id"]: parent})
        self.assertEqual(chain, [parent["submission_id"]])

    def test_the_public_corpora_are_never_written(self):
        before = {p.name: p.read_bytes() for p in CORPUS_DIR.glob("*.json")}
        lk.build_index()
        lk.check(make_submission(), self.index)
        after = {p.name: p.read_bytes() for p in CORPUS_DIR.glob("*.json")}
        self.assertEqual(before, after)

    def test_locked_json_is_still_empty(self):
        locked = json.loads((CORPUS_DIR / "locked.json").read_text(encoding="utf-8"))
        self.assertEqual(locked["samples"], [])


# --- blinding ---------------------------------------------------------------------------


class TestBlinding(unittest.TestCase):
    def test_a_packet_shows_the_turns_and_nothing_that_hints_at_the_answer(self):
        submission = make_submission(slices=("explicit_negation", "safe_near_miss"))
        packet = ann.build_packet(submission, person("person-902"))
        self.assertEqual(set(packet), set(ann.PACKET_FIELDS))
        self.assertEqual(packet["turns"], submission["turns"])
        blob = json.dumps(packet, ensure_ascii=False)
        for leak in ("explicit_negation", "safe_near_miss", "person-901", "fictional-author-one",
                     "svi_score", "crisis_precheck", "routed_critical", "intended_slices",
                     "lineage", "attestations", "derived", "created_at"):
            self.assertNotIn(leak, blob, f"a packet must not carry {leak}")
        # the author's own fields are absent by construction, not by filtering
        self.assertEqual(set(packet) - set(ann.PACKET_FIELDS), set())
        self.assertNotIn("author", packet)

    def test_a_packet_carries_no_other_reviewers_decision(self):
        submission = make_submission()
        first = make_review(submission, "person-902", routing="Critical",
                            labels={"immediate_danger": True}, evidence={"immediate_danger": ["t1"]})
        packet = ann.build_packet(submission, person("person-903"))
        self.assertNotIn(first["record_sha256"], json.dumps(packet))
        self.assertNotIn("Critical", json.dumps(packet["record_template"]))

    def test_the_blank_record_in_a_packet_is_empty(self):
        packet = ann.build_packet(make_submission(), person("person-902"))
        template = packet["record_template"]
        self.assertEqual((template["decision"], template["routing"], template["attestation"]), ("", "", ""))
        self.assertTrue(ann.validate_record(template, packet))

    def test_a_reviewer_can_recompute_the_narrative_hash_from_the_packet(self):
        submission = make_submission()
        packet = ann.build_packet(submission, person("person-902"))
        self.assertEqual(sub.narrative_sha256(packet), packet["narrative_sha256"])


class TestReviewRecords(unittest.TestCase):
    def setUp(self):
        self.submission = make_submission()
        self.packet = ann.build_packet(self.submission, person("person-902"))

    def test_a_filled_record_validates(self):
        self.assertEqual(ann.validate_record(make_review(self.submission), self.packet), [])

    def test_a_critical_label_must_be_routed_critical(self):
        record = make_review(self.submission, labels={"crisis_self_harm": True},
                             evidence={"crisis_self_harm": ["t1"]}, routing="High")
        self.assertIn("a crisis or immediate-danger label must be routed Critical",
                      ann.validate_record(record, self.packet))

    def test_a_positive_label_needs_evidence_turns(self):
        record = make_review(self.submission, labels={"legal_urgency": True}, routing="Moderate")
        self.assertIn("label legal_urgency is true but has no expected_evidence",
                      ann.validate_record(record, self.packet))

    def test_evidence_must_name_a_victim_turn_of_this_packet(self):
        record = make_review(self.submission, labels={"legal_urgency": True},
                             evidence={"legal_urgency": ["t9"]}, routing="Moderate")
        self.assertTrue(any("not a victim turn" in e for e in ann.validate_record(record, self.packet)))

    def test_an_altered_record_fails_its_own_hash(self):
        record = dict(make_review(self.submission))
        record["routing"] = "High"
        self.assertIn("record_sha256 does not match the record", ann.validate_record(record, self.packet))

    def test_a_record_for_different_text_is_refused(self):
        other = make_submission(texts=[TEXT["en2"]])
        record = make_review(other)
        self.assertTrue(any("narrative_sha256" in e for e in ann.validate_record(record, self.packet)))

    def test_the_attestation_must_be_exact(self):
        record = dict(make_review(self.submission))
        record["attestation"] = "I looked at it"
        record["record_sha256"] = ann.record_sha256(record)
        self.assertIn("the reviewer attestation sentence is missing or altered",
                      ann.validate_record(record, self.packet))

    def test_abstention_and_flags_require_reasoning(self):
        record = dict(make_review(self.submission, abstain=True))
        record["reasoning"] = "unclear"
        record["record_sha256"] = ann.record_sha256(record)
        self.assertTrue(any("reasoning of at least" in e for e in ann.validate_record(record, self.packet)))

    def test_a_reviewer_without_the_language_is_refused(self):
        hindi = make_submission(language="hi", texts=[TEXT["hi1"]])
        packet = ann.build_packet(hindi, person("person-905"))
        record = make_review(hindi, "person-905")
        self.assertIn("reviewer is not recorded as competent in hi", ann.validate_record(record, packet))


# --- assignment and conflicts ------------------------------------------------------------


class TestAssignment(unittest.TestCase):
    def test_assignment_is_deterministic(self):
        subs = [make_submission(i) for i in range(1, 6)]
        first = asg.assign(subs, roster())
        second = asg.assign(list(reversed(subs)), roster())
        self.assertEqual(first["assignments"], second["assignments"])

    def test_an_author_is_never_assigned_their_own_sample(self):
        subs = [make_submission(i, author="person-901") for i in range(1, 6)]
        for row in asg.assign(subs, roster())["assignments"]:
            self.assertNotIn("person-901", [r["person_id"] for r in row["reviewers"]])

    def test_two_distinct_reviewers_per_sample(self):
        for row in asg.assign([make_submission(1)], roster())["assignments"]:
            ids = [r["person_id"] for r in row["reviewers"]]
            self.assertEqual(len(ids), 2)
            self.assertEqual(len(set(ids)), 2)

    def test_one_human_with_two_accounts_gets_one_slot(self):
        people = [dict(p) for p in PEOPLE[:3]]
        twin = dict(people[1])
        twin["identity"] = "fictional-reviewer-two-alt"
        people.append(twin)
        allocation = asg.assign([make_submission(1)], roster(people=people))
        ids = [r["person_id"] for r in allocation["assignments"][0]["reviewers"]]
        self.assertEqual(len(set(ids)), len(ids))

    def test_language_competency_is_enforced_and_a_shortfall_is_reported(self):
        only_english = [p for p in PEOPLE if p["person_id"] == "person-905"]
        hindi = make_submission(1, language="hi", texts=[TEXT["hi1"]], author="person-901")
        allocation = asg.assign([hindi], roster(people=only_english))
        self.assertTrue(allocation["shortfalls"])
        self.assertFalse(allocation["complete"])

    def test_load_is_spread_rather_than_piled_on_one_person(self):
        subs = [make_submission(i) for i in range(1, 13)]
        load = asg.assign(subs, roster())["load"]
        working = [v for k, v in load.items() if v]
        self.assertGreaterEqual(len(working), 3)
        self.assertLessEqual(max(working) - min(working), 2)

    def test_duplicate_reviewer_is_detected(self):
        submission = make_submission()
        first = make_review(submission, "person-902")
        self.assertTrue(asg.duplicate_reviewer([first], make_review(submission, "person-902")))
        self.assertFalse(asg.duplicate_reviewer([first], make_review(submission, "person-903")))

    def test_identical_reasoning_is_flagged_but_not_called_invalid(self):
        submission = make_submission()
        shared = "Both of us read this as an ordinary procedural question about the counter."
        records = [make_review(submission, "person-902", reasoning=shared),
                   make_review(submission, "person-903", reasoning=shared)]
        flags = asg.copied_reasoning(records)
        self.assertEqual(len(flags), 1)
        self.assertIn("human inspection", flags[0]["note"])
        packet = ann.build_packet(submission, person("person-902"))
        self.assertEqual(ann.validate_record(records[0], packet), [])

    def test_conflicts_are_detected_field_by_field(self):
        submission = make_submission()
        a = make_review(submission, "person-902", routing="Low")
        b = make_review(submission, "person-903", routing="Moderate",
                        labels={"legal_urgency": True}, evidence={"legal_urgency": ["t1"]})
        comparison = asg.compare_reviews([a, b])
        self.assertFalse(comparison["agreed"])
        self.assertIn("routing", comparison["conflicts"])
        self.assertIn("label:legal_urgency", comparison["conflicts"])
        self.assertFalse(comparison["critical_conflict"])

    def test_a_critical_disagreement_is_marked_critical(self):
        submission = make_submission()
        a = make_review(submission, "person-902", routing="Low")
        b = make_review(submission, "person-903", routing="Critical",
                        labels={"immediate_danger": True}, evidence={"immediate_danger": ["t1"]})
        self.assertTrue(asg.compare_reviews([a, b])["critical_conflict"])

    def test_agreeing_reviews_report_no_conflict(self):
        submission = make_submission()
        self.assertTrue(asg.compare_reviews([make_review(submission, "person-902"),
                                             make_review(submission, "person-903")])["agreed"])


# --- adjudication -------------------------------------------------------------------------


class TestAdjudication(unittest.TestCase):
    def setUp(self):
        self.submission = make_submission()
        self.a = make_review(self.submission, "person-902", routing="Low")
        self.b = make_review(self.submission, "person-903", routing="Moderate",
                             labels={"legal_urgency": True}, evidence={"legal_urgency": ["t1"]})

    def test_a_valid_non_critical_adjudication_is_accepted(self):
        record = make_adjudication(self.submission, [self.a, self.b])
        self.assertEqual(adj.validate_record(record, self.submission, [self.a, self.b]), [])

    def test_the_author_cannot_adjudicate(self):
        record = make_adjudication(self.submission, [self.a, self.b], adjudicator="person-901")
        self.assertIn("the author of a sample cannot adjudicate it",
                      adj.validate_record(record, self.submission, [self.a, self.b]))

    def test_a_reviewer_in_conflict_cannot_adjudicate_it(self):
        record = make_adjudication(self.submission, [self.a, self.b], adjudicator="person-903")
        self.assertIn("a reviewer whose record is in conflict cannot adjudicate that conflict",
                      adj.validate_record(record, self.submission, [self.a, self.b]))

    def test_an_adjudication_cannot_carry_scenario_text(self):
        record = dict(make_adjudication(self.submission, [self.a, self.b]))
        record["turns"] = self.submission["turns"]
        self.assertTrue(any("cannot carry scenario text" in e
                            for e in adj.validate_record(record, self.submission, [self.a, self.b])))

    def test_both_reviews_survive_adjudication_untouched(self):
        before = (self.a["record_sha256"], self.b["record_sha256"])
        make_adjudication(self.submission, [self.a, self.b])
        self.assertEqual((self.a["record_sha256"], self.b["record_sha256"]), before)

    def test_reasoning_is_required(self):
        record = dict(make_adjudication(self.submission, [self.a, self.b]))
        record["reasoning"] = "ok"
        record["record_sha256"] = adj.record_sha256(record)
        self.assertTrue(any("written reasoning" in e
                            for e in adj.validate_record(record, self.submission, [self.a, self.b])))

    def test_a_critical_conflict_may_only_record_the_conservative_routing(self):
        crit_a = make_review(self.submission, "person-902", routing="Low")
        crit_b = make_review(self.submission, "person-903", routing="Critical",
                             labels={"crisis_self_harm": True}, evidence={"crisis_self_harm": ["t1"]})
        record = make_adjudication(self.submission, [crit_a, crit_b], routing="Low")
        errs = adj.validate_record(record, self.submission, [crit_a, crit_b])
        self.assertIn("an unresolved critical disagreement must record conservative_routing_only", errs)
        conservative = make_adjudication(self.submission, [crit_a, crit_b], routing="Critical",
                                         labels={"crisis_self_harm": True},
                                         evidence={"crisis_self_harm": ["t1"]}, conservative=True)
        self.assertEqual(adj.validate_record(conservative, self.submission, [crit_a, crit_b]), [])
        self.assertTrue(adj.eligible_after_adjudication(conservative, [crit_a, crit_b]))

    def test_a_critical_conflict_cannot_be_resolved_by_the_adjudicator_alone(self):
        crit_a = make_review(self.submission, "person-902", routing="Low")
        crit_b = make_review(self.submission, "person-903", routing="Critical",
                             labels={"crisis_self_harm": True}, evidence={"crisis_self_harm": ["t1"]})
        record = make_adjudication(self.submission, [crit_a, crit_b], routing="Critical",
                                   labels={"crisis_self_harm": True},
                                   evidence={"crisis_self_harm": ["t1"]}, resolved=True)
        errs = adj.validate_record(record, self.submission, [crit_a, crit_b])
        self.assertTrue(any("distinct reviewers holding" in e for e in errs))
        self.assertTrue(any("cannot be resolved by an adjudicator" in e for e in errs))

    def test_a_third_agreeing_review_can_resolve_a_critical_conflict(self):
        crit_a = make_review(self.submission, "person-902", routing="Low")
        crit_b = make_review(self.submission, "person-903", routing="Critical",
                             labels={"crisis_self_harm": True}, evidence={"crisis_self_harm": ["t1"]})
        third = make_review(self.submission, "person-905", routing="Critical",
                            labels={"crisis_self_harm": True}, evidence={"crisis_self_harm": ["t1"]})
        record = make_adjudication(self.submission, [crit_a, crit_b, third], routing="Critical",
                                   labels={"crisis_self_harm": True},
                                   evidence={"crisis_self_harm": ["t1"]},
                                   basis="third_independent_review", resolved=True)
        self.assertEqual(adj.validate_record(record, self.submission, [crit_a, crit_b, third]), [])
        self.assertEqual(adj.eligible_after_adjudication(record, [crit_a, crit_b, third]), [])


# --- ledger -------------------------------------------------------------------------------


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "reviews.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_and_read_back(self):
        submission = make_submission()
        append(self.path, "review", make_review(submission, "person-902"))
        append(self.path, "review", make_review(submission, "person-903"))
        self.assertEqual(len(read(self.path)), 2)

    def test_the_same_record_cannot_be_appended_twice(self):
        record = make_review(make_submission(), "person-902")
        append(self.path, "review", record)
        with self.assertRaises(LedgerError):
            append(self.path, "review", record)

    def test_editing_an_entry_breaks_the_chain(self):
        submission = make_submission()
        append(self.path, "review", make_review(submission, "person-902"))
        append(self.path, "review", make_review(submission, "person-903"))
        lines = self.path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[0])
        entry["record"]["routing"] = "Critical"
        lines[0] = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(LedgerError):
            read(self.path)

    def test_deleting_an_entry_breaks_the_chain(self):
        submission = make_submission()
        append(self.path, "review", make_review(submission, "person-902"))
        append(self.path, "review", make_review(submission, "person-903"))
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.path.write_text(lines[1] + "\n", encoding="utf-8")
        with self.assertRaises(LedgerError):
            read(self.path)

    def test_truncation_is_caught_only_against_a_recorded_head(self):
        submission = make_submission()
        append(self.path, "review", make_review(submission, "person-902"))
        recorded = head(self.path)
        append(self.path, "review", make_review(submission, "person-903"))
        two = head(self.path)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.path.write_text(lines[0] + "\n", encoding="utf-8")
        read(self.path)  # a truncated chain is internally consistent
        verify_head(self.path, recorded)  # and still matches the OLD head
        with self.assertRaises(LedgerError):
            verify_head(self.path, two)

    def test_an_empty_ledger_is_valid(self):
        self.assertEqual(read(self.path), [])
        self.assertTrue(head(self.path).startswith("0:"))


# --- states -------------------------------------------------------------------------------


class TestStates(unittest.TestCase):
    def test_no_command_can_skip_from_submitted_to_frozen(self):
        with self.assertRaises(st.StateError):
            st.validate_transition("submitted", "frozen")

    def test_eligible_is_only_reachable_from_review_complete(self):
        self.assertEqual(st.reachable("eligible"), ["review_complete"])
        self.assertEqual(st.reachable("frozen"), ["eligible"])

    def test_terminal_states_cannot_be_left(self):
        for state in st.TERMINAL:
            with self.assertRaises(st.StateError):
                st.validate_transition(state, "assigned")

    def test_a_transition_record_carries_the_whole_audit_tuple(self):
        record = st.make_transition("v1", "SUB-V1-EN-0001", person("person-902"), "submitted", "assigned",
                                    "two independent reviewers allocated", {"reviewers": 2}, TS)
        for field in ("actor", "timestamp", "prior_state", "new_state", "reason",
                      "input_sha256", "record_sha256"):
            self.assertIn(field, record)
        self.assertEqual(st.validate_record(record), [])

    def test_a_justified_transition_needs_an_input_hash(self):
        with self.assertRaises(st.StateError):
            st.make_transition("v1", "SUB-V1-EN-0001", person("person-902"), "submitted", "assigned",
                               "allocated reviewers", None, TS)

    def test_replay_refuses_a_history_that_skips_a_state(self):
        first = st.make_transition("v1", "SUB-V1-EN-0001", person("person-902"), "submitted", "assigned",
                                   "reviewers allocated", {"n": 2}, TS)
        wrong = st.make_transition("v1", "SUB-V1-EN-0001", person("person-902"), "review_complete",
                                   "eligible", "everything passed", {"n": 2}, TS)
        with self.assertRaises(st.StateError):
            st.replay([first, wrong])


# --- coverage -----------------------------------------------------------------------------


class TestCoverage(unittest.TestCase):
    def test_the_committed_plan_validates_and_asks_for_180_samples(self):
        plan = pl.load_plan("v1")
        self.assertEqual(pl.validate_plan(plan), [])
        self.assertEqual(plan["total_min"], 180)
        self.assertEqual({e["language"]: e["min"] for e in plan["languages"]},
                         {"en": 60, "hi": 60, "hinglish": 60})

    def test_every_category_and_slice_has_a_reason(self):
        plan = pl.load_plan("v1")
        for entry in plan["categories"] + plan["slices"]:
            self.assertGreater(len(entry["why"]), 40)

    def test_an_empty_corpus_satisfies_nothing(self):
        report = pl.coverage(pl.load_plan("v1"), [])
        self.assertFalse(report["satisfied"])
        self.assertEqual(report["samples"], 0)

    def test_categories_are_derived_from_labels_not_from_intent(self):
        self.assertIn("no_alert_control", pl.categories_of({}, "Low", False))
        self.assertIn("multi_label", pl.categories_of(
            {"legal_urgency": True, "medical_urgency": True}, "High", False))
        self.assertIn("expected_abstention", pl.categories_of({}, "Moderate", True))

    def test_a_language_shortfall_is_reported_separately(self):
        plan = pl.load_plan("v1")
        items = [{"language": "en", "categories": ["no_alert_control"], "slices": []}] * 60
        report = pl.coverage(plan, items)
        kinds = {(s["kind"], s["name"]) for s in report["shortfalls"]}
        self.assertIn(("language", "hi"), kinds)
        self.assertIn(("language", "hinglish"), kinds)


# --- private root ---------------------------------------------------------------------------


class TestPrivateRoot(unittest.TestCase):
    def test_an_unset_root_is_refused_with_no_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ROOT_ENV, None)
            with self.assertRaises(RootError):
                eval_root()

    def test_path_traversal_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for bad in ("../escape", "..", "a/../../escape", "/etc/passwd", "C:/Windows",
                        "sub/../../out", "\\\\server\\share"):
                with self.assertRaises(RootError, msg=bad):
                    resolve_under(Path(tmp), bad)

    def test_a_legitimate_relative_path_resolves_inside_the_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = resolve_under(Path(tmp), "frozen/v1/corpus.json")
            self.assertTrue(str(target).startswith(str(Path(tmp).resolve())))

    def test_the_layout_is_versioned(self):
        dirs = version_dirs("v2-holdout")
        self.assertTrue(all("v2-holdout" in d for d in dirs.values()))

    def test_a_bad_version_token_is_refused(self):
        with self.assertRaises(RootError):
            version_dirs("../v1")


# --- end-to-end through the store ------------------------------------------------------------


class TestStoreWorkflow(TempRoot):
    def test_init_writes_blank_templates_and_no_scenario(self):
        for name in ("submission-template-en.json", "submission-template-hi.json", "roster-template.json"):
            path = self.root / "intake" / name
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "turns" in payload:
                self.assertEqual([t["text"] for t in payload["turns"]], [""])
            if "people" in payload:
                self.assertEqual(payload["people"], [])

    def test_a_submission_is_recorded_once_and_never_replaced(self):
        record = make_submission()
        self.submit(record)
        with self.assertRaises(StoreError):
            self.submit(record)

    def test_a_schema_invalid_submission_records_nothing(self):
        broken = make_submission()
        broken["turns"][0]["text"] = TEXT["en2"]  # hash no longer matches
        with self.assertRaises(StoreError):
            self.submit(broken)
        self.assertEqual(self.store.submissions(), {})

    def test_a_pii_hit_moves_the_sample_to_review_required(self):
        record = make_submission(texts=["Please call 9876543210 about the form at the counter."])
        result = self.submit(record)
        self.assertEqual(result["state"], "pii_review_required")

    def test_an_author_cannot_review_their_own_sample(self):
        record = make_submission(author="person-902")
        self.submit(record)
        self.store.save_assignment(person("person-902"), TS)
        review = make_review(record, "person-902")
        with self.assertRaises(StoreError) as ctx:
            self.store.import_review(review, person("person-902"), TS)
        self.assertIn("cannot review it", str(ctx.exception))

    def test_the_same_reviewer_cannot_review_twice(self):
        record = make_submission()
        self.submit(record)
        allocation = self.store.save_assignment(person("person-902"), TS)
        first = allocation["assignments"][0]["reviewers"][0]["person_id"]
        review = make_review(record, first)
        self.store.import_review(review, person("person-902"), TS)
        again = make_review(record, first, reasoning="A second look at the same counter sentence today.")
        with self.assertRaises(StoreError) as ctx:
            self.store.import_review(again, person("person-902"), TS)
        self.assertIn("already recorded a review", str(ctx.exception))

    def test_two_agreeing_reviews_complete_the_review(self):
        record = make_submission()
        self.submit(record)
        allocation = self.store.save_assignment(person("person-902"), TS)
        for entry in allocation["assignments"][0]["reviewers"]:
            self.store.import_review(make_review(record, entry["person_id"]), person("person-902"), TS)
        self.assertEqual(self.store.state_of(record["submission_id"]), "review_complete")
        outcome = self.store.outcome(record["submission_id"])
        self.assertEqual(outcome["source"], "reviews")

    def test_disagreement_leads_to_conflicted_and_no_outcome(self):
        record = make_submission()
        self.submit(record)
        allocation = self.store.save_assignment(person("person-902"), TS)
        reviewers = [e["person_id"] for e in allocation["assignments"][0]["reviewers"]]
        self.store.import_review(make_review(record, reviewers[0]), person("person-902"), TS)
        self.store.import_review(
            make_review(record, reviewers[1], routing="Moderate", labels={"legal_urgency": True},
                        evidence={"legal_urgency": ["t1"]},
                        reasoning="This reads to me as a live procedural problem that needs follow-up."),
            person("person-902"), TS)
        self.assertEqual(self.store.state_of(record["submission_id"]), "conflicted")
        self.assertIsNone(self.store.outcome(record["submission_id"]))

    def test_an_adjudication_resolves_a_non_critical_conflict(self):
        record = make_submission()
        self.submit(record)
        allocation = self.store.save_assignment(person("person-902"), TS)
        reviewers = [e["person_id"] for e in allocation["assignments"][0]["reviewers"]]
        self.store.import_review(make_review(record, reviewers[0]), person("person-902"), TS)
        self.store.import_review(
            make_review(record, reviewers[1], routing="Moderate", labels={"legal_urgency": True},
                        evidence={"legal_urgency": ["t1"]},
                        reasoning="This reads to me as a live procedural problem that needs follow-up."),
            person("person-902"), TS)
        reviews = self.store.reviews(record["submission_id"])
        adjudicator = next(p for p in ("person-904", "person-902", "person-903")
                           if p not in reviewers)
        decision = make_adjudication(record, reviews, adjudicator=adjudicator)
        result = self.store.import_adjudication(decision, person("person-902"), TS)
        self.assertEqual(result["state"], "review_complete")
        self.assertEqual(self.store.outcome(record["submission_id"])["source"], "adjudication")

    def test_status_and_errors_never_contain_scenario_text(self):
        record = make_submission(texts=[TEXT["en1"], TEXT["en2"]])
        self.submit(record)
        blob = json.dumps(self.store.status(), ensure_ascii=False)
        for text in (TEXT["en1"], TEXT["en2"]):
            self.assertNotIn(text[:25], blob)

    def test_ledgers_verify_and_expose_a_head(self):
        record = make_submission()
        self.submit(record)
        heads = self.store.heads()
        self.assertEqual(set(heads), {"submissions", "reviews", "adjudications", "states"})
        self.assertTrue(heads["submissions"].startswith("1:"))

    def test_exported_packets_are_one_per_assigned_reviewer(self):
        record = make_submission()
        self.submit(record)
        self.store.save_assignment(person("person-902"), TS)
        written = self.store.export_packets()
        self.assertEqual(len(written), 2)
        packet = json.loads(written[0].read_text(encoding="utf-8"))
        self.assertNotIn("person-901", json.dumps(packet))

    def test_the_actor_must_be_a_real_person_on_the_roster(self):
        with self.assertRaises(StoreError):
            self.store.actor("person-999")
        with self.assertRaises(StoreError):
            self.store.actor("person-901", "can_adjudicate")

    def test_detector_categories_are_unchanged_by_this_tooling(self):
        self.assertEqual(len(DETECTOR_CATEGORIES), 8)
        self.assertEqual(len(CATEGORIES), 11)


if __name__ == "__main__":
    unittest.main()
