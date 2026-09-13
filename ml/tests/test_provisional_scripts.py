"""Task 5D-L provisional fixed scripts: exact packet text, hashes, labels, templating.

Standard library only. The texts are provisional, unreviewed and local-demo only;
these tests prove they cannot become approved scripts by accident.
"""

import ast
import hashlib
import re
import unittest
from pathlib import Path

from ml.assessment import assess
from ml.dialogue import next as dialogue_next
from ml.dialogue.scripts import SCRIPTS, provisional, text_for, unwritten
from ml.dialogue.scripts.fixed_scripts import NOT_WRITTEN
from ml.dialogue.states import State
from ml.tests.source_scan import iter_source_files

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent
PACKET = REPO / provisional.SOURCE_PACKET

PACKET_HASHES = {
    "S0:en": "8296a38a8dde4a9cc1480b82cdc57ec97f3b3421acba49875aebbab38d8e7de2",
    "S0:hi": "8bf8bed902cd53a2dae73c31cb1e31422049db92f6e3e08f4ae585e9b2efedc5",
    "SH:en": "d883bbddf6975370f68a6529b745a459c1f3fd033160c3a09ac22fa789c981c9",
    "SH:hi": "da39efc28d4f22c2c967c1f383bb2b8bb7dabdc158f574f91ea95010cda35de8",
    "SX:en": "2e8aad0e51696f6789b7ba57db3b34483c7a812029e55a460f1d6933ed3ad8c5",
    "SX:hi": "68a40e233eb01a1a12592c559487c9520f8f70fb402e6233c5917ec09f473b9b",
    "S9:en": "dc3094445f87503a1cd1541d9cf427630ea45a25463ccb94838bf50a6fee1349",
    "S9:hi": "fccc6bfeb3f0ffc11bf1c314ce4ac13608a382d5702c7f8866a8e75141b4509a",
}


def packet_blocks():
    doc = PACKET.read_text(encoding="utf-8")
    out = {}
    for section in re.split(r"(?m)^## ", doc)[1:]:
        state = section.split(" ", 1)[0]
        for word, lang in (("English", "en"), ("Hindi", "hi")):
            m = re.search(rf"### Exact proposed {word} wording\n\n```text\n(.*?)\n```\n\nSHA-256: `([0-9a-f]{{64}})`",
                          section, re.S)
            if m:
                out[f"{state}:{lang}"] = (m.group(1), m.group(2))
    return out


class TestExactPacketCopy(unittest.TestCase):
    def test_all_eight_records_exist_and_verify(self):
        self.assertEqual(set(provisional.PROVISIONAL_SCRIPTS), set(PACKET_HASHES))
        self.assertTrue(provisional.all_verified())

    def test_every_text_is_byte_identical_to_the_tracked_packet(self):
        blocks = packet_blocks()
        self.assertEqual(set(blocks), set(PACKET_HASHES))
        for key, (text, recorded) in blocks.items():
            record = provisional.PROVISIONAL_SCRIPTS[key]
            self.assertEqual(recorded, PACKET_HASHES[key], key)
            self.assertEqual(record.sha256, PACKET_HASHES[key], key)
            self.assertEqual(record.text, text, key)
            self.assertEqual(hashlib.sha256(record.text.encode("utf-8")).hexdigest(), recorded, key)

    def test_any_change_to_a_text_fails_verification(self):
        for key, record in provisional.PROVISIONAL_SCRIPTS.items():
            for mutated in (record.text + " ", record.text[:-1], record.text.replace(".", ",", 1),
                            record.text.replace("।", ".", 1)):
                if mutated == record.text:
                    continue
                self.assertFalse(provisional.ProvisionalScript(record.state, record.lang, mutated,
                                                               record.sha256).verified(), key)

    def test_language_and_placeholder_shape(self):
        for key, record in provisional.PROVISIONAL_SCRIPTS.items():
            body = record.text.replace(provisional.REFERENCE_TOKEN, "")
            self.assertNotIn("{", body, key)
            self.assertNotIn("}", body, key)
            self.assertEqual(record.text.count(provisional.REFERENCE_TOKEN),
                             1 if record.state is State.S9_CLOSING else 0, key)
            if record.lang == "en":
                self.assertTrue(body.isascii(), key)
            else:  # formal Hindi, no Hinglish: no Latin letters outside the token
                self.assertIsNone(re.search(r"[A-Za-z]", body), key)
            self.assertIsNone(re.search(r"\d|https?:|www\.|14566|NHAA", record.text), key)


