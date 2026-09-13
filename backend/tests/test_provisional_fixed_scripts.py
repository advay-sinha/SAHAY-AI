"""Task 5D-L: provisional, unreviewed, local-demo-only fixed scripts.

Default off. Refused outside APP_ENV development/test. Text only (PC-12
`audio:"none"`). `fixed_scripts_ready` stays false. All victim text here is
short, synthetic and fictional.
"""

import hashlib
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.tests.test_contract_decisions import DecisionBase
from backend.tests.test_vertical_slice import ASSESSMENT_KEYS, HAVE_DEPS, drain, recv_until

REPO = Path(__file__).resolve().parents[2]
PACKET = REPO / "docs" / "dialogue" / "FIXED_SCRIPTS_CANDIDATE_REVIEW.md"
CRISIS = "Ab aur nahi jee sakti, main jaan de dungi."
NARRATIVE = "Fictional test narrative about a form at the office."


def packet_texts():
    doc = PACKET.read_text(encoding="utf-8")
    out = {}
    for section in re.split(r"(?m)^## ", doc)[1:]:
        state = section.split(" ", 1)[0]
        for word, lang in (("English", "en"), ("Hindi", "hi")):
            m = re.search(rf"### Exact proposed {word} wording\n\n```text\n(.*?)\n```", section, re.S)
            if m:
                out[f"{state}:{lang}"] = m.group(1)
    return out


TEXTS = packet_texts()
ENABLED = SimpleNamespace(PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO=True, APP_ENV="test")


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class ProvisionalBase(DecisionBase):
    enabled = True

    def setUp(self):
        from backend.app.services import fixed_scripts

        if self.enabled:
            patcher = patch.object(fixed_scripts, "get_settings", return_value=ENABLED)
            patcher.start()
            self.addCleanup(patcher.stop)

    # -- service-level calls, so the outbound events can be inspected -------------
    def call(self, fn, *args):
        from backend.app.core.db import session_factory
        from backend.app.services import intake

        async def run():
            async with session_factory()() as db:
                result = await getattr(intake, fn)(db, *args)
                await db.commit()
            return result

        return self.client.portal.call(run)

    def create(self, consent="granted", lang="en"):
        session, case, out = self.call("create_session", "mobile_chat", consent, lang)
        return {"session_id": session.id, "case_id": case.id, "reference": case.reference, "lang": lang}, out

    def assistant_turns(self, session_id):
        return self.db("SELECT state, text, lang, intent, review_status, was_fallback, seq FROM turns "
                       "WHERE session_id=? AND speaker='assistant' ORDER BY seq", session_id)

    def audit_actions(self, case_id, action):
        return self.db("SELECT detail FROM audit_log WHERE case_id=? AND action=?", case_id, action)

    def turn_events(self, out):
        return [payload for kind, payload in out.events if kind == "assistant.turn"]


