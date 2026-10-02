"""Meaning check for English rewordings and the Hinglish register (EXT-132)."""

import unittest

from ml.dialogue import intents
from ml.dialogue.hinglish import to_hinglish_register
from ml.guardrails.validator import validate
from ml.llm.meaning import keeps_meaning

QUESTION_INTENTS = sorted(intents.REPHRASABLE_INTENTS - {intents.ACKNOWLEDGE})


class TestMeaning(unittest.TestCase):
    def test_every_approved_english_source_keeps_its_own_meaning(self):
        for intent in intents.REPHRASABLE_INTENTS:
            source = intents.licensed_question(intent, "en") or intents.fallback_text(intent, "en")
            self.assertTrue(keeps_meaning(source, intent), intent)

    def test_no_approved_question_passes_as_another(self):
        for intent in QUESTION_INTENTS:
            source = intents.licensed_question(intent, "en")
            for other in QUESTION_INTENTS:
                if other != intent:
                    self.assertFalse(keeps_meaning(source, other), f"{intent} passes as {other}")

    def test_measured_drift_and_added_requests_are_rejected(self):
        self.assertFalse(keeps_meaning("Did you hear anything, and what time was it?", intents.ASK_WHO_AND_WHEN))
        self.assertFalse(keeps_meaning("Are you safe, and does anyone need medical help?",
                                       intents.ASK_IMMEDIATE_SAFETY))
        self.assertFalse(keeps_meaning("Do you need medical help right now?", intents.ASK_WHAT_THEY_WANT))
        self.assertFalse(keeps_meaning("", intents.ASK_MEDICAL_NEED))
        # Measured live 2026-10-02: narrows "anyone" to "you", dropping injured family members.
        self.assertFalse(keeps_meaning("Do you need medical help right now?", intents.ASK_MEDICAL_NEED))
        self.assertTrue(keeps_meaning("Does anyone there need medical help now?", intents.ASK_MEDICAL_NEED))
        self.assertFalse(keeps_meaning("Anything", "unknown_intent"))
        # Whole-word matching (2026-10-02 safety review): no stem inside another word.
        self.assertFalse(keeps_meaning("Is this the first time, and do you have a lawyer?",
                                       intents.ASK_EXISTING_ACTION))
        self.assertFalse(keeps_meaning("Whose fault was it, and when did this happen?", intents.ASK_WHO_AND_WHEN))
        self.assertFalse(keeps_meaning("There is no need to say more.", intents.ACKNOWLEDGE))

    def test_measured_faithful_rewordings_are_accepted(self):
        for text, intent in (
            ("Do you have someone with you right now?", intents.ASK_SUPPORT_NETWORK),
            ("What kind of help would you like right now?", intents.ASK_WHAT_THEY_WANT),
            ("Who was involved and when did this happen?", intents.ASK_WHO_AND_WHEN),
            ("Are the threats still going on — has anyone told you not to speak up?",
             intents.ASK_ONGOING_THREAT),
        ):
            self.assertTrue(keeps_meaning(text, intent), text)


class TestHinglishRegister(unittest.TestCase):
    def test_every_approved_hindi_sentence_becomes_valid_latin_script(self):
        for intent in intents.REPHRASABLE_INTENTS:
            source = intents.licensed_question(intent, "hi") or intents.fallback_text(intent, "hi")
            roman = to_hinglish_register(source)
            self.assertFalse(any(0x0900 <= ord(c) <= 0x097F for c in roman), roman)
            self.assertTrue(validate(roman, intent, "hi")["ok"], roman)

    def test_everyday_spellings_and_sentence_capitals(self):
        self.assertEqual(to_hinglish_register("बताने के लिए धन्यवाद। आप कहिए।"),
                         "Bataane ke liye dhanyavaad. Aap kahiye.")
        self.assertIn("FIR", to_hinglish_register("क्या कोई एफ़आईआर दर्ज हुई है?"))


if __name__ == "__main__":
    unittest.main()


class TestReviewedWordings(unittest.TestCase):
    def test_pinned_hinglish_equals_the_transliterated_approved_hindi(self):
        from ml.dialogue import variants

        for intent, pinned in variants.HINGLISH_TEXT.items():
            source = intents.licensed_question(intent, "hi") or intents.fallback_text(intent, "hi")
            self.assertEqual(to_hinglish_register(source), pinned, intent)
        self.assertEqual(set(variants.HINGLISH_TEXT), set(intents.REPHRASABLE_INTENTS))

    def test_every_reviewed_wording_passes_the_checks(self):
        from ml.dialogue import variants

        for intent, text in variants.HINGLISH_TEXT.items():
            self.assertTrue(validate(text, intent, "hi")["ok"], text)
        for intent, texts in variants.EN_VARIANTS.items():
            for text in texts:
                self.assertTrue(validate(text, intent, "en")["ok"], text)
                self.assertTrue(keeps_meaning(text, intent), text)

    def test_nothing_unapproved_is_offered(self):
        from unittest.mock import patch

        from ml.dialogue import variants

        with patch.dict(variants.VARIANT_REVIEW, {"status": "DRAFT_UNREVIEWED"}), \
                patch.dict(variants.HINGLISH_REVIEW, {"status": "DRAFT_UNREVIEWED"}):
            self.assertIsNone(variants.english_variant(intents.ASK_MEDICAL_NEED))
            self.assertIsNone(variants.hinglish_text(intents.ASK_MEDICAL_NEED))
        with patch.dict(variants.HINGLISH_REVIEW, {"status": "APPROVED", "reviewer": "", "review_date": ""}):
            self.assertIsNone(variants.hinglish_text(intents.ASK_MEDICAL_NEED), "approval needs a named reviewer")
