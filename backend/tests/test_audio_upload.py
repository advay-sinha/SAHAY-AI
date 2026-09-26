"""POST /sessions/{id}/audio — whole-utterance voice turn (contract change PC-11).

The ASR adapter is replaced by a queued mock, so no speech model or process is needed. All
text is fictional. Covers: the victim-safe response shape, the same path as a typed turn
(crisis pre-check first), console-only ASR measurements, abstention on poor audio, and every
refusal the contract lists.
"""

import unittest
from unittest import mock

from backend.tests.test_vertical_slice import ASSESSMENT_KEYS, HAVE_DEPS, SliceBase, drain, recv_until

TRANSCRIBED = {"status": "transcribed", "text": "Woh log phir aaye the, bahut darr lag raha hai.",
               "asr_confidence": 0.82, "low_asr_confidence": False, "poor_audio": False,
               "quality": {"snr_db": 28.0, "clipping_ratio": 0.0}, "speech_s": 2.4, "duration_s": 3.0}
WAV = {"Content-Type": "audio/wav"}


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestAudioUpload(SliceBase):
    def upload(self, session, responses, body=b"RIFF-fictional-audio", headers=None, lang=None):
        from backend.app.adapters.asr import MockASR
        provider = MockASR(list(responses))
        hdrs = {"Authorization": f"Bearer {session['session_token']}", **(headers or WAV)}
        url = f"/sessions/{session['session_id']}/audio" + (f"?lang={lang}" if lang else "")
        with mock.patch("backend.app.api.sessions.get_asr", return_value=provider):
            r = self.client.post(url, content=body, headers=hdrs)
        self.settle()
        return r, provider

    def turns(self, session_id):
        from sqlalchemy import select
        from backend.app.models import Turn

        async def load():
            from backend.app.core import db as dbmod
            async with dbmod.session_factory()() as s:
                return list((await s.execute(select(Turn).where(Turn.session_id == session_id)
                                             .order_by(Turn.seq))).scalars())
        return self.client.portal.call(load)

    def test_accepted_turn_is_victim_safe_and_measured_for_the_console(self):
        s = self.new_session(channel="mobile_voice")
        with self.client.websocket_connect(s["connect"]) as victim:
            recv_until(victim, "session.status")
            r, _ = self.upload(s, [TRANSCRIBED])
            frames = drain(victim)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(set(body), {"turn_id", "status"})
        self.assertEqual(body["status"], "accepted")
        victim_turn = next(t for t in self.turns(s["session_id"]) if t.speaker == "victim")
        self.assertEqual(body["turn_id"], victim_turn.id)
        self.assertEqual(victim_turn.text, TRANSCRIBED["text"])
        self.assertEqual(victim_turn.asr_confidence, 0.82)
        self.assertEqual(victim_turn.asr_quality["snr_db"], 28.0)
        # The victim socket shows the transcript but never a measurement or assessment field.
        for frame in frames:
            for key in ASSESSMENT_KEYS + ("asr_confidence", "asr_quality", "poor_audio", "snr_db", "quality"):
                self.assertNotIn(key, frame, frame["type"])
        self.assertIn("transcript.line", {f["type"] for f in frames})

    def test_spoken_crisis_takes_the_same_path_as_typed_crisis(self):
        s = self.new_session(channel="mobile_voice", lang="en")
        r, _ = self.upload(s, [{**TRANSCRIBED, "text": "I want to kill myself tonight."}])
        self.assertEqual(r.json()["status"], "accepted")
        packet = self.packet(s["case_id"])
        self.assertEqual(packet["header"]["band"], "Critical")
        self.assertTrue(any(a["alert_type"] == "crisis" for a in packet["alerts"]), packet["alerts"])

    def test_poor_audio_makes_the_assessment_abstain(self):
        s = self.new_session(channel="mobile_voice")
        r, _ = self.upload(s, [{**TRANSCRIBED, "poor_audio": True}])
        self.assertEqual(r.json()["status"], "accepted")
        packet = self.packet(s["case_id"])
        self.assertTrue(packet["uncertainty"]["quality_flags"].get("poor_audio"), packet["uncertainty"])
        self.assertTrue(packet["assessment"]["needs_human"])
        self.assertIsNone(packet["assessment"]["svi"])
        self.assertEqual(packet["uncertainty"]["asr_confidence"], 0.82)

    def test_no_speech_and_unreadable_create_no_turn(self):
        s = self.new_session(channel="mobile_voice")
        r, _ = self.upload(s, [{"status": "no_speech", "text": ""}])
        self.assertEqual(r.json(), {"turn_id": None, "status": "no_speech"})
        r, _ = self.upload(s, [{"status": "audio_unreadable"}])
        self.assertEqual(r.json(), {"turn_id": None, "status": "audio_unreadable"})
        r, _ = self.upload(s, [{"status": "transcribed", "text": "   "}])
        self.assertEqual(r.json(), {"turn_id": None, "status": "no_speech"})
        self.assertEqual([t for t in self.turns(s["session_id"]) if t.speaker == "victim"], [])

    def test_refusals(self):
        from backend.app.adapters.asr import ASRRejected, ASRUnavailable
        voice = self.new_session(channel="mobile_voice")
        chat = self.new_session(channel="mobile_chat")
        declined = self.new_session(channel="mobile_voice", consent="declined")
        self.assertEqual(self.upload(chat, [TRANSCRIBED])[0].status_code, 409)
        self.assertEqual(self.upload(declined, [TRANSCRIBED])[0].status_code, 409)
        r, provider = self.upload(voice, [TRANSCRIBED], headers={"Content-Type": "text/plain"})
        self.assertEqual((r.status_code, provider.calls), (415, 0))
        r, provider = self.upload(voice, [TRANSCRIBED], lang="fr")
        self.assertEqual((r.status_code, provider.calls), (400, 0))
        r, provider = self.upload(voice, [TRANSCRIBED], body=b"x" * (5 * 1024 * 1024 + 1))
        self.assertEqual((r.status_code, provider.calls), (413, 0))
        self.assertEqual(self.upload(voice, [ASRUnavailable("down")])[0].status_code, 503)
        self.assertEqual(self.upload(voice, [ASRRejected(413, "too_long")])[0].status_code, 413)
        self.assertEqual(self.upload(voice, [])[0].json(), {"turn_id": None, "status": "no_speech"})

    def test_only_the_sessions_own_victim_token(self):
        a = self.new_session(channel="mobile_voice")
        b = self.new_session(channel="mobile_voice")
        from backend.app.adapters.asr import MockASR
        with mock.patch("backend.app.api.sessions.get_asr", return_value=MockASR([TRANSCRIBED])):
            other = self.client.post(f"/sessions/{a['session_id']}/audio", content=b"x",
                                     headers={"Authorization": f"Bearer {b['session_token']}", **WAV})
            officer = self.client.post(f"/sessions/{a['session_id']}/audio", content=b"x",
                                       headers={**self.login("exec1"), **WAV})
        self.assertEqual(other.status_code, 403)
        self.assertEqual(officer.status_code, 403)


if __name__ == "__main__":
    unittest.main()
