"""Lead decisions of 2026-09-11 (PC-01, PC-02, PC-03, PC-06, PC-07, PC-08,
PC-09), tested over the real REST API and WebSocket.

Reuses the disposable-database harness from test_vertical_slice. All text is
fictional.
"""

import os
import sqlite3
import unittest

from backend.tests.test_vertical_slice import (
    ASSESSMENT_KEYS,
    HAVE_DEPS,
    TURNS,
    SliceBase,
    drain,
    recv_until,
)


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class DecisionBase(SliceBase):
    def db(self, sql, *args):
        con = sqlite3.connect(os.path.join(self.tmp.name, "slice.db"))
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def ready_case(self, turns=TURNS):
        s = self.new_session()
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            for t in turns:
                self.say(ws, t)
        return s

    def victim_headers(self, s):
        return {"Authorization": f"Bearer {s['session_token']}"}


class TestSessionResponse(DecisionBase):
    """PC-09: the POST /sessions response is frozen."""

    FROZEN = {"session_id", "case_id", "reference_no", "session_token", "ws_url", "lang", "consent",
              "ai_disclosure", "human_request_available"}

    def test_exact_fields_and_no_token_in_ws_url(self):
        r = self.client.post("/sessions", json={"channel": "mobile_chat", "consent": "granted", "lang": "hi"})
        body = r.json()
        self.assertEqual(set(body), self.FROZEN)
        self.assertEqual(body["ws_url"], f"/ws/session/{body['session_id']}")
        self.assertNotIn("token", body["ws_url"])
        self.assertTrue(body["human_request_available"])
        for key in ASSESSMENT_KEYS + ("state",):
            self.assertNotIn(key, body)

    def test_the_session_token_is_a_victim_credential_for_one_session_only(self):
        from backend.app.core.security import decode_token

        a, b = self.new_session(), self.new_session()
        claims = decode_token(a["session_token"])
        self.assertEqual(claims["role"], "victim")
        self.assertEqual(claims["sid"], a["session_id"])
        h = self.victim_headers(a)
        cid = a["case_id"]
        for path in ("/queue", f"/cases/{cid}", f"/cases/{cid}/audit"):
            self.assertEqual(self.client.get(path, headers=h).status_code, 403, path)
        for path, body in ((f"/cases/{cid}/claim", None), (f"/cases/{cid}/takeover", None),
                           (f"/cases/{cid}/messages", {"text": "x"}),
                           (f"/cases/{cid}/override", {"band": "Low", "reason": "x"})):
            self.assertEqual(self.client.post(path, headers=h, json=body).status_code, 403, path)
        self.assertEqual(self.client.post(f"/sessions/{b['session_id']}/end", headers=h).status_code, 403)

    def test_unknown_channel_is_rejected_and_old_values_are_gone(self):
        for channel in ("chat", "voice", "sms"):
            r = self.client.post("/sessions", json={"channel": channel, "consent": "granted"})
            self.assertEqual(r.status_code, 422, channel)


class TestAlertAcknowledgement(DecisionBase):
    """PC-01: executive only, case access, officer and time, idempotent, and
    no effect on the assessment or the victim timeline."""

    def test_frozen_shape_and_idempotency(self):
        s = self.ready_case()
        h = self.login("exec1")
        alert = self.packet(s["case_id"])["alerts"][0]
        url = f"/cases/{s['case_id']}/alerts/{alert['id']}/ack"
        first = self.client.post(url, headers=h)
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual(set(body), {"alert_id", "case_id", "acknowledged_by", "acknowledged_at"})
        self.assertEqual(body["acknowledged_by"], "u-exec1")
        self.assertEqual(body["case_id"], s["case_id"])
        self.assertEqual(self.client.post(url, headers=h).json(), body)

    def test_ack_changes_neither_assessment_nor_timeline_and_tells_the_victim_nothing(self):
        s = self.ready_case()
        h = self.login("exec1")
        cid = s["case_id"]
        before = self.packet(cid)
        timeline_before = self.client.get(f"/cases/{cid}/timeline", headers=self.victim_headers(s)).json()
        assessments_before = self.db("SELECT count(*) FROM assessments WHERE case_id=?", cid)
        with self.client.websocket_connect(s["connect"]) as victim:
            recv_until(victim, "session.status")
            for alert in before["alerts"]:
                self.client.post(f"/cases/{cid}/alerts/{alert['id']}/ack", headers=h)
            self.settle()
            self.assertEqual(drain(victim), [])
        after = self.packet(cid)
        self.assertEqual(after["assessment"], before["assessment"])
        self.assertEqual(after["header"]["band"], before["header"]["band"])
        self.assertEqual(after["trajectory"], before["trajectory"])
        self.assertEqual(self.client.get(f"/cases/{cid}/timeline", headers=self.victim_headers(s)).json(),
                         timeline_before)
        self.assertEqual(self.db("SELECT count(*) FROM assessments WHERE case_id=?", cid), assessments_before)
        self.assertTrue(all(a["acknowledged_at"] for a in after["alerts"]))

    def test_an_officer_cannot_ack_on_a_case_another_officer_claimed(self):
        s = self.ready_case()
        cid = s["case_id"]
        self.client.post(f"/cases/{cid}/claim", headers=self.login("exec1"))
        alert = self.packet(cid)["alerts"][0]
        r = self.client.post(f"/cases/{cid}/alerts/{alert['id']}/ack", headers=self.login("exec2"))
        self.assertEqual(r.status_code, 403)
        ok = self.client.post(f"/cases/{cid}/alerts/{alert['id']}/ack", headers=self.login("exec1"))
        self.assertEqual(ok.status_code, 200)

    def test_alert_frames_keep_the_event_name_in_type(self):
        """PC-02: the envelope's type is the event name; the kind is alert_type."""
        s = self.new_session()
        exec_token = self.client.post("/auth/login", json={"username": "exec1", "password": "test-only-not-a-real-password"}).json()["token"]
        with self.client.websocket_connect(f"/ws/session/{s['session_id']}?token={exec_token}") as officer, \
                self.client.websocket_connect(s["connect"]) as victim:
            recv_until(officer, "session.status")
            recv_until(victim, "session.status")
            frames = []
            for t in TURNS:
                self.say(victim, t)
                frames += drain(officer)
        alerts = [f for f in frames if f.get("alert_type")]
        self.assertTrue(alerts)
        for f in alerts:
            self.assertEqual(f["type"], "alert.safety")
        for f in (f for f in frames if f["type"] == "escalation.packet"):
            for a in f["alerts"]:
                self.assertIn("alert_type", a)
                self.assertNotIn("type", a)


