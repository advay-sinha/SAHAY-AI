"""GET /sessions/{id}/turns/{turn_id}/audio (contract change PC-12, M13).

No speech engine runs here: the synthesiser and the fixed-script registry are replaced by fakes.
All text is fictional.
"""

import itertools
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from backend.tests.test_vertical_slice import HAVE_DEPS, SliceBase

SEQ = itertools.count(1000)
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt fictional"


class FakeSynth:
    def __init__(self, audio=WAV):
        self.audio, self.calls = audio, 0

    def synthesize(self, text, lang):
        self.calls += 1
        return self.audio


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestTurnAudio(SliceBase):
    def add_turn(self, session_id, speaker="assistant", state="S2", text="Can you tell me when this happened?"):
        from backend.app.models import Turn
        from backend.app.services import audit

        turn_id = str(uuid.uuid4())

        async def insert():
            from backend.app.core import db as dbmod
            async with dbmod.session_factory()() as s:
                s.add(Turn(id=turn_id, session_id=session_id, seq=next(SEQ),
                           speaker=speaker, text=text, lang="en", state=state, created_at=audit.now()))
                await s.commit()
        self.client.portal.call(insert)
        return turn_id

    def get(self, session, turn_id, token=None):
        headers = {"Authorization": f"Bearer {token or session['session_token']}"}
        return self.client.get(f"/sessions/{session['session_id']}/turns/{turn_id}/audio", headers=headers)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from backend.app.core.config import get_settings
        self.settings = get_settings()
        self.patches = [mock.patch.object(self.settings, "AUDIO_STORAGE_PATH", self.tmp.name),
                        mock.patch.object(self.settings, "FIXED_AUDIO_ROOT", str(Path(self.tmp.name) / "fixed"))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_generated_turn_is_synthesised_once_then_cached(self):
        s = self.new_session(lang="en")
        turn_id = self.add_turn(s["session_id"])
        fake = FakeSynth()
        with mock.patch("backend.app.api.sessions.get_tts", return_value=fake):
            first, second = self.get(s, turn_id), self.get(s, turn_id)
        for r in (first, second):
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.headers["content-type"], "audio/wav")
            self.assertEqual(r.headers["cache-control"], "no-store")
            self.assertEqual(r.content, WAV)
        self.assertEqual(fake.calls, 1)

    def test_no_voice_means_404_and_the_client_keeps_the_text(self):
        s = self.new_session(lang="en")
        turn_id = self.add_turn(s["session_id"])
        with mock.patch("backend.app.api.sessions.get_tts", return_value=FakeSynth(b"")):
            r = self.get(s, turn_id)
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("text", r.json())

    def test_fixed_scripts_play_only_approved_recordings_and_are_never_synthesised(self):
        s = self.new_session(lang="en")
        turn_id = self.add_turn(s["session_id"], state="SX", text="fictional fixed script")
        fake = FakeSynth()
        with mock.patch("backend.app.api.sessions.get_tts", return_value=fake):
            self.assertEqual(self.get(s, turn_id).status_code, 404)  # nothing approved in the registry
            rec = Path(self.tmp.name) / "rec.wav"
            rec.write_bytes(WAV)
            with mock.patch("ml.tts.presynth.servable", return_value=rec):
                r = self.get(s, turn_id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, WAV)
        self.assertEqual(fake.calls, 0)

    def test_only_the_sessions_own_victim_gets_assistant_audio(self):
        s, other = self.new_session(lang="en"), self.new_session(lang="en")
        turn_id = self.add_turn(s["session_id"])
        victim_turn = self.add_turn(s["session_id"], speaker="victim")
        with mock.patch("backend.app.api.sessions.get_tts", return_value=FakeSynth()):
            self.assertIn(self.get(s, turn_id, token=other["session_token"]).status_code, (403, 404))
            self.assertEqual(self.get(s, victim_turn).status_code, 404)
            self.assertEqual(self.get(s, "no-such-turn").status_code, 404)
            console = self.login("exec1")["Authorization"].split(" ", 1)[1]
            self.assertEqual(self.get(s, turn_id, token=console).status_code, 403)

    def test_synthesis_latency_is_recorded(self):
        from sqlalchemy import select
        from backend.app.models import LatencyMetric
        s = self.new_session(lang="en")
        turn_id = self.add_turn(s["session_id"])
        with mock.patch("backend.app.api.sessions.get_tts", return_value=FakeSynth()):
            self.get(s, turn_id)

        async def load():
            from backend.app.core import db as dbmod
            async with dbmod.session_factory()() as db:
                return [m.stage for m in (await db.execute(select(LatencyMetric)
                                                           .where(LatencyMetric.turn_id == turn_id))).scalars()]
        self.assertEqual(self.client.portal.call(load), ["tts_synthesis"])


class TestAdapter(unittest.TestCase):
    def test_default_provider_produces_no_audio(self):
        from backend.app.adapters.tts import get_provider

        class S:
            TTS_PROVIDER = "none"
        self.assertEqual(get_provider(S()).synthesize("hello", "en"), b"")


if __name__ == "__main__":
    unittest.main()
