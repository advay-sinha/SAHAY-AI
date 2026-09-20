"""End-to-end safety and flow tests over the real REST API and WebSocket.

A disposable SQLite database per test class; the app's session factory is
pointed at it, so API calls and the background assessment runner share it.
Every WebSocket read has a timeout, so a missing event fails the test instead
of hanging it. All text is fictional.

Covers (PHASE I): victim isolation from assessment data, victim-safe
timeline, consent-declined suppression, crisis interrupt and non-resumption,
AI/human decision separation, 400 on a blank override reason, safe duplicate
acknowledgement, RBAC, no tokens or narratives in logs, evidence ids resolve,
Needs Human Assessment hides every score, confirmation alone creates the
victim-safe action, duplicate-claim safety, invalid transitions, reconnect,
slow-client isolation, and the storage path guard.
"""

import importlib.util
import io
import json
import logging
import os
import queue
import tempfile
import unittest

_DEPS = ("fastapi", "pydantic_settings", "sqlalchemy", "aiosqlite", "jwt", "pwdlib", "httpx")
HAVE_DEPS = all(importlib.util.find_spec(m) is not None for m in _DEPS)

PASSWORD = "test-only-not-a-real-password"
ASSESSMENT_KEYS = ("svi", "band", "dims", "needs_human", "confidence", "alerts", "recommendation",
                   "evidence_turn_ids", "overrides_applied", "severity")

TURNS = [
    "Complaint ke baad se gaon mein humara hukka paani band kar diya hai. Hand pump se paani nahi lene dete.",
    "Pichle hafte thane gaye to police ne report nahi likhi. Pradhan ke logon ne dhamki di ki complaint wapas lo.",
    "Abhi ghar pe hain, par woh bol kar gaye ki wapas aayenge aur maar denge. Bahut darr lag raha hai.",
    "Mere pita ko chot lagi thi, haath toot gaya. Ilaaj nahi ho pa raha.",
]


class Closed(Exception):
    pass


def recv(ws, timeout=5.0):
    try:
        msg = ws._send_queue.get(timeout=timeout)
    except queue.Empty:
        raise AssertionError("timed out waiting for a WebSocket frame") from None
    if isinstance(msg, BaseException):
        raise msg
    if msg.get("type") == "websocket.close":
        raise Closed(msg.get("code"))
    return json.loads(msg["text"])


def recv_until(ws, event_type, limit=40, timeout=5.0):
    """Read frames until one of `event_type` arrives; return all frames read."""
    frames = []
    for _ in range(limit):
        frame = recv(ws, timeout)
        frames.append(frame)
        if frame.get("type") == event_type:
            return frames
    raise AssertionError(f"{event_type} not received in {limit} frames")


