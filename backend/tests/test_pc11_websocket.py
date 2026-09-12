"""PC-11 exact WebSocket protocol and durable idempotency tests."""

import asyncio
import unittest
from unittest.mock import patch

from backend.tests.test_contract_decisions import DecisionBase
from backend.tests.test_vertical_slice import Closed, HAVE_DEPS, recv, recv_until


@unittest.skipUnless(HAVE_DEPS, "backend packages not installed")
class TestPC11Protocol(DecisionBase):
    def close_code(self, session, frame=None, *, query=""):
        with self.client.websocket_connect(session["ws_url"] + query) as ws:
            if frame is not None:
                if isinstance(frame, bytes):
                    ws.send_bytes(frame)
                elif isinstance(frame, str):
                    ws.send_text(frame)
                else:
                    ws.send_json(frame)
            with self.assertRaises(Closed) as closed:
                recv(ws, timeout=7)
            return closed.exception.args[0]

    def test_auth_ok_is_first_and_snapshot_follows(self):
        session = self.new_session()
        with self.client.websocket_connect(session["ws_url"]) as ws:
            ws.send_json({"type": "auth", "token": session["session_token"]})
            self.assertEqual(recv(ws), {"type": "auth.ok", "session_id": session["session_id"], "role": "victim"})
            self.assertEqual(recv_until(ws, "session.status")[-1]["state"], "S1")

    def test_authentication_timeout_and_post_connect_expiry_close_without_reason(self):
        from backend.app.core.security import InvalidToken, decode_token

        session = self.new_session()
        with self.client.websocket_connect(session["ws_url"]) as ws:
            with self.assertRaises(Closed) as closed:
                recv(ws, timeout=7)
            self.assertEqual(closed.exception.args, (4401, ""))

        claims = decode_token(session["session_token"])
        with patch("backend.app.ws.session.decode_token", side_effect=[claims, InvalidToken("expired")]):
            with self.client.websocket_connect(session["ws_url"]) as ws:
                ws.send_json({"type": "auth", "token": session["session_token"]})
                self.assertEqual(recv(ws)["type"], "auth.ok")
                recv_until(ws, "session.status")
                ws.send_json({"type": "request_human", "request_id": "h:1"})
                with self.assertRaises(Closed) as closed:
                    recv(ws)
                self.assertEqual(closed.exception.args, (4401, ""))

    def test_query_and_malformed_pre_authentication_frames_fail_closed(self):
        session = self.new_session()
        self.assertEqual(self.close_code(session, query="?token=unexpected"), 4400)
        self.assertEqual(self.close_code(session, "{"), 4400)
        self.assertEqual(self.close_code(session, b"binary"), 4400)
        self.assertEqual(self.close_code(session, {"type": "chat.message"}), 4400)
        self.assertEqual(self.close_code(session, {"type": "auth"}), 4401)
        self.assertEqual(self.close_code(session, {"type": "auth", "token": ""}), 4401)
        self.assertEqual(self.close_code(session, {"type": "auth", "token": "bad"}), 4401)
        self.assertEqual(self.close_code(session, {"type": "auth", "token": session["session_token"], "extra": True}), 4400)

    def test_valid_victim_identity_cannot_access_another_path_session(self):
        first, second = self.new_session(), self.new_session()
        self.assertEqual(self.close_code(second, {"type": "auth", "token": first["session_token"]}), 4403)

    def test_malformed_post_auth_frames_and_staff_actions_close(self):
        session = self.new_session()
        bad_frames = [
            "{", b"binary", {"type": "unknown"},
            {"type": "chat.message", "client_message_id": "m:0", "text": "x", "lang": "hi"},
            {"type": "chat.message", "client_message_id": "m:1", "text": "x", "lang": "hi", "extra": 1},
        ]
        for frame in bad_frames:
            with self.subTest(frame=repr(frame)):
                with self.socket(session) as ws:
                    recv_until(ws, "session.status")
                    if isinstance(frame, bytes):
                        ws.send_bytes(frame)
                    elif isinstance(frame, str):
                        ws.send_text(frame)
                    else:
                        ws.send_json(frame)
                    with self.assertRaises(Closed) as closed:
                        recv(ws)
                    self.assertEqual(closed.exception.args[0], 4400)

        token = self.client.post("/auth/login", json={"username": "exec1", "password": "test-only-not-a-real-password"}).json()["token"]
        with self.socket(session, token) as ws:
            recv_until(ws, "session.status")
            ws.send_json({"type": "request_human", "request_id": "h:1"})
            with self.assertRaises(Closed) as closed:
                recv(ws)
            self.assertEqual(closed.exception.args[0], 4403)

    def test_chat_ack_is_post_commit_and_retry_is_idempotent(self):
        session = self.new_session(lang="en")
        with self.socket(session) as ws:
            recv_until(ws, "session.status")
            ws.send_json({"type": "chat.message", "client_message_id": "m:1", "text": "  Fictional text.  ", "lang": "en"})
            accepted = recv(ws)
            self.assertEqual(accepted["status"], "accepted")
            self.assertTrue(accepted["turn_id"])
            recv_until(ws, "session.status")

            ws.send_json({"type": "chat.message", "client_message_id": "m:1", "text": "Fictional text.", "lang": "en"})
            duplicate = recv(ws)
            self.assertEqual(duplicate, {"type": "chat.ack", "client_message_id": "m:1",
                                         "status": "duplicate", "turn_id": accepted["turn_id"]})

            ws.send_json({"type": "chat.message", "client_message_id": "m:1", "text": "Different fictional text.", "lang": "en"})
            self.assertEqual(recv(ws), {"type": "chat.ack", "client_message_id": "m:1",
                                        "status": "rejected", "error": "id_conflict"})
            ws.send_json({"type": "chat.message", "client_message_id": "m:2", "text": "Language mismatch", "lang": "hi"})
            self.assertEqual(recv(ws), {"type": "chat.ack", "client_message_id": "m:2",
                                        "status": "rejected", "error": "not_permitted"})

        rows = self.db("SELECT client_message_id, text, lang FROM turns WHERE session_id=? AND speaker='victim'", session["session_id"])
        self.assertEqual(rows, [("m:1", "Fictional text.", "en")])

    def test_human_request_is_causal_atomic_and_available_after_decline(self):
        session = self.new_session(consent="declined", lang="en")
        with self.socket(session) as ws:
            recv_until(ws, "session.status")
            ws.send_json({"type": "request_human", "request_id": "h:1"})
            self.assertEqual(recv(ws), {"type": "human_request.ack", "request_id": "h:1", "status": "accepted"})
            self.assertEqual(recv_until(ws, "session.status")[-1]["state"], "SH")
            ws.send_json({"type": "request_human", "request_id": "h:1"})
            self.assertEqual(recv(ws), {"type": "human_request.ack", "request_id": "h:1", "status": "duplicate"})
        self.assertEqual(self.db("SELECT request_id FROM human_requests WHERE session_id=?", session["session_id"]), [("h:1",)])
        self.assertEqual(self.db("SELECT state FROM sessions WHERE id=?", session["session_id"]), [("SH",)])

    def test_internal_failure_sends_no_ack_and_closes_1011(self):
        session = self.new_session()
        with patch("backend.app.ws.session.intake.request_human", side_effect=RuntimeError("private detail")):
            with self.socket(session) as ws:
                recv_until(ws, "session.status")
                ws.send_json({"type": "request_human", "request_id": "h:1"})
                with self.assertRaises(Closed) as closed:
                    recv(ws)
                self.assertEqual(closed.exception.args[0], 1011)
        self.assertEqual(self.db("SELECT count(*) FROM human_requests WHERE session_id=?", session["session_id"]), [(0,)])

    def test_concurrent_duplicates_create_exactly_one_row(self):
        from backend.app.core.db import session_factory
        from backend.app.services import intake

        chat = self.new_session(consent="declined", lang="en")
        human = self.new_session(consent="declined", lang="en")

        async def chat_once():
            async with session_factory()() as db:
                out = await intake.submit_turn(db, chat["session_id"], "Concurrent fictional text.", "en", client_message_id="m:1")
                await db.commit()
                return out.idempotency_status, out.persisted_id

        async def human_once():
            async with session_factory()() as db:
                out = await intake.request_human(db, human["session_id"], "h:1")
                await db.commit()
                return out.idempotency_status

        chat_results = self.client.portal.call(lambda: asyncio.gather(chat_once(), chat_once()))
        human_results = self.client.portal.call(lambda: asyncio.gather(human_once(), human_once()))
        self.assertEqual(sorted(status for status, _ in chat_results), ["accepted", "duplicate"])
        self.assertEqual(len({turn_id for _, turn_id in chat_results}), 1)
        self.assertEqual(sorted(human_results), ["accepted", "duplicate"])
        self.assertEqual(self.db("SELECT count(*) FROM turns WHERE session_id=? AND client_message_id='m:1'", chat["session_id"]), [(1,)])
        self.assertEqual(self.db("SELECT count(*) FROM human_requests WHERE session_id=? AND request_id='h:1'", human["session_id"]), [(1,)])


if __name__ == "__main__":
    unittest.main()
