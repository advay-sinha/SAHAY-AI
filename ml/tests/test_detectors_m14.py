"""Detector drafts v1.2 (plan M14): P-DET-6 misspelt imminent return, P-DET-3 conditional clauses.

Every sentence here is short, fictional and written for this test, alongside the rules. That
makes them development evidence, not holdout evidence (ml/eval/CONTAMINATION.md). The exposed
fixtures DEV-EN-022 and CAND-HG-004 are regression targets only.
"""

import unittest

from ml.assessment import assess
from ml.eval import contamination
from ml.guardrails import crisis_check
from ml.nlp import lexicons
from ml.nlp.detectors import match_turn, normalise_spelling

RETURN_TONIGHT = {
    "en": ["They said they will come back tonight.", "He is coming back tonight with his brothers.",
           "they wil come back tonite", "They'll come back 2nite, he said."],
    "hinglish": ["Woh aaj raat wapas aayenge.", "Bole aaj raat phir aayenge.", "woh aaj raat wapis ayenge"],
    "hi": ["वे आज रात वापस आएंगे।", "उन्होंने कहा आज रात फिर आएंगे।"],
}
RETURN_NOT_IMMINENT = [
    "They didn't come back tonight.",          # negated
    "If they don't come back tonight we can sleep.",  # conditional return is not a claim of danger (D1)
    "My son will come back tonight from the city.",   # "come back tonight" fires; see test below
]
CONDITIONAL_COERCION = {
    "en": ["If you don't withdraw the complaint, they will burn the house.",
           "Unless you take back the complaint they said you will suffer."],
    "hinglish": ["Agar complaint wapas nahi li to jaan se maar denge.", "Shikayat wapas nahi li toh dekh lena.",
                 "Complaint wapas lo nahi to maar denge."],
    "hi": ["अगर शिकायत वापस नहीं ली तो जान से मार देंगे।", "शिकायत वापस नहीं ली तो अंजाम बुरा होगा।"],
}
PLAIN_NEGATION_STAYS = [
    "Maine complaint wapas nahi li.",
    "They did not threaten us.",
    "मैंने शिकायत वापस नहीं ली।",
    "शिकायत वापस नहीं ली तोड़फोड़ के बाद भी",  # "तो" must be a whole word, never inside "तोड़"
]


class TestSpellingMap(unittest.TestCase):
    def test_whole_words_only(self):
        self.assertEqual(normalise_spelling("they wil come back tonite"), "they will come back tonight")
        self.assertEqual(normalise_spelling("wildlife willow tonites"), "wildlife willow tonites")
        self.assertEqual(normalise_spelling("woh wapis ayenge"), "woh wapas aayenge")

    def test_map_is_explicit_ascii_and_never_introduces_negation(self):
        for variant, canonical in lexicons.SPELLING_VARIANTS.items():
            self.assertTrue(variant.isascii() and variant == variant.casefold(), variant)
            self.assertNotEqual(variant, canonical)
            for neg in lexicons.NEGATIONS_BEFORE + lexicons.NEGATIONS_AFTER:
                self.assertNotIn(neg.strip(), canonical.split(), (variant, canonical))

    def test_spelling_map_never_touches_the_crisis_precheck(self):
        # The crisis pre-check keeps its own reviewed normalisation; the detector map is separate.
        self.assertFalse(crisis_check("they wil come back tonite")["crisis"])


class TestReturnTonight(unittest.TestCase):
    def test_fires_as_imminent_in_every_language(self):
        for lang, texts in RETURN_TONIGHT.items():
            for text in texts:
                found = match_turn("D1", text)
                self.assertIsNotNone(found, (lang, text))
                self.assertEqual(found[0], 3, (lang, text))

    def test_negated_and_conditional_returns_do_not_fire(self):
        for text in RETURN_NOT_IMMINENT[:2]:
            self.assertIsNone(match_turn("D1", text), text)
        self.assertNotIn("D1", lexicons.CONDITIONAL_NEGATION_EXEMPT)

    def test_known_limitation_benign_return_fires(self):
        # Documented false positive (review packet §4): the lexicon cannot tell who returns.
        self.assertEqual(match_turn("D1", RETURN_NOT_IMMINENT[2])[0], 3)

    def test_regression_target_routes_critical(self):
        turns = [{"id": "t1", "speaker": "victim", "text": "They threatend us and said they wil come back tonite."}]
        result = assess(turns, True, channel="mobile_chat")
        self.assertEqual(result["band"], "Critical")
        self.assertIn("DEV-EN-022", contamination.REGRESSION_TARGETS_M14)
        self.assertIn("regression_only", contamination.classify("DEV-EN-022")["classes"])


class TestConditionalCoercion(unittest.TestCase):
    def test_conditional_negation_does_not_cancel_coercion(self):
        for lang, texts in CONDITIONAL_COERCION.items():
            for text in texts:
                self.assertIsNotNone(match_turn("D3", text), (lang, text))

    def test_plain_negation_still_cancels(self):
        for text in PLAIN_NEGATION_STAYS:
            self.assertIsNone(match_turn("D3", text), text)

    def test_conditional_coercion_raises_the_coercion_alert(self):
        turns = [{"id": "t1", "speaker": "victim", "text": "Agar complaint wapas nahi li to jaan se maar denge."}]
        alerts = assess(turns, True, channel="mobile_chat")["alerts"]
        self.assertIn("coercion", [a["type"] for a in alerts])
        self.assertIn("CAND-HG-004", contamination.REGRESSION_TARGETS_M14)

    def test_exemption_is_d3_only(self):
        self.assertEqual(lexicons.CONDITIONAL_NEGATION_EXEMPT, frozenset({"D3"}))


class TestVersion(unittest.TestCase):
    def test_version_marks_the_draft(self):
        self.assertEqual(lexicons.LEXICON_VERSION, "detectors-v1.2-draft")


if __name__ == "__main__":
    unittest.main()
