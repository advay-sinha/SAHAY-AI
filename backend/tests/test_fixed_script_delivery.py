"""Approved fixed scripts are spoken once, at the right moment, and only then.

The real records are IN_REVIEW, so these tests simulate approval by patching
the two lookups (the policy's and intake's) to return the drafted text. With
the patch removed, every script stays silent; test_vertical_slice covers that.
"""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from backend.tests.test_vertical_slice import HAVE_DEPS, TURNS, SliceBase, drain, recv_until

if HAVE_DEPS:
    from ml.dialogue.scripts import fixed_scripts

CRISIS_TURN = "Ab aur nahi jee sakti, main jaan de dungi."


def approved_text(state, lang):
    return fixed_scripts.DRAFT_TEXT.get(f"{state.value}:{lang}")


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestApprovedFixedScripts(SliceBase):
    def setUp(self):
        stack = ExitStack()
        stack.enter_context(patch.object(fixed_scripts, "text_for", approved_text))
        stack.enter_context(patch("backend.app.services.intake.fixed_script_text", approved_text))
        self.addCleanup(stack.close)

    def assistant_texts(self, frames):
        return [f["text"] for f in frames if f["type"] == "assistant.turn"]

    def test_opening_is_spoken_once_on_first_connect(self):
        s = self.new_session(lang="hi")
        with self.client.websocket_connect(s["connect"]) as ws:
            frames = recv_until(ws, "session.status") + drain(ws)
            self.assertEqual(self.assistant_texts(frames), [fixed_scripts.DRAFT_TEXT["S0:hi"]])
        with self.client.websocket_connect(s["connect"]) as ws:
            frames = recv_until(ws, "session.status") + drain(ws)
            self.assertEqual(self.assistant_texts(frames), [], "the opening is never repeated")
        transcript = self.packet(s["case_id"])["transcript"]
        self.assertEqual([t["speaker"] for t in transcript], ["assistant"])

    def test_declined_session_hears_the_handoff_not_the_opening(self):
        s = self.new_session(consent="declined", lang="en")
        with self.client.websocket_connect(s["connect"]) as ws:
            frames = recv_until(ws, "session.status") + drain(ws)
        self.assertEqual(self.assistant_texts(frames), [fixed_scripts.DRAFT_TEXT["SH:en"]])

    def test_crisis_speaks_sx_once_then_holds(self):
        s = self.new_session(lang="hi")
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            drain(ws)
            self.say(ws, TURNS[0])
            frames = self.say(ws, CRISIS_TURN) + drain(ws)
            states = [f["state"] for f in frames if f["type"] == "session.status"]
            self.assertEqual(states[-1], "SX")
            self.assertEqual(self.assistant_texts(frames), [fixed_scripts.DRAFT_TEXT["SX:hi"]])
            for frame in frames:
                for key in ("svi", "band", "alert", "severity"):
                    self.assertNotIn(key, frame)
        self.assertEqual(self.packet(s["case_id"])["header"]["band"], "Critical")

    def test_human_request_speaks_handoff_once(self):
        s = self.new_session(lang="en")
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            drain(ws)
            ws.send_json({"type": "request_human"})
            first = recv_until(ws, "session.status") + drain(ws)
            ws.send_json({"type": "request_human"})
            second = recv_until(ws, "session.status") + drain(ws)
        self.assertEqual(self.assistant_texts(first), [fixed_scripts.DRAFT_TEXT["SH:en"]])
        self.assertEqual(self.assistant_texts(second), [])

    def test_human_request_after_crisis_does_not_speak_over_sx(self):
        s = self.new_session(lang="hi")
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            drain(ws)
            self.say(ws, CRISIS_TURN)
            drain(ws)
            ws.send_json({"type": "request_human"})
            frames = recv_until(ws, "session.status") + drain(ws)
        self.assertEqual(self.assistant_texts(frames), [])

    def test_ending_an_ordinary_intake_speaks_the_closing(self):
        s = self.new_session(lang="en")
        vh = {"Authorization": f"Bearer {s['session_token']}"}
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            drain(ws)
            self.say(ws, TURNS[0])
            drain(ws)
            self.assertEqual(self.client.post(f"/sessions/{s['session_id']}/end", headers=vh).status_code, 200)
            frames = drain(ws, timeout=1.0)
        self.assertEqual(self.assistant_texts(frames), [fixed_scripts.DRAFT_TEXT["S9:en"]])


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestUnapprovedScriptsStaySilent(SliceBase):
    def test_no_fixed_script_is_spoken_while_records_are_in_review(self):
        s = self.new_session(lang="en")
        with self.client.websocket_connect(s["connect"]) as ws:
            frames = recv_until(ws, "session.status") + drain(ws)
            ws.send_json({"type": "request_human"})
            frames += recv_until(ws, "session.status") + drain(ws)
        self.assertNotIn("assistant.turn", [f["type"] for f in frames])


if __name__ == "__main__":
    unittest.main()
