"""Guardrail validator and crisis pre-check tests.

Every prohibition in docs/dialogue/STATES.md is exercised in Hindi and English.
"""

import unittest

from ml.dialogue import intents
from ml.guardrails import crisis_check, validate
from ml.guardrails.lexicons.prohibitions import MAX_CHARS, PROHIBITED

ASK = intents.ASK_IMMEDIATE_SAFETY


class TestValidatorAccepts(unittest.TestCase):
    def test_a_plain_rephrasing_of_the_licensed_question_passes(self):
        result = validate("Are you safe where you are right now?", ASK, "en")
        self.assertTrue(result["ok"], result["reason"])

    def test_hindi_rephrasing_passes(self):
        result = validate("क्या आप अभी सुरक्षित हैं?", ASK, "hi")
        self.assertTrue(result["ok"], result["reason"])

    def test_acknowledgement_without_a_question_passes(self):
        result = validate("Thank you for telling me.", intents.ACKNOWLEDGE, "en")
        self.assertTrue(result["ok"], result["reason"])


class TestValidatorRejects(unittest.TestCase):
    def assert_rejected(self, text, intent=ASK, lang="en", reason_prefix=None):
        result = validate(text, intent, lang)
        self.assertFalse(result["ok"], msg=f"accepted: {text!r}")
        self.assertTrue(result["safe_text"], msg="a rejection must supply a fallback")
        if reason_prefix:
            self.assertTrue(result["reason"].startswith(reason_prefix), result["reason"])
        return result

    def test_empty_output_is_rejected(self):
        self.assert_rejected("", reason_prefix="empty_output")
        self.assert_rejected(None, reason_prefix="empty_output")
        self.assert_rejected("   ", reason_prefix="empty_output")

    def test_two_questions_are_rejected(self):
        self.assert_rejected("Are you safe? Who was it?", reason_prefix="multiple_questions")

    def test_overlong_output_is_rejected(self):
        self.assert_rejected("Are you safe? "[:1] + "a" * (MAX_CHARS + 5), reason_prefix="too_long")

    def test_acknowledge_may_not_ask_anything(self):
        self.assert_rejected("Go on, what happened next?", intent=intents.ACKNOWLEDGE,
                             reason_prefix="unlicensed_question")

    def test_question_intent_must_still_ask(self):
        self.assert_rejected("You are safe now.", reason_prefix="licensed_question_missing")

    def test_assessment_vocabulary_never_reaches_the_victim(self):
        self.assert_rejected("Your risk band is high, are you safe?",
                             reason_prefix="leaks_assessment")
        self.assert_rejected("Your SVI is elevated, are you safe?",
                             reason_prefix="leaks_assessment")

    def test_urls_phone_numbers_and_ids_are_rejected(self):
        self.assert_rejected("Visit https://example.org, are you safe?", reason_prefix="contains_url")
        self.assert_rejected("Call 011 2345 6789, are you safe?", reason_prefix="contains_phone")
        self.assert_rejected("Your number is 123456789012, are you safe?",
                             reason_prefix="contains_long_id")

    def test_percentages_and_markup_are_rejected(self):
        self.assert_rejected("I am 90% sure, are you safe?", reason_prefix="contains_percentage")
        self.assert_rejected("<p>Are you safe?</p>", reason_prefix="contains_markup")

    def test_lists_are_rejected(self):
        self.assert_rejected("Are you safe?\n1. tell me more", reason_prefix="contains_list")

    def test_fixed_script_intents_cannot_be_validated_through_this_path(self):
        result = validate("Anything at all.", intents.CRISIS_SCRIPT, "en")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "intent_is_fixed_script")
        self.assertIsNone(result["safe_text"])

    def test_unknown_intent_is_rejected(self):
        result = validate("Are you safe?", "improvise_something", "en")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "unknown_intent")


class TestEveryProhibitionInBothLanguages(unittest.TestCase):
    """One marker per prohibition per language must be caught."""

    def test_each_prohibition_has_markers_in_both_languages(self):
        for reason, (markers_en, markers_hi) in PROHIBITED.items():
            self.assertTrue(markers_en, msg=f"{reason} has no English markers")
            self.assertTrue(markers_hi, msg=f"{reason} has no Hindi markers")

    def test_each_marker_is_rejected(self):
        for reason, (markers_en, markers_hi) in PROHIBITED.items():
            for lang, markers in (("en", markers_en), ("hi", markers_hi)):
                for marker in markers:
                    text = f"{marker} are you safe?"
                    result = validate(text, ASK, lang)
                    self.assertFalse(result["ok"], msg=f"{reason}/{lang}: accepted {text!r}")
                    self.assertTrue(
                        result["reason"].startswith(reason),
                        msg=f"{text!r} rejected as {result['reason']}, expected {reason}",
                    )

    def test_rejection_returns_the_prewritten_fallback_not_a_repair(self):
        result = validate("Please calm down, are you safe?", ASK, "en")
        self.assertFalse(result["ok"])
        self.assertEqual(result["safe_text"], intents.fallback_text(ASK, "en"))


class TestCrisisPrecheck(unittest.TestCase):
    def test_english_first_person_crisis_fires(self):
        self.assertTrue(crisis_check("I want to die, there is no point")["crisis"])
        self.assertTrue(crisis_check("I am going to kill myself tonight")["crisis"])

    def test_hindi_crisis_fires(self):
        self.assertTrue(crisis_check("मैं आत्महत्या कर लूंगी")["crisis"])

    def test_hinglish_crisis_fires(self):
        self.assertTrue(crisis_check("main jaan de dungi ab")["crisis"])

    def test_negated_crisis_language_does_not_fire_but_is_recorded(self):
        result = crisis_check("I would never kill myself, I want help")
        self.assertFalse(result["crisis"])
        self.assertTrue(result["suppressed"])

    def test_a_third_party_threat_is_not_crisis_lexicon_material(self):
        # This is a D1/D3 threat, scored by the detectors, not the crisis lexicon.
        result = crisis_check("He said he would kill me if I complain")
        self.assertFalse(result["crisis"])
        self.assertEqual(result["matches"], [])

    def test_crisis_language_attributed_to_another_person_still_fires(self):
        # Recall-first: being told to kill yourself is a crisis, not a quotation
        # to be filtered out.
        result = crisis_check("He told me to kill myself")
        self.assertTrue(result["crisis"])
        self.assertEqual(result["matches"][0].get("context"), "attributed_to_third_party")

    def test_ordinary_utterance_does_not_fire(self):
        self.assertFalse(crisis_check("They stopped me from using the water tap")["crisis"])

    def test_empty_input_is_safe(self):
        self.assertFalse(crisis_check("")["crisis"])
        self.assertFalse(crisis_check(None)["crisis"])

    def test_matching_is_case_insensitive(self):
        self.assertTrue(crisis_check("I WANT TO DIE")["crisis"])


if __name__ == "__main__":
    unittest.main()