class TestProvisionalScriptsShown(ProvisionalBase):
    def test_s0_is_the_exact_packet_text_in_the_session_language_with_audio_none(self):
        for lang in ("en", "hi"):
            with self.subTest(lang=lang):
                s, out = self.create(lang=lang)
                [event] = self.turn_events(out)
                self.assertEqual(event["text"], TEXTS[f"S0:{lang}"])
                self.assertEqual(event["audio"], "none")
                self.assertEqual(event["intent"], "opening_script")
                self.assertEqual(set(event), {"turn_id", "text", "lang", "intent", "audio"})
                [row] = self.assistant_turns(s["session_id"])
                self.assertEqual(row, ("S0", TEXTS[f"S0:{lang}"], lang, "opening_script",
                                       "provisional_unreviewed", 0, 1))
                [detail] = self.audit_actions(s["case_id"], "fixed_script.provisional_shown")
                self.assertIn('"PROVISIONAL_UNREVIEWED"', detail[0])
                self.assertIn('"local_demo_only": true', detail[0])
                self.assertIn(hashlib.sha256(TEXTS[f"S0:{lang}"].encode()).hexdigest(), detail[0])
                self.assertNotIn(TEXTS[f"S0:{lang}"], detail[0])

    def test_s0_is_not_shown_without_granted_consent(self):
        for consent in ("pending", "declined"):
            with self.subTest(consent=consent):
                s, out = self.create(consent=consent)
                self.assertEqual(self.turn_events(out), [])
                self.assertEqual(self.assistant_turns(s["session_id"]), [])

    def test_sx_is_shown_once_and_crisis_routing_is_unchanged(self):
        for lang in ("en", "hi"):
            with self.subTest(lang=lang):
                s, _ = self.create(lang=lang)
                out = self.call("submit_turn", s["session_id"], CRISIS, lang)
                kinds = [kind for kind, _ in out.events]
                [event] = self.turn_events(out)
                self.assertEqual(event["text"], TEXTS[f"SX:{lang}"])
                self.assertEqual(event["audio"], "none")
                self.assertEqual(event["intent"], "crisis_script")
                self.assertIn("alert.safety", kinds)
                self.assertEqual(out.events[-1][1]["state"], "SX")
                self.assertEqual(self.db("SELECT band, takeover_requested_at IS NOT NULL FROM cases WHERE id=?",
                                         s["case_id"]), [("Critical", 1)])
                again = self.call("submit_turn", s["session_id"], "Fictional follow-up.", lang)
                self.assertEqual(self.turn_events(again), [])
                self.assertEqual(again.events[-1][1]["state"], "SX")
                self.assertEqual([r[0] for r in self.assistant_turns(s["session_id"])], ["S0", "SX"])

    def test_sh_is_shown_once_on_first_entry_and_never_over_sx(self):
        s, _ = self.create()
        out = self.call("request_human", s["session_id"], "h:1")
        [event] = self.turn_events(out)
        self.assertEqual(event["text"], TEXTS["SH:en"])
        self.assertEqual(event["audio"], "none")
        self.assertIn("No officer has joined", event["text"])
        self.assertEqual(self.turn_events(self.call("request_human", s["session_id"], "h:1")), [])
        self.assertEqual(self.turn_events(self.call("request_human", s["session_id"], "h:2")), [])

        crisis, _ = self.create()
        self.call("submit_turn", crisis["session_id"], CRISIS, "en")
        out = self.call("request_human", crisis["session_id"], "h:1")
        self.assertEqual(self.turn_events(out), [])
        self.assertEqual([r[0] for r in self.assistant_turns(crisis["session_id"])], ["S0", "SX"])

    def test_sh_is_not_shown_after_a_verified_takeover_or_without_granted_consent(self):
        s, _ = self.create()
        h = self.login("exec1")
        self.assertEqual(self.client.post(f"/cases/{s['case_id']}/claim", headers=h).status_code, 200)
        self.assertEqual(self.client.post(f"/cases/{s['case_id']}/takeover", headers=h).status_code, 200)
        self.assertEqual(self.turn_events(self.call("request_human", s["session_id"], "h:1")), [])
        for consent in ("pending", "declined"):
            other, _ = self.create(consent=consent)
            self.assertEqual(self.turn_events(self.call("request_human", other["session_id"], "h:1")), [])

    def test_s9_substitutes_only_the_sessions_own_persisted_reference(self):
        for lang in ("en", "hi"):
            with self.subTest(lang=lang):
                s, _ = self.create(lang=lang)
                self.call("submit_turn", s["session_id"], NARRATIVE, lang)
                case, out = self.call("end_session", s["session_id"])
                [event] = self.turn_events(out)
                expected = TEXTS[f"S9:{lang}"].replace("{reference_no}", s["reference"])
                self.assertEqual(event["text"], expected)
                self.assertEqual(event["text"].count(s["reference"]), 1)
                self.assertNotIn("{", event["text"])
                self.assertEqual(event["audio"], "none")
                self.assertRegex(s["reference"], r"^SAH-[0-9A-F]{6}$")
                self.assertEqual(case.reference, s["reference"])
                _case, again = self.call("end_session", s["session_id"])
                self.assertEqual(self.turn_events(again), [])
                self.assertEqual([r[0] for r in self.assistant_turns(s["session_id"])], ["S0", "S9"])

    def test_s9_is_suppressed_for_a_foreign_or_malformed_reference(self):
        # "SAH-000000" is well formed but is not derived from, so not owned by, the session.
        for bad in ("SAH-000000", "SAH-abc123", "SAH-1234567", "SAH-{reference_no}", ""):
            with self.subTest(reference=bad):
                s, _ = self.create()
                self.call("submit_turn", s["session_id"], NARRATIVE, "en")
                self.db_write("UPDATE cases SET reference=? WHERE id=?", bad, s["case_id"])
                _case, out = self.call("end_session", s["session_id"])
                self.assertEqual(self.turn_events(out), [])
                self.assertEqual([r[0] for r in self.assistant_turns(s["session_id"])], ["S0"])
                [detail] = self.audit_actions(s["case_id"], "fixed_script.provisional_suppressed")
                self.assertIn('"reference_invalid"', detail[0])

    def test_s9_is_suppressed_after_sx_sh_takeover_or_when_nothing_was_recorded(self):
        crisis, _ = self.create()
        self.call("submit_turn", crisis["session_id"], CRISIS, "en")
        handoff, _ = self.create()
        self.call("submit_turn", handoff["session_id"], NARRATIVE, "en")
        self.call("request_human", handoff["session_id"], "h:1")
        taken, _ = self.create()
        self.call("submit_turn", taken["session_id"], NARRATIVE, "en")
        h = self.login("exec1")
        self.client.post(f"/cases/{taken['case_id']}/claim", headers=h)
        self.assertEqual(self.client.post(f"/cases/{taken['case_id']}/takeover", headers=h).status_code, 200)
        empty, _ = self.create()
        for s in (crisis, handoff, taken, empty):
            _case, out = self.call("end_session", s["session_id"])
            self.assertEqual(self.turn_events(out), [], s)
            self.assertNotIn("S9", [r[0] for r in self.assistant_turns(s["session_id"])])
        [detail] = self.audit_actions(empty["case_id"], "fixed_script.provisional_suppressed")
        self.assertIn('"nothing_recorded"', detail[0])

    def test_a_changed_text_fails_its_hash_and_is_not_shown(self):
        from ml.dialogue.scripts import provisional

        original = provisional.PROVISIONAL_SCRIPTS["S0:en"]
        tampered = provisional.ProvisionalScript(original.state, "en", original.text + " ", original.sha256)
        with patch.dict(provisional.PROVISIONAL_SCRIPTS, {"S0:en": tampered}):
            s, out = self.create()
        self.assertEqual(self.turn_events(out), [])
        [detail] = self.audit_actions(s["case_id"], "fixed_script.provisional_suppressed")
        self.assertIn('"hash_mismatch"', detail[0])

    def test_fixed_scripts_ready_and_audio_readiness_stay_false(self):
        from ml.dialogue.scripts import provisional, unwritten

        body = self.client.get("/health").json()
        self.assertIs(body["fixed_scripts_ready"], False)
        self.assertEqual(len(body["detail"]["outstanding_fixed_scripts"]), 8)
        self.assertEqual(len(unwritten()), 8)
        self.assertIs(provisional.AUDIO_READY, False)

    def test_the_victim_socket_receives_text_only_turns_and_no_assessment_data(self):
        s = self.new_session(lang="hi")
        with self.socket(s) as ws:
            recv_until(ws, "session.status")
            frames = self.say(ws, CRISIS)
            frames += drain(ws)
        turns = [f for f in frames if f["type"] == "assistant.turn"]
        self.assertEqual([t["text"] for t in turns], [TEXTS["SX:hi"]])
        self.assertEqual({t["audio"] for t in turns}, {"none"})
        for frame in frames:
            for key in ASSESSMENT_KEYS:
                self.assertNotIn(key, frame)

    def test_the_audit_never_contains_victim_text(self):
        s, _ = self.create()
        self.call("submit_turn", s["session_id"], CRISIS, "en")
        for (detail,) in self.db("SELECT detail FROM audit_log WHERE case_id=?", s["case_id"]):
            self.assertNotIn(CRISIS, detail)

    def db_write(self, sql, *args):
        import sqlite3

        con = sqlite3.connect(os.path.join(self.tmp.name, "slice.db"))
        try:
            con.execute(sql, args)
            con.commit()
        finally:
            con.close()


