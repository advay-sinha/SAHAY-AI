"""Consent gate and human-decision separation.

Root CLAUDE.md invariants 4, 6 and 7. Standard library unittest.
"""

import unittest

from backend.app.services.consent import (
    CONSENT_DECLINED,
    CONSENT_GRANTED,
    CONSENT_PENDING,
    may_assess,
    session_capabilities,
)
from backend.app.services.decisions import (
    DECISION_CONFIRM,
    InvalidDecision,
    OverrideReasonRequired,
    STATUS_AWAITING,
    human_decision_payload,
    recommendation_payload,
    validate_override,
)


class TestConsentGate(unittest.TestCase):
    def test_assessment_requires_an_explicit_grant(self):
        self.assertTrue(may_assess(CONSENT_GRANTED))
        self.assertFalse(may_assess(CONSENT_DECLINED))
        self.assertFalse(may_assess(CONSENT_PENDING))
        self.assertFalse(may_assess(None))

    def test_declined_consent_suppresses_scoring_and_retention(self):
        caps = session_capabilities(CONSENT_DECLINED)
        self.assertFalse(caps["assessment_enabled"])
        self.assertFalse(caps["scoring_enabled"])
        self.assertFalse(caps["audio_retained"])

    def test_declined_consent_still_reaches_a_human(self):
        caps = session_capabilities(CONSENT_DECLINED)
        self.assertTrue(caps["routes_to_human"])
        self.assertTrue(caps["human_request_available"])

    def test_ai_disclosure_and_human_request_are_unconditional(self):
        for consent in (CONSENT_GRANTED, CONSENT_DECLINED, CONSENT_PENDING, None):
            caps = session_capabilities(consent)
            self.assertTrue(caps["ai_disclosure_visible"], msg=consent)
            self.assertTrue(caps["human_request_available"], msg=consent)


class TestHumanDecisionSeparation(unittest.TestCase):
    def test_a_recommendation_is_never_presented_as_an_action_taken(self):
        rec = recommendation_payload("a1", "escalate", "because", ["policy:1"], 0.8)
        self.assertEqual(rec["status"], STATUS_AWAITING)
        self.assertFalse(rec["decided_by_machine"])

    def test_a_recommendation_carries_no_decision_or_officer_field(self):
        rec = recommendation_payload("a1", "escalate", "because", [], 0.8)
        self.assertNotIn("decision", rec)
        self.assertNotIn("officer_id", rec)

    def test_a_human_decision_must_name_an_officer(self):
        with self.assertRaises(InvalidDecision):
            human_decision_payload("a1", DECISION_CONFIRM, "agreed", "")

    def test_an_unknown_decision_is_refused(self):
        with self.assertRaises(InvalidDecision):
            human_decision_payload("a1", "auto_approve", "", "off-1")

    def test_the_two_payloads_stay_separate(self):
        rec = recommendation_payload("a1", "escalate", "because", [], 0.8)
        decision = human_decision_payload("a1", DECISION_CONFIRM, "agreed", "off-1")
        # CONTRACTS.md names the field "rationale" on both action.recommended and
        # POST /cases/{id}/decisions, so the overlap is contractual. What matters
        # is that they are separate records: only the human one names an officer,
        # and only the AI one carries a confidence and policy citations.
        self.assertEqual(set(rec) & set(decision), {"action_id", "status", "rationale"})
        self.assertEqual(decision["officer_id"], "off-1")
        self.assertNotIn("confidence", decision)
        self.assertNotIn("policy_citations", decision)
        self.assertNotIn("officer_id", rec)


class TestBandOverride(unittest.TestCase):
    def test_an_override_without_a_reason_is_refused_server_side(self):
        for reason in (None, "", "   "):
            with self.assertRaises(OverrideReasonRequired, msg=repr(reason)):
                validate_override("High", reason)

    def test_an_override_with_a_reason_is_accepted(self):
        result = validate_override("Critical", "  caller reported a weapon  ")
        self.assertEqual(result["reason"], "caller reported a weapon")


if __name__ == "__main__":
    unittest.main()
