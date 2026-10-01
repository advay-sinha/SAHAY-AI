"""Content checks for every written fixed script (S0, S9, SX, SH).

Fixed scripts never pass through the generated-text validator, so these tests
hold them to the same content rules directly, in both languages, whatever
their review status. Standard library only.
"""

import unittest

from ml.dialogue.scripts.fixed_scripts import DRAFT_TEXT, REQUIRED_CONTENT, SCRIPTS
from ml.dialogue.states import State
from ml.guardrails import crisis_check
from ml.guardrails import rules
from ml.guardrails.banned_patterns import BANNED
from ml.guardrails.validator import _prohibited_hit

WRITTEN = {key: record for key, record in SCRIPTS.items() if record.text}


class TestFixedScriptContent(unittest.TestCase):
    def test_every_script_is_written_in_both_languages(self):
        for state in REQUIRED_CONTENT:
            for lang in ("hi", "en"):
                self.assertIn(f"{state.value}:{lang}", WRITTEN)

    def test_no_banned_pattern_prohibition_or_phrase_rule(self):
        for key, record in WRITTEN.items():
            with self.subTest(key=key):
                self.assertEqual([r for r, p in BANNED.items() if p.search(record.text)], [])
                self.assertIsNone(_prohibited_hit(record.text, record.lang))
                self.assertIsNone(rules.check(record.text))

    def test_no_script_asks_a_question(self):
        for key, record in WRITTEN.items():
            self.assertNotIn("?", record.text, msg=key)

    def test_no_script_trips_the_crisis_precheck(self):
        for key, record in WRITTEN.items():
            self.assertFalse(crisis_check(record.text)["crisis"], msg=key)

    def test_opening_discloses_ai_and_the_right_to_a_person(self):
        self.assertIn("AI assistant, not a person", DRAFT_TEXT["S0:en"])
        self.assertIn("talk to a person at any time", DRAFT_TEXT["S0:en"])
        self.assertIn("एआई सहायक", DRAFT_TEXT["S0:hi"])
        self.assertIn("कभी भी", DRAFT_TEXT["S0:hi"])

    def test_crisis_script_stays_minimal(self):
        # Acknowledge, connect to a person, ask them to stay. Nothing else.
        for lang in ("hi", "en"):
            text = DRAFT_TEXT[f"SX:{lang}"]
            self.assertLessEqual(text.count("।") + text.count("."), 3, msg=lang)
            self.assertLess(len(text), 120, msg=lang)

    def test_closing_promises_no_timeline_or_callback(self):
        for word in ("hour", "day", "call you", "will contact", "arrest", "compensation"):
            self.assertNotIn(word, DRAFT_TEXT["S9:en"].lower())

    def test_a_script_that_is_not_approved_is_not_speakable(self):
        for key, record in SCRIPTS.items():
            if record.status != "APPROVED":
                self.assertFalse(record.speakable, msg=key)

    def test_states_cover_every_fixed_script(self):
        self.assertEqual(
            set(REQUIRED_CONTENT),
            {State.S0_OPENING, State.S9_CLOSING, State.SX_CRISIS, State.SH_HUMAN_HANDOFF},
        )


if __name__ == "__main__":
    unittest.main()