def drain(ws, timeout=0.3):
    frames = []
    while True:
        try:
            frames.append(recv(ws, timeout))
        except AssertionError:
            return frames


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class SliceBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.orm import Session as SyncSession
        from sqlalchemy.pool import NullPool

        import backend.app.models  # noqa: F401
        from backend.app.core import db as dbmod
        from backend.app.core.security import hash_password
        from backend.app.main import app
        from backend.app.models import PolicyChunk, User
        from backend.app.adapters.assessment_runner import runner
        from backend.seed.seed import POLICY_CHUNKS

        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "slice.db").replace("\\", "/")
        sync = create_engine(f"sqlite:///{path}")
        dbmod.Base.metadata.create_all(sync)
        with SyncSession(sync) as s:
            for uid, name, role in (("u-exec1", "exec1", "executive"), ("u-exec2", "exec2", "executive"),
                                    ("u-sup", "sup1", "supervisor")):
                s.add(User(id=uid, username=name, password_hash=hash_password(PASSWORD), role=role,
                           display_name=name))
            for c in POLICY_CHUNKS:
                s.add(PolicyChunk(id=f"p-{c['key']}", source=c["source"], citation=c["citation"],
                                  text=c["text"], keywords=c["keywords"]))
            s.commit()
        sync.dispose()

        engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
        dbmod.attach_sqlite_pragmas(engine)
        cls._previous_factory = dbmod.session_factory()
        dbmod.use_session_factory(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
        cls.engine, cls.runner = engine, runner
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        from backend.app.core import db as dbmod

        cls.client.portal.call(cls.runner.drain)
        cls.client.__exit__(None, None, None)
        dbmod.use_session_factory(cls._previous_factory)
        cls.tmp.cleanup()

    # -- helpers --------------------------------------------------------
    def login(self, username):
        r = self.client.post("/auth/login", json={"username": username, "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        return {"Authorization": f"Bearer {r.json()['token']}"}

    def new_session(self, consent="granted", lang="hi", channel="mobile_chat"):
        r = self.client.post("/sessions", json={"channel": channel, "consent": consent, "lang": lang})
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        # PC-09: ws_url carries no token. The text-first slice still connects
        # with the transitional query token (CONTRACTS.md section 1, PC-05).
        body["connect"] = f"{body['ws_url']}?token={body['session_token']}"
        return body

    def settle(self):
        self.client.portal.call(self.runner.drain)

    def say(self, ws, text):
        ws.send_json({"type": "chat.message", "text": text, "lang": "hi"})
        frames = recv_until(ws, "session.status")
        self.settle()
        return frames

    def packet(self, case_id, who="exec1"):
        r = self.client.get(f"/cases/{case_id}", headers=self.login(who))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class TestVictimIsolation(SliceBase):
    def test_a_victim_socket_never_receives_assessment_data(self):
        s = self.new_session()
        exec_token = self.client.post("/auth/login", json={"username": "exec1", "password": PASSWORD}).json()["token"]
        with self.client.websocket_connect(s["connect"]) as victim, \
                self.client.websocket_connect(f"/ws/session/{s['session_id']}?token={exec_token}") as officer:
            recv_until(victim, "session.status")
            recv_until(officer, "session.status")
            victim_frames, officer_frames = [], []
            for text in TURNS:
                victim_frames += self.say(victim, text)
                victim_frames += drain(victim)
                officer_frames += drain(officer)

        victim_types = {f["type"] for f in victim_frames}
        self.assertTrue(victim_types <= {"assistant.turn", "transcript.line", "session.status", "timeline.update",
                                         "officer.message"}, victim_types)
        for frame in victim_frames:
            for key in ASSESSMENT_KEYS:
                self.assertNotIn(key, frame, f"{frame['type']} carried {key}")
        officer_types = {f["type"] for f in officer_frames}
        self.assertIn("dimension.update", officer_types)
        self.assertIn("alert.safety", officer_types)
        self.assertIn("escalation.packet", officer_types)

    def test_a_publisher_mistake_is_blocked_for_victims(self):
        from backend.app.ws.hub import hub

        s = self.new_session()
        with self.client.websocket_connect(s["connect"]) as victim:
            recv_until(victim, "session.status")
            before = hub.leaks_blocked
            self.client.portal.call(lambda: _async_publish(hub, s["session_id"], "assistant.turn",
                                                           {"turn_id": "t", "text": "x", "band": "Critical"}))
            self.assertEqual(drain(victim), [])
            self.assertEqual(hub.leaks_blocked, before + 1)

    def test_a_victim_token_cannot_open_another_session(self):
        from starlette.websockets import WebSocketDisconnect

        a, b = self.new_session(), self.new_session()
        with self.assertRaises((WebSocketDisconnect, Closed)):
            with self.client.websocket_connect(f"/ws/session/{b['session_id']}?token={a['session_token']}") as ws:
                recv(ws)

    def test_victim_timeline_is_own_case_only_and_assessment_free(self):
        from backend.app.ws.fanout import find_leaks

        a, b = self.new_session(), self.new_session()
        mine = self.client.get(f"/cases/{a['case_id']}/timeline", headers={"Authorization": f"Bearer {a['session_token']}"})
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(find_leaks(mine.json()), [])
        self.assertEqual(sorted(mine.json()), ["reference", "timeline"])
        theirs = self.client.get(f"/cases/{b['case_id']}/timeline", headers={"Authorization": f"Bearer {a['session_token']}"})
        self.assertEqual(theirs.status_code, 403)

    def test_victim_tokens_cannot_use_console_routes(self):
        s = self.new_session()
        h = {"Authorization": f"Bearer {s['session_token']}"}
        for path in ("/queue", f"/cases/{s['case_id']}", f"/cases/{s['case_id']}/audit"):
            self.assertEqual(self.client.get(path, headers=h).status_code, 403, path)


class TestAssessmentBehaviour(SliceBase):
    def run_turns(self, s, turns):
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            for t in turns:
                self.say(ws, t)

    def test_needs_human_assessment_hides_every_score(self):
        s = self.new_session()
        self.run_turns(s, TURNS[:1])
        p = self.packet(s["case_id"])
        a = p["assessment"]
        self.assertIsNone(a["svi"])
        self.assertIsNone(a["band"])
        self.assertTrue(all(d["score"] is None for d in a["dimensions"]))
        self.assertTrue(all(t["svi"] is None for t in p["trajectory"]))
        self.assertTrue(p["header"]["needs_human_assessment"])

    def test_score_appears_with_breakdown_confidence_and_provisional_flag(self):
        s = self.new_session()
        self.run_turns(s, TURNS)
        a = self.packet(s["case_id"])["assessment"]
        self.assertIsNotNone(a["band"])
        self.assertIsNotNone(a["aggregate_confidence"])
        self.assertEqual(len(a["dimensions"]), 9)
        self.assertTrue(a["weights_are_provisional"])
        d4 = next(d for d in a["dimensions"] if d["dimension"] == "D4")
        self.assertIsNone(d4["score"])  # acoustic: unavailable, not guessed

    def test_every_evidence_id_resolves_to_a_real_turn(self):
        s = self.new_session()
        self.run_turns(s, TURNS)
        p = self.packet(s["case_id"])
        ids = {t["id"] for t in p["transcript"]}
        linked = [i for d in p["assessment"]["dimensions"] for i in d["evidence_turn_ids"]]
        linked += [i for a in p["alerts"] for i in a["evidence_turn_ids"]]
        linked += [i for r in p["recommendations"] for i in r["evidence_turn_ids"]]
        self.assertTrue(linked)
        self.assertLessEqual(set(linked), ids)

    def test_consent_declined_suppresses_assessment(self):
        s = self.new_session(consent="declined")
        self.assertEqual(self.packet(s["case_id"])["header"]["session_state"], "SH")
        self.run_turns(s, TURNS)
        p = self.packet(s["case_id"])
        self.assertTrue(p["assessment"]["suppressed"])
        self.assertEqual(p["trajectory"], [])
        self.assertEqual(p["recommendations"], [])
        self.assertEqual(p["alerts"], [])

    def test_crisis_forces_sx_critical_alert_and_takeover_and_never_resumes(self):
        s = self.new_session()
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            self.say(ws, TURNS[0])
            frames = self.say(ws, "Ab aur nahi jee sakti, main jaan de dungi.")
            self.assertEqual(frames[-1]["state"], "SX")
            self.assertNotIn("assistant.turn", [f["type"] for f in frames])  # SX unapproved: silent
            frames = self.say(ws, "Koi hai?")
            self.assertEqual(frames[-1]["state"], "SX")
            self.assertNotIn("assistant.turn", [f["type"] for f in frames])
        p = self.packet(s["case_id"])
        self.assertEqual(p["header"]["band"], "Critical")
        self.assertTrue(p["header"]["takeover_requested"])
        self.assertIn(("crisis", "critical"), [(a["alert_type"], a["severity"]) for a in p["alerts"]])
        q = self.client.get("/queue", headers=self.login("exec1")).json()
        self.assertEqual(q[0]["case_id"], s["case_id"])

    def test_reprocessing_does_not_duplicate_alerts(self):
        from backend.app.workers.assessment import run_cycle

        s = self.new_session()
        self.run_turns(s, TURNS)
        before = self.packet(s["case_id"])["alerts"]
        self.client.portal.call(run_cycle, s["case_id"])
        self.client.portal.call(run_cycle, s["case_id"])
        after = self.packet(s["case_id"])["alerts"]
        self.assertEqual(len(before), len(after))
        self.assertEqual(len({a["alert_type"] for a in after}), len(after))


class TestCasework(SliceBase):
    def ready_case(self):
        s = self.new_session()
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            for t in TURNS:
                self.say(ws, t)
        return s

    def test_claim_is_safe_against_duplicates(self):
        s = self.ready_case()
        h1, h2 = self.login("exec1"), self.login("exec2")
        self.assertEqual(self.client.post(f"/cases/{s['case_id']}/claim", headers=h1).status_code, 200)
        self.assertEqual(self.client.post(f"/cases/{s['case_id']}/claim", headers=h1).status_code, 200)
        r = self.client.post(f"/cases/{s['case_id']}/claim", headers=h2)
        self.assertEqual(r.status_code, 409)

    def test_actions_require_the_claim(self):
        s = self.ready_case()
        h = self.login("exec1")
        self.assertEqual(self.client.post(f"/cases/{s['case_id']}/takeover", headers=h).status_code, 409)
        rec = self.packet(s["case_id"])["recommendations"][0]
        r = self.client.post(f"/cases/{s['case_id']}/decisions", headers=h,
                             json={"action_id": rec["action_id"], "decision": "confirm"})
        self.assertEqual(r.status_code, 409)

    def test_blank_override_reason_is_400(self):
        s = self.ready_case()
        h = self.login("exec1")
        self.client.post(f"/cases/{s['case_id']}/claim", headers=h)
        for body in ({"band": "High"}, {"band": "High", "reason": ""}, {"band": "High", "reason": "   "}):
            r = self.client.post(f"/cases/{s['case_id']}/override", headers=h, json=body)
            self.assertEqual(r.status_code, 400, body)
        r = self.client.post(f"/cases/{s['case_id']}/override", headers=h,
                             json={"band": "High", "reason": "officer judgement"})
        self.assertEqual(r.status_code, 200)

    def test_duplicate_acknowledgement_is_safe(self):
        s = self.ready_case()
        h = self.login("exec1")
        alert = self.packet(s["case_id"])["alerts"][0]
        first = self.client.post(f"/cases/{s['case_id']}/alerts/{alert['id']}/ack", headers=h).json()
        second = self.client.post(f"/cases/{s['case_id']}/alerts/{alert['id']}/ack", headers=self.login("exec2")).json()
        self.assertEqual(first, second)  # the first acknowledgement stands
        audit = self.client.get(f"/cases/{s['case_id']}/audit", headers=h).json()
        acks = [e for e in audit if e["action"] == "alert.acknowledged" and e["detail"]["alert_id"] == alert["id"]]
        self.assertEqual(len(acks), 1)

    def test_decisions_stay_separate_and_only_confirmation_reaches_the_victim(self):
        s = self.ready_case()
        h = self.login("exec1")
        self.client.post(f"/cases/{s['case_id']}/claim", headers=h)
        vh = {"Authorization": f"Bearer {s['session_token']}"}
        def stages():
            body = self.client.get(f"/cases/{s['case_id']}/timeline", headers=vh).json()
            return [e["stage"] for e in body["timeline"]]

        self.assertNotIn("action_taken", stages())  # recommendations alone do nothing

        recs = self.packet(s["case_id"])["recommendations"]
        self.assertGreaterEqual(len(recs), 2)
        r = self.client.post(f"/cases/{s['case_id']}/decisions", headers=h,
                             json={"action_id": recs[0]["action_id"], "decision": "reject"})
        self.assertEqual(r.status_code, 400)  # reject needs a rationale
        self.client.post(f"/cases/{s['case_id']}/decisions", headers=h,
                         json={"action_id": recs[0]["action_id"], "decision": "reject", "rationale": "not wanted"})
        self.assertNotIn("action_taken", stages())
        ok = self.client.post(f"/cases/{s['case_id']}/decisions", headers=h,
                              json={"action_id": recs[1]["action_id"], "decision": "confirm"})
        self.assertEqual(ok.status_code, 200)
        again = self.client.post(f"/cases/{s['case_id']}/decisions", headers=h,
                                 json={"action_id": recs[1]["action_id"], "decision": "confirm"})
        self.assertEqual(again.json()["decision_id"], ok.json()["decision_id"])  # idempotent
        clash = self.client.post(f"/cases/{s['case_id']}/decisions", headers=h,
                                 json={"action_id": recs[1]["action_id"], "decision": "reject", "rationale": "x"})
        self.assertEqual(clash.status_code, 409)
        self.assertEqual(stages().count("action_taken"), 1)

        p = self.packet(s["case_id"])
        self.assertEqual(len(p["decisions"]), 2)
        for rec in p["recommendations"]:
            self.assertNotIn("decision", rec)
            self.assertNotIn("officer", rec)

    def test_body_officer_id_must_be_the_caller(self):
        s = self.ready_case()
        h = self.login("exec1")
        self.client.post(f"/cases/{s['case_id']}/claim", headers=h)
        rec = self.packet(s["case_id"])["recommendations"][0]
        r = self.client.post(f"/cases/{s['case_id']}/decisions", headers=h,
                             json={"action_id": rec["action_id"], "decision": "confirm", "officer_id": "u-exec2"})
        self.assertEqual(r.status_code, 403)

    def test_takeover_mutes_the_assistant_and_tells_the_victim(self):
        s = self.ready_case()
        h = self.login("exec1")
        self.client.post(f"/cases/{s['case_id']}/claim", headers=h)
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            self.assertEqual(self.client.post(f"/cases/{s['case_id']}/takeover", headers=h).status_code, 200)
            frames = recv_until(ws, "session.status")
            self.assertTrue(frames[-1]["human_joined"])
            frames = self.say(ws, "Hello?")
            self.assertNotIn("assistant.turn", [f["type"] for f in frames])
        self.assertEqual(self.client.post(f"/cases/{s['case_id']}/takeover", headers=h).status_code, 200)

    def test_supervisor_reads_queue_but_executive_boundary_holds(self):
        s = self.ready_case()
        sup = self.login("sup1")
        cid = s["case_id"]
        self.assertEqual(self.client.get("/queue", headers=sup).status_code, 200)
        self.assertEqual(self.client.get(f"/cases/{cid}", headers=sup).status_code, 200)
        self.assertEqual(self.client.get(f"/cases/{cid}/audit", headers=sup).status_code, 200)
        # PC-06: the supervisor view is read-only. Every write is 403.
        alert = self.packet(cid)["alerts"][0]
        rec = self.packet(cid)["recommendations"][0]
        writes = (
            (f"/cases/{cid}/claim", None),
            (f"/cases/{cid}/alerts/{alert['id']}/ack", None),
            (f"/cases/{cid}/decisions", {"action_id": rec["action_id"], "decision": "confirm"}),
            (f"/cases/{cid}/override", {"band": "High", "reason": "x"}),
            (f"/cases/{cid}/takeover", None),
            (f"/cases/{cid}/messages", {"text": "hello"}),
        )
        for path, body in writes:
            r = self.client.post(path, headers=sup, json=body)
            self.assertEqual(r.status_code, 403, path)
        self.assertIsNone(self.packet(cid)["header"]["assigned_officer_id"])


class TestReconnectAndErrors(SliceBase):
    def test_reconnect_resumes_from_the_database(self):
        s = self.new_session()
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            self.say(ws, TURNS[0])
        with self.client.websocket_connect(s["connect"]) as ws:
            snap = recv_until(ws, "session.status")[-1]
            self.assertEqual(snap["state"], "S1")
            self.say(ws, TURNS[1])
        p = self.packet(s["case_id"])
        seqs = [t["seq"] for t in p["transcript"]]
        self.assertEqual(seqs, sorted(set(seqs)))  # contiguous, no duplicates
        self.assertEqual([t["text"] for t in p["transcript"] if t["speaker"] == "victim"], TURNS[:2])

    def test_ended_session_rejects_new_turns(self):
        s = self.new_session()
        vh = {"Authorization": f"Bearer {s['session_token']}"}
        r = self.client.post(f"/sessions/{s['session_id']}/end", headers=vh)
        self.assertEqual(r.json()["reference_no"], s["reference_no"])
        with self.client.websocket_connect(s["connect"]) as ws:
            recv_until(ws, "session.status")
            ws.send_json({"type": "chat.message", "text": "still there?"})
            recv_until(ws, "session.status")
        self.assertEqual([t for t in self.packet(s["case_id"])["transcript"] if t["speaker"] == "victim"], [])

    def test_validation_errors_do_not_echo_input(self):
        secret_text = "fictional narrative that must not be echoed"
        r = self.client.post("/sessions", json={"channel": secret_text, "consent": "granted"})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(secret_text, r.text)
        self.assertNotIn("input", r.text)

    def test_logs_contain_no_tokens_or_narrative(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        root.addHandler(handler)
        old = root.level
        root.setLevel(logging.DEBUG)
        try:
            s = self.new_session()
            with self.client.websocket_connect(s["connect"]) as ws:
                recv_until(ws, "session.status")
                for t in TURNS:
                    self.say(ws, t)
        finally:
            root.removeHandler(handler)
            root.setLevel(old)
        text = stream.getvalue()
        self.assertNotIn("eyJ", text)
        for t in TURNS:
            self.assertNotIn(t[:30], text)


class TestHubAndStorage(unittest.TestCase):
    def test_a_slow_client_never_blocks_publishing(self):
        import asyncio

        from backend.app.ws.hub import Connection, Hub

        async def scenario():
            hub = Hub()
            got = []
            blocked = asyncio.Event()

            async def slow_send(_):
                await blocked.wait()  # never returns

            async def fast_send(frame):
                got.append(frame)

            async def close():
                pass

            slow = hub.subscribe(Connection("slow", "s1", "executive", slow_send, close))
            hub.subscribe(Connection("fast", "s1", "executive", fast_send, close))
            loop = asyncio.get_running_loop()
            publish_time = 0.0
            for i in range(400):
                start = loop.time()
                hub.publish("s1", "escalation.packet", {"case_id": str(i)})
                publish_time += loop.time() - start
                # Real publishers yield between events (a turn emits a handful);
                # this lets healthy subscribers drain while the stalled one fills.
                await asyncio.sleep(0)
            await asyncio.sleep(0.05)
            return publish_time, len(got), slow.dropped, hub.slow_disconnects

        elapsed, delivered, dropped, disconnects = asyncio.run(scenario())
        self.assertLess(elapsed, 0.5)
        self.assertEqual(delivered, 400)
        self.assertTrue(dropped)
        self.assertEqual(disconnects, 1)

    def test_storage_refuses_paths_outside_its_root(self):
        from backend.app.adapters.storage import LocalStorage, UnsafePath

        with tempfile.TemporaryDirectory() as root:
            st = LocalStorage(root)
            p = st.put(b"x", "session-1", "turn-1.bin")
            self.assertTrue(str(p).startswith(str(st.root)))
            self.assertTrue(st.delete("session-1", "turn-1.bin"))
            for bad in (("..", "x"), ("../../.env",), ("a/b",), ("C:\\x",), ("",)):
                with self.assertRaises(UnsafePath, msg=bad):
                    st.path_for(*bad)


class TestFixtures(unittest.TestCase):
    def test_no_real_identifiers_in_seeds_or_fixtures(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1]
        files = [root / "seed" / "seed.py", root / "scenarios" / "data.py", pathlib.Path(__file__)]
        patterns = {
            "phone number": re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
            "Aadhaar-like number": re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)"),
            "email address": re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I),
        }
        for f in files:
            text = f.read_text(encoding="utf-8")
            for label, pattern in patterns.items():
                self.assertIsNone(pattern.search(text), f"{label} in {f.name}")
        self.assertIn("fictional", (root / "scenarios" / "data.py").read_text(encoding="utf-8").lower())


async def _async_publish(hub, session_id, event_type, payload):
    hub.publish(session_id, event_type, payload)


if __name__ == "__main__":
    unittest.main()