class TestProvisionalScriptsDisabledByDefault(ProvisionalBase):
    enabled = False

    def test_the_default_setting_is_off(self):
        from backend.app.core.config import Settings

        settings = Settings(_env_file=None, APP_ENV="test", DATABASE_URL="sqlite+aiosqlite:///:memory:")
        self.assertIs(settings.PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO, False)

    def test_nothing_is_shown_on_any_path_when_disabled(self):
        from backend.app.services import fixed_scripts

        self.assertFalse(fixed_scripts.provisional_enabled())
        s, out = self.create()
        self.assertEqual(self.turn_events(out), [])
        out = self.call("submit_turn", s["session_id"], NARRATIVE, "en")
        self.assertEqual(self.turn_events(out), [])
        _case, out = self.call("end_session", s["session_id"])
        self.assertEqual(self.turn_events(out), [])
        crisis, _ = self.create()
        out = self.call("submit_turn", crisis["session_id"], CRISIS, "en")
        self.assertEqual(self.turn_events(out), [])
        self.assertIn("alert.safety", [kind for kind, _ in out.events])
        handoff, _ = self.create()
        self.assertEqual(self.turn_events(self.call("request_human", handoff["session_id"], "h:1")), [])
        for sid in (s["session_id"], crisis["session_id"], handoff["session_id"]):
            self.assertEqual(self.assistant_turns(sid), [])
        self.assertEqual(self.db("SELECT count(*) FROM audit_log WHERE action LIKE 'fixed_script.provisional%'"),
                         [(0,)])


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestProvisionalFlagRefusal(unittest.TestCase):
    def settings(self, **values):
        from backend.app.core.config import Settings

        return Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///:memory:", **values)

    def test_enabling_is_accepted_only_in_development_and_test(self):
        for env in ("development", "test"):
            self.assertIs(self.settings(APP_ENV=env, PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO=True)
                          .PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO, True)

    def test_enabling_in_production_demo_local_staging_or_unknown_fails(self):
        from pydantic import ValidationError

        from backend.app.core.config import Settings

        for env in ("production", "demo", "local", "staging", "unknown", ""):
            with self.subTest(env=env), self.assertRaises(ValidationError) as caught:
                Settings(_env_file=None, APP_ENV=env, PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO=True,
                         DATABASE_URL="postgresql+asyncpg://u:synthetic-secret-marker@db.invalid/app")
            self.assertNotIn("synthetic-secret-marker", str(caught.exception))

    def test_environment_variables_are_refused_the_same_way(self):
        from pydantic import ValidationError

        from backend.app.core.config import Settings

        env = {"APP_ENV": "production", "PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO": "true",
               "DATABASE_URL": "postgresql+asyncpg://u:synthetic-secret-marker@db.invalid/app"}
        with patch.dict(os.environ, env), self.assertRaises(ValidationError) as caught:
            Settings(_env_file=None)
        self.assertNotIn("synthetic-secret-marker", str(caught.exception))

    def test_the_service_refuses_even_if_validation_were_bypassed(self):
        from backend.app.services import fixed_scripts

        for env in ("production", "demo", "local", "staging", None):
            forged = SimpleNamespace(PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO=True, APP_ENV=env)
            with patch.object(fixed_scripts, "get_settings", return_value=forged):
                self.assertFalse(fixed_scripts.provisional_enabled(), env)
        truthy = SimpleNamespace(PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO="true", APP_ENV="test")
        with patch.object(fixed_scripts, "get_settings", return_value=truthy):
            self.assertFalse(fixed_scripts.provisional_enabled())

    def test_production_startup_refuses_without_echoing_secrets(self):
        env = dict(os.environ)
        env.update({"APP_ENV": "production", "PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO": "true",
                    "DATABASE_URL": "postgresql+asyncpg://u:synthetic-secret-marker@db.invalid/app",
                    "SECRET_KEY": "synthetic-signing-marker", "PYTHONDONTWRITEBYTECODE": "1"})
        result = subprocess.run([sys.executable, "-c", "import backend.app.main"], cwd=str(REPO), env=env,
                                capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PROVISIONAL_FIXED_SCRIPTS_LOCAL_DEMO", output)
        self.assertNotIn("synthetic-secret-marker", output)
        self.assertNotIn("synthetic-signing-marker", output)


if __name__ == "__main__":
    unittest.main()
