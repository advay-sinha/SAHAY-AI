"""D5 lexicon v1.1 (draft): anxiety and low-mood indicators (plan M10, Problem Statement coverage).

All sentences are short, fictional and written for this test. They check that the new terms
fire on first-person anxiety and low-mood phrasing in English, Hinglish and Hindi; that a nearby
negation cancels them; that common near-misses do not fire; and that D5 never overlaps the
crisis lexicon, which alone owns D2.
"""

import unittest

from ml.guardrails import crisis_check
from ml.guardrails.lexicons import crisis as crisis_lex
from ml.nlp import lexicons
from ml.nlp.detectors import match_turn

HITS = {
    "en": ["I keep having panic attacks since that night.", "I can't stop worrying about my son.",
           "I have lost interest in everything.", "I cry every day now.", "I feel numb most days.",
           "I stopped eating after they came."],
    "hinglish": ["Mujhe bahut ghabrahat hoti hai raat ko.", "Man nahi lagta kisi kaam mein.",
                 "Main roz roti hoon.", "Bhookh nahi lagti ab.", "Dil ghabrata rehta hai."],
    "hi": ["मुझे घबराहट होती है।", "मन नहीं लगता किसी काम में।", "रोज़ रोती हूँ।", "भूख नहीं लगती।",
           "बहुत बेचैनी रहती है।"],
}
NEGATED = ["I don't have panic attacks.", "I am not anxious anymore.", "Mujhe ghabrahat nahi hoti.",
           "मुझे घबराहट नहीं होती।"]
NEAR_MISSES = ["Don't worry about me.", "Chinta mat karo, sab theek hoga.", "Police ne bahut pareshan kiya.",
               "There was tension on the rope.", "Unhone kaha ki tension mat lo.", "The panic button is by the door.",
               "Please eat something first."]


class TestD5AnxietyLowMood(unittest.TestCase):
    def test_first_person_phrasing_fires_in_every_language(self):
        for lang, texts in HITS.items():
            for text in texts:
                self.assertIsNotNone(match_turn("D5", text), (lang, text))

    def test_negation_cancels(self):
        for text in NEGATED:
            self.assertIsNone(match_turn("D5", text), text)

    def test_near_misses_do_not_fire(self):
        for text in NEAR_MISSES:
            self.assertIsNone(match_turn("D5", text), text)

    def test_tiers_stay_below_severe(self):
        # Anxiety and low mood are tier 1-2 indicators; tier 3 stays reserved for other dimensions.
        self.assertTrue(all(tier <= 2 for _, tier in lexicons.LEXICONS["D5"]))

    def test_no_overlap_with_the_crisis_lexicon(self):
        crisis_terms = [t.casefold() for t in crisis_lex.CRISIS_EN + crisis_lex.CRISIS_HI + crisis_lex.CRISIS_HINGLISH]
        for term, _ in lexicons.LEXICONS["D5"]:
            for c in crisis_terms:
                self.assertNotIn(term.casefold(), c, (term, c))
                self.assertNotIn(c, term.casefold(), (term, c))

    def test_low_mood_is_not_crisis_and_crisis_still_fires(self):
        for texts in HITS.values():
            for text in texts:
                self.assertFalse(crisis_check(text)["crisis"], text)
        self.assertTrue(crisis_check("I have nothing left to live for.")["crisis"])

    def test_no_diagnostic_words_in_the_lexicon(self):
        for term, _ in lexicons.LEXICONS["D5"]:
            for word in ("depress", "ptsd", "disorder", "anxiety disorder", "trauma", "mental illness"):
                self.assertNotIn(word, term.casefold(), term)

    def test_version_marks_the_lexicon_unreviewed(self):
        self.assertTrue(lexicons.LEXICON_VERSION.endswith("draft"))


if __name__ == "__main__":
    unittest.main()
