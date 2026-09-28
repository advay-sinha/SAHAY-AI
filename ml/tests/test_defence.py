"""Judge-defence pages and component cards (plan M16): generated from results, and worded honestly."""

import json
import unittest
from pathlib import Path

from ml.eval import defence, table

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "ml" / "eval" / "results"
CARDS = [
    "ml/nlp/DETECTORS_CARD.md", "ml/svi/SVI_CARD.md", "ml/guardrails/VALIDATOR_CARD.md", "ml/voice/ASR_CARD.md",
    "ml/tts/TTS_CARD.md", "ml/acoustics/D4_CARD.md", "ml/ser/MODEL_CARD.md", "ml/textaffect/MODEL_CARD.md",
    "ml/shadow/MODEL_CARD.md", "ml/training/STAGE_W_CARD.md",
    "docs/defence/LIMITATIONS.md", "docs/defence/JUDGE_QA.md", "docs/defence/README.md",
    "docs/defence/NUMBERS.md", "docs/defence/RED_TEAM.md",
]
#: Phrases that may appear only when explicitly negated ("not clinically validated", "No, and we don't").
NEGATION_OK = ("not ", "no ", "never ", "don't", "without", "prohibited", "claims of", "claim ")


class TestWording(unittest.TestCase):
    def test_every_card_and_page_exists(self):
        for rel in CARDS:
            self.assertTrue((REPO / rel).is_file(), rel)

    def test_no_unqualified_claim(self):
        for rel in CARDS:
            text = (REPO / rel).read_text(encoding="utf-8").casefold()
            for phrase in table.BANNED_PHRASES:
                start = text.find(phrase)
                while start != -1:
                    before = text[max(0, start - 60):start]
                    self.assertTrue(any(n in before for n in NEGATION_OK), f"{rel}: {phrase!r} unqualified")
                    start = text.find(phrase, start + 1)

    def test_official_is_never_used_as_a_claim_while_locked_is_empty(self):
        # Generated pages pass the strict guard; the written Q&A may quote a claim only to deny it
        # (checked above), but must not call any number official.
        for rel in ("docs/defence/NUMBERS.md", "docs/defence/RED_TEAM.md"):
            table.check_wording((REPO / rel).read_text(encoding="utf-8"), 0)
        qa = (REPO / "docs/defence/JUDGE_QA.md").read_text(encoding="utf-8").casefold()
        self.assertNotRegex(qa, r"\bofficial\b")


class TestGenerated(unittest.TestCase):
    def setUp(self):
        evals = sorted(RESULTS.glob("eval-20*.json"))
        tables = sorted(RESULTS.glob("eval-table-*.json"))
        self.report = json.loads(evals[-1].read_text(encoding="utf-8"))
        self.table = json.loads(tables[-1].read_text(encoding="utf-8"))

    def test_red_team_totals_match_the_report(self):
        page = defence.red_team(self.report)
        rt = self.report["redteam"]
        self.assertIn(f"{rt['passed']} of {rt['cases']} cases blocked", page)
        for lang, s in rt["by_language"].items():
            self.assertIn(f"| {defence.LANG_NAMES.get(lang, lang)} | {s['cases']} |", page)

    def test_numbers_page_is_aggregate_only_and_marks_pending(self):
        page = defence.numbers(self.report, self.table)
        self.assertIn("Locked-set metrics: **pending**", page)
        self.assertIn("## Not measured yet", page)
        self.assertNotIn('"text"', page)
        table.check_wording(page, int(self.table.get("locked_samples") or 0))


if __name__ == "__main__":
    unittest.main()
