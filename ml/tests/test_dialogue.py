"""Dialogue policy tests, including the unconditional crisis interrupt."""

import unittest

from ml.dialogue import next as dialogue_next
from ml.dialogue.states import DEFAULT_ORDER, State
from ml.dialogue import intents


ALL_STATES = list(State)


class TestCrisisInterrupt(unittest.TestCase):
    def test_crisis_forces_sx_from_every_state(self):
        for state in ALL_STATES:
            result = dialogue_next(state, {}, "any utterance", {"crisis": True})
            self.assertEqual(result["next_state"], State.SX_CRISIS.value, msg=state)
            self.assertEqual(result["intent"], intents.CRISIS_SCRIPT, msg=state)

    def test_crisis_overrides_a_human_request(self):
        result = dialogue_next(State.S2_IMMEDIATE_SAFETY, {}, "", {"crisis": True, "request_human": True})
        self.assertEqual(result["next_state"], State.SX_CRISIS.value)

    def test_sx_never_resumes_intake(self):
        result = dialogue_next(State.SX_CRISIS, {"incident": "x", "safety_now": "yes"}, "", {})
        self.assertEqual(result["next_state"], State.SX_CRISIS.value)

    def test_sx_is_not_rephrasable_and_needs_an_approved_script(self):
        result = dialogue_next(State.S1_FREE_NARRATIVE, {}, "", {"crisis": True})
        self.assertTrue(result["fixed_script"])
        self.assertFalse(result["rephrasable"])
        # The script has not been written or reviewed yet, so nothing is speakable.
        self.assertFalse(result["script_available"])
        self.assertIsNone(result["fallback_text"])


class TestHumanRequest(unittest.TestCase):
    def test_request_human_forces_handoff_from_every_intake_state(self):
        for state in DEFAULT_ORDER:
            result = dialogue_next(state, {}, "", {"request_human": True})
            self.assertEqual(result["next_state"], State.SH_HUMAN_HANDOFF.value, msg=state)

    def test_handoff_does_not_resume_intake(self):
        result = dialogue_next(State.SH_HUMAN_HANDOFF, {}, "", {})
        self.assertEqual(result["next_state"], State.SH_HUMAN_HANDOFF.value)

    def test_consent_declined_routes_to_a_person(self):
        result = dialogue_next(State.S0_OPENING, {}, "", {"consent": False})
        self.assertEqual(result["next_state"], State.SH_HUMAN_HANDOFF.value)


class TestFlow(unittest.TestCase):
    def test_unknown_state_opens_with_the_fixed_opening_script(self):
        result = dialogue_next(None, {}, "", {})
        self.assertEqual(result["next_state"], State.S0_OPENING.value)
        self.assertTrue(result["fixed_script"])

    def test_s0_advances_to_free_narrative(self):
        result = dialogue_next(State.S0_OPENING, {}, "", {})
        self.assertEqual(result["next_state"], State.S1_FREE_NARRATIVE.value)

    def test_s1_keeps_listening_until_the_narrative_slot_is_filled(self):
        result = dialogue_next(State.S1_FREE_NARRATIVE, {}, "", {})
        self.assertEqual(result["next_state"], State.S1_FREE_NARRATIVE.value)
        self.assertEqual(result["intent"], intents.ACKNOWLEDGE)

    def test_s1_licenses_no_question(self):
        result = dialogue_next(State.S1_FREE_NARRATIVE, {}, "", {})
        self.assertIsNone(result["licensed_question"])

    def test_filled_slots_skip_their_state(self):
        slots = {
            "incident": "described",
            "medical_need": "none",
            "_sources": {"medical_need": "answered"},
        }
        result = dialogue_next(State.S2_IMMEDIATE_SAFETY, slots, "", {})
        self.assertEqual(result["next_state"], State.S4_WHO_AND_WHEN.value)

    def test_s2_is_not_skipped_on_an_extracted_value(self):
        slots = {
            "incident": "described",
            "safety_now": "maybe",
            "proximity_of_threat": "unknown",
            "_sources": {"safety_now": "extracted", "proximity_of_threat": "extracted"},
        }
        result = dialogue_next(State.S1_FREE_NARRATIVE, slots, "", {})
        self.assertEqual(result["next_state"], State.S2_IMMEDIATE_SAFETY.value)

    def test_s2_is_skipped_when_explicitly_answered(self):
        slots = {
            "incident": "described",
            "safety_now": "no",
            "proximity_of_threat": "next door",
            "_sources": {"safety_now": "answered", "proximity_of_threat": "answered"},
        }
        result = dialogue_next(State.S1_FREE_NARRATIVE, slots, "", {})
        self.assertEqual(result["next_state"], State.S3_MEDICAL_NEED.value)

    def test_every_slot_filled_reaches_closing(self):
        slots = {name: "x" for name in (
            "incident", "safety_now", "proximity_of_threat", "medical_need",
            "persons", "when", "threat_ongoing", "isolation", "fir_status",
            "requested_support",
        )}
        slots["_sources"] = {"safety_now": "answered", "proximity_of_threat": "answered"}
        result = dialogue_next(State.S1_FREE_NARRATIVE, slots, "", {})
        self.assertEqual(result["next_state"], State.S9_CLOSING.value)

    def test_closing_is_terminal(self):
        result = dialogue_next(State.S9_CLOSING, {}, "", {})
        self.assertEqual(result["next_state"], State.S9_CLOSING.value)


class TestIntentDiscipline(unittest.TestCase):
    def test_every_state_licenses_exactly_one_intent(self):
        for state in ALL_STATES:
            self.assertIn(state, intents.STATE_INTENT, msg=state)

    def test_question_intents_ask_one_question_only(self):
        for intent, texts in intents.LICENSED_QUESTION.items():
            for lang, text in texts.items():
                if text is None:
                    continue
                self.assertEqual(text.count("?"), 1, msg=f"{intent}:{lang}")

    def test_every_rephrasable_intent_has_a_fallback_in_both_languages(self):
        for intent in intents.REPHRASABLE_INTENTS:
            for lang in intents.SUPPORTED_LANGS:
                self.assertTrue(
                    intents.fallback_text(intent, lang),
                    msg=f"{intent}:{lang} has no fallback; the system cannot run with the LLM off",
                )

    def test_fixed_script_intents_are_never_rephrasable(self):
        for intent in (intents.OPENING_SCRIPT, intents.CLOSING_SCRIPT,
                       intents.CRISIS_SCRIPT, intents.HANDOFF_SCRIPT):
            self.assertNotIn(intent, intents.REPHRASABLE_INTENTS, msg=intent)

    def test_unreviewed_text_is_not_marked_speakable(self):
        for lang in intents.SUPPORTED_LANGS:
            self.assertFalse(
                intents.is_speakable(lang),
                msg="Review status was changed without a type:dialogue review",
            )


if __name__ == "__main__":
    unittest.main()