class TestDedicatedTables(DecisionBase):
    """PC-03: overrides and timeline_events are authoritative; audit is accountability."""

    def test_override_is_stored_in_the_overrides_table(self):
        s = self.ready_case()
        h = self.login("exec1")
        cid = s["case_id"]
        self.client.post(f"/cases/{cid}/claim", headers=h)
        r = self.client.post(f"/cases/{cid}/override", headers=h, json={"band": "Critical", "reason": "officer judgement"})
        self.assertEqual(r.status_code, 200)
        again = self.client.post(f"/cases/{cid}/override", headers=h, json={"band": "Critical", "reason": "officer judgement"})
        self.assertEqual(again.json()["override_id"], r.json()["override_id"])  # identical repeat: no new row
        rows = self.db("SELECT id, officer_id, to_band, reason FROM overrides WHERE case_id=?", cid)
        self.assertEqual(rows, [(r.json()["override_id"], "u-exec1", "Critical", "officer judgement")])
        packet = self.packet(cid)
        self.assertEqual([(o["id"], o["to_band"], o["reason"]) for o in packet["overrides"]],
                         [(rows[0][0], "Critical", "officer judgement")])
        audit = self.client.get(f"/cases/{cid}/audit", headers=h).json()
        entries = [e for e in audit if e["action"] == "band.override"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["detail"]["override_id"], rows[0][0])

    def test_timeline_is_read_from_timeline_events(self):
        s = self.ready_case()
        h = self.login("exec1")
        cid = s["case_id"]
        self.client.post(f"/cases/{cid}/claim", headers=h)
        rec = self.packet(cid)["recommendations"][0]
        self.client.post(f"/cases/{cid}/decisions", headers=h, json={"action_id": rec["action_id"], "decision": "confirm"})
        stored = [r[0] for r in self.db(
            "SELECT stage FROM timeline_events WHERE case_id=? ORDER BY created_at, id", cid)]
        self.assertEqual(stored, ["request_received", "under_review", "officer_assigned", "action_taken"])
        served = self.client.get(f"/cases/{cid}/timeline", headers=self.victim_headers(s)).json()["timeline"]
        self.assertEqual([e["stage"] for e in served], stored)
        for e in served:
            self.assertEqual(set(e), {"stage", "label", "ts"})
            self.assertNotIn(rec["action_type"], e["label"])  # labels never name the pathway
        audit_stages = [e["detail"]["stage"] for e in self.client.get(f"/cases/{cid}/audit", headers=h).json()
                        if e["action"] == "timeline.stage_added"]
        self.assertEqual(audit_stages, stored)

    def test_the_schema_has_the_fifteen_contract_tables(self):
        names = {r[0] for r in self.db("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertLessEqual({"overrides", "timeline_events"}, names)
        from backend.app.core.db import Base

        self.assertEqual(len(Base.metadata.tables), 15)


class TestOfficerMessage(DecisionBase):
    """PC-07: only the claiming officer, only after verified takeover."""

    def test_refused_before_takeover_and_for_everyone_else(self):
        s = self.ready_case()
        cid = s["case_id"]
        h1, h2 = self.login("exec1"), self.login("exec2")
        url = f"/cases/{cid}/messages"
        self.assertEqual(self.client.post(url, headers=h1, json={"text": "hello"}).status_code, 409)  # unclaimed
        self.client.post(f"/cases/{cid}/claim", headers=h1)
        self.assertEqual(self.client.post(url, headers=h1, json={"text": "hello"}).status_code, 409)  # not taken over
        self.client.post(f"/cases/{cid}/takeover", headers=h1)
        self.assertEqual(self.client.post(url, headers=h2, json={"text": "hello"}).status_code, 409)  # not the owner
        self.assertEqual(self.client.post(url, headers=self.login("sup1"), json={"text": "hello"}).status_code, 403)
        self.assertEqual(self.client.post(url, headers=self.victim_headers(s), json={"text": "hello"}).status_code, 403)
        self.assertEqual(self.client.post(url, headers=h1, json={"text": "   "}).status_code, 400)
        self.assertEqual(self.client.post(url, headers=h1, json={"text": "x" * 2001}).status_code, 400)
        self.assertEqual(self.db("SELECT count(*) FROM turns WHERE speaker='officer' AND session_id=?", s["session_id"]), [(0,)])

    def test_delivered_as_a_human_officer_message_with_no_assessment_field(self):
        s = self.ready_case()
        cid = s["case_id"]
        h = self.login("exec1")
        self.client.post(f"/cases/{cid}/claim", headers=h)
        self.client.post(f"/cases/{cid}/takeover", headers=h)
        text = "I am an officer. I have read your messages and I am here."
        with self.client.websocket_connect(s["connect"]) as victim:
            recv_until(victim, "session.status")
            r = self.client.post(f"/cases/{cid}/messages", headers=h, json={"text": text, "lang": "en"})
            self.assertEqual(r.status_code, 201, r.text)
            self.assertEqual(set(r.json()), {"turn_id", "case_id", "origin", "ts"})
            frames = recv_until(victim, "officer.message")
        msg = frames[-1]
        self.assertEqual(set(msg), {"type", "turn_id", "text", "lang", "ts", "origin"})
        self.assertEqual(msg["origin"], "human_officer")
        self.assertEqual(msg["text"], text)
        for key in ASSESSMENT_KEYS:
            self.assertNotIn(key, msg)
        # Stored as an officer turn; audited without the text.
        self.assertEqual(self.db("SELECT speaker, text FROM turns WHERE id=?", msg["turn_id"]), [("officer", text)])
        audit = self.client.get(f"/cases/{cid}/audit", headers=h).json()
        entry = next(e for e in audit if e["action"] == "officer.message")
        self.assertEqual(entry["actor_kind"], "human")
        self.assertNotIn(text, str(entry))
        packet = self.packet(cid)
        self.assertIsNotNone(packet["header"]["human_joined_at"])
        self.assertIn(("officer", text), [(t["speaker"], t["text"]) for t in packet["transcript"]])

    def test_refused_after_the_session_ends(self):
        s = self.ready_case()
        cid = s["case_id"]
        h = self.login("exec1")
        self.client.post(f"/cases/{cid}/claim", headers=h)
        self.client.post(f"/cases/{cid}/takeover", headers=h)
        self.client.post(f"/sessions/{s['session_id']}/end", headers=self.victim_headers(s))
        self.assertEqual(self.client.post(f"/cases/{cid}/messages", headers=h, json={"text": "hi"}).status_code, 409)

    def test_only_the_officer_message_service_publishes_the_event(self):
        """No AI path can emit officer.message: one publisher, in casework."""
        import pathlib

        app = pathlib.Path(__file__).resolve().parents[1] / "app"
        users = sorted(str(p.relative_to(app)).replace("\\", "/") for p in app.rglob("*.py")
                       if '"officer.message"' in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["services/casework.py", "ws/events.py"])


class TestNormalisationInThePacket(DecisionBase):
    """PC-08: the packet records the normalisation and shows D4 as unavailable."""

    def test_text_channel_assessment_is_renormalised_and_says_so(self):
        s = self.ready_case()
        a = self.packet(s["case_id"])["assessment"]
        self.assertTrue(a["scoring_version"])
        n = a["normalization"]
        self.assertEqual(n["structurally_unavailable"], ["D4"])
        self.assertAlmostEqual(n["weight_denominator"], 0.88, places=6)
        self.assertEqual(n["channel"], "mobile_chat")
        d4 = next(d for d in a["dimensions"] if d["dimension"] == "D4")
        self.assertFalse(d4["available"])
        self.assertIsNone(d4["score"])
        self.assertEqual(d4["effective_weight"], 0.0)
        stored = self.db("SELECT scoring_version FROM assessments WHERE case_id=?", s["case_id"])
        self.assertTrue(all(v for (v,) in stored))

    def test_audio_channel_without_acoustics_abstains(self):
        s = self.new_session(channel="mobile_voice")
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            for t in TURNS:
                self.say(ws, t)
        a = self.packet(s["case_id"])["assessment"]
        self.assertIn("acoustic_not_measured", a["abstention_reasons"])
        self.assertEqual(a["normalization"]["structurally_unavailable"], [])


if __name__ == "__main__":
    unittest.main()
