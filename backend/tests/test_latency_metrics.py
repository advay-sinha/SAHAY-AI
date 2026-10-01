"""Per-turn latency measurements (HANDOVER M2): recorded server-side, never sent to a client.

The ASR adapter is a queued mock; all text is fictional.
"""

import unittest
from unittest import mock

from backend.tests.test_vertical_slice import HAVE_DEPS, SliceBase, drain, recv_until

TRANSCRIBED = {"status": "transcribed", "text": "Woh log phir aaye the, bahut darr lag raha hai.",
               "asr_confidence": 0.82, "low_asr_confidence": False, "poor_audio": False,
               "quality": {"snr_db": 28.0}, "speech_s": 2.4, "duration_s": 3.0,
               "timings_ms": {"decode": 12, "asr": 340, "total": 360}}
TIMING_KEYS = ("timings_ms", "duration_ms", "latency", "reply_path", "asr_request", "request_total")


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestLatencyMetrics(SliceBase):
    def metrics(self, session_id):
        from sqlalchemy import select
        from backend.app.models import LatencyMetric

        async def load():
            from backend.app.core import db as dbmod
            async with dbmod.session_factory()() as s:
                rows = (await s.execute(select(LatencyMetric).where(LatencyMetric.session_id == session_id)))
                return [(m.stage, m.duration_ms, m.turn_id) for m in rows.scalars()]
        return self.client.portal.call(load)

    def test_voice_turn_records_every_server_stage_and_leaks_nothing(self):
        from backend.app.adapters.asr import MockASR
        s = self.new_session(channel="mobile_voice")
        with self.client.websocket_connect(s["connect"]) as victim:
            recv_until(victim, "session.status")
            with mock.patch("backend.app.api.sessions.get_asr", return_value=MockASR([TRANSCRIBED])):
                r = self.client.post(f"/sessions/{s['session_id']}/audio", content=b"RIFF-fictional",
                                     headers={"Authorization": f"Bearer {s['session_token']}",
                                              "Content-Type": "audio/wav"})
            self.settle()
            frames = drain(victim)
        self.assertEqual(r.status_code, 200, r.text)
        rows = self.metrics(s["session_id"])
        stages = {stage for stage, _, _ in rows}
        for stage in ("asr_request", "request_total", "safety_precheck", "dialogue_policy", "reply_path",
                      "asr_service_decode", "asr_service_asr", "asr_service_total"):
            self.assertIn(stage, stages)
        self.assertTrue(all(ms >= 0 for _, ms, _ in rows))
        self.assertEqual({t for _, _, t in rows}, {r.json()["turn_id"]})
        self.assertEqual(dict((st, ms) for st, ms, _ in rows)["asr_service_asr"], 340.0)
        for text in [r.text] + [str(f) for f in frames]:
            for key in TIMING_KEYS:
                self.assertNotIn(key, text)

    def test_typed_turn_records_the_reply_path_but_no_asr_stage(self):
        s = self.new_session(channel="mobile_chat")
        with self.client.websocket_connect(s["connect"]) as victim:
            recv_until(victim, "session.status")
            frames = self.say(victim, "Woh log phir aaye the.") + drain(victim)
        stages = {st for st, _, _ in self.metrics(s["session_id"])}
        self.assertTrue({"safety_precheck", "dialogue_policy", "reply_path"} <= stages, stages)
        self.assertFalse(any(st.startswith("asr") for st in stages), stages)
        for f in frames:
            for key in TIMING_KEYS:
                self.assertNotIn(key, str(f))


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestRecorder(unittest.TestCase):
    def test_only_known_numeric_stages_are_written(self):
        from backend.app.services import latency

        class DB:
            def __init__(self):
                self.rows = []

            def add(self, row):
                self.rows.append(row)

        db = DB()
        n = latency.record(db, "s1", "t1", {"safety_precheck": 0.4, "made_up": 5, "reply_path": "fast",
                                            "dialogue_policy": True, "output_validator": 2})
        self.assertEqual(n, 2)
        self.assertEqual(sorted(r.stage for r in db.rows), ["output_validator", "safety_precheck"])
        self.assertEqual(latency.asr_service_timings({"timings_ms": {"decode": 1, "asr": 2, "x": 3}}),
                         {"asr_service_decode": 1, "asr_service_asr": 2})
        self.assertEqual(latency.asr_service_timings(None), {})


if __name__ == "__main__":
    unittest.main()