class TestLabelsAndGates(unittest.TestCase):
    def test_labels_are_provisional_unreviewed_local_demo_text_only(self):
        self.assertEqual(provisional.STATUS, "PROVISIONAL_UNREVIEWED")
        self.assertIs(provisional.LOCAL_DEMO_ONLY, True)
        self.assertEqual(provisional.TURN_REVIEW_STATUS, "provisional_unreviewed")
        self.assertEqual(provisional.AUDIO, "none")
        self.assertIs(provisional.AUDIO_READY, False)

    def test_no_reviewer_approval_or_date_is_recorded(self):
        self.assertEqual(provisional.ProvisionalScript.__slots__, ("state", "lang", "text", "sha256"))
        source = (ML / "dialogue" / "scripts" / "provisional.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b20\d\d-\d\d-\d\d\b", source))
        self.assertNotIn("APPROVED", source.replace("NOT approved", ""))
        self.assertNotIn("reviewer=", source)

    def test_the_approval_registry_is_untouched_and_fails_closed(self):
        self.assertEqual(len(unwritten()), 8)
        for key, record in SCRIPTS.items():
            self.assertEqual(record.status, NOT_WRITTEN, key)
            self.assertIsNone(record.text, key)
            self.assertIsNone(record.reviewer, key)
            self.assertIsNone(record.audio_asset, key)
        for state in provisional.STATES:
            for lang in provisional.LANGS:
                self.assertIsNone(text_for(state, lang))

    def test_the_policy_still_reports_every_fixed_script_unavailable(self):
        cases = (
            (None, {}, {"lang": "en"}),
            ("S1", {}, {"lang": "hi", "crisis": True}),
            ("S1", {}, {"lang": "en", "request_human": True}),
            ("S9", {}, {"lang": "en"}),
        )
        for state, slots, flags in cases:
            decision = dialogue_next(state, slots, "", flags)
            self.assertTrue(decision["fixed_script"])
            self.assertFalse(decision["script_available"])
            self.assertIsNone(decision["fallback_text"])

    def test_script_for_returns_only_verified_records(self):
        self.assertIsNotNone(provisional.script_for(State.S0_OPENING, "en"))
        self.assertIsNone(provisional.script_for(State.S1_FREE_NARRATIVE, "en"))
        self.assertIsNone(provisional.script_for(State.S0_OPENING, "fr"))
        self.assertIsNone(provisional.script_for(State.S0_OPENING, "hinglish"))


class TestClosingTemplate(unittest.TestCase):
    TEMPLATE = provisional.PROVISIONAL_SCRIPTS["S9:en"].text

    def test_a_valid_reference_fills_the_single_slot(self):
        for lang in provisional.LANGS:
            template = provisional.PROVISIONAL_SCRIPTS[f"S9:{lang}"].text
            rendered = provisional.render_closing(template, "SAH-0A1B2C")
            self.assertEqual(rendered, template.replace("{reference_no}", "SAH-0A1B2C"))
            self.assertEqual(rendered.count("SAH-0A1B2C"), 1)

    def test_malformed_references_are_refused(self):
        for bad in ("", "SAH-0a1b2c", "SAH-0A1B2", "SAH-0A1B2C3", " SAH-0A1B2C", "SAH-0A1B2C\n", "SAH-0A1B2G",
                    "SAH-{reference_no}", "sah-0A1B2C", "SAH-0A1B2C.", "SAH-2026-00000001", None, 123):
            self.assertIsNone(provisional.render_closing(self.TEMPLATE, bad), repr(bad))

    def test_templates_without_exactly_one_token_or_with_other_braces_are_refused(self):
        token = provisional.REFERENCE_TOKEN
        for bad in ("No token here.", f"{token} and {token}", f"{token} {{lang}}", f"{token} }}", None):
            self.assertIsNone(provisional.render_closing(bad, "SAH-0A1B2C"), repr(bad))

    def test_non_closing_texts_cannot_be_templated(self):
        for key, record in provisional.PROVISIONAL_SCRIPTS.items():
            if record.state is not State.S9_CLOSING:
                self.assertIsNone(provisional.render_closing(record.text, "SAH-0A1B2C"), key)


class TestFirewall(unittest.TestCase):
    def test_the_module_is_pure_and_imports_no_model(self):
        tree = ast.parse((ML / "dialogue" / "scripts" / "provisional.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * node.level + (node.module or ""))
        self.assertEqual(imported, {"hashlib", "re", "typing", "..states"})

    def test_no_ml_module_selects_the_provisional_texts(self):
        pattern = re.compile(r"\bprovisional\b")
        users = [p.relative_to(ML).as_posix() for p in iter_source_files(ML)
                 if "tests" not in p.parts and p.name != "provisional.py"
                 and pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(users, [])

    def test_the_backend_service_is_the_only_product_consumer_and_uses_no_model(self):
        app = REPO / "backend" / "app"
        users = sorted(p.relative_to(app).as_posix() for p in iter_source_files(app)
                       if "scripts import provisional" in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["services/fixed_scripts.py"])
        service = (app / "services" / "fixed_scripts.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*(from|import)\s+\S*(llm|runtime|shadow|training|whisper|muril|"
                                    r"assessment|detectors|tts)\b", service))

    def test_assessment_ignores_provisional_assistant_turns(self):
        victim = [{"id": "v1", "speaker": "victim", "text": "Fictional note about a bus pass form.", "state": "S1"}]
        shown = victim + [{"id": f"a{i}", "speaker": "assistant", "text": r.text, "state": r.state.value}
                          for i, r in enumerate(provisional.PROVISIONAL_SCRIPTS.values())]
        self.assertEqual(assess(victim, True, channel="mobile_chat"), assess(shown, True, channel="mobile_chat"))


if __name__ == "__main__":
    unittest.main()
