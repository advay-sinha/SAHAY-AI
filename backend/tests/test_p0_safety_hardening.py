"""Regression tests for the Task 2 P0 backend safety boundaries.

All submitted text is short, synthetic, and explicitly fictional. The tests
reuse the existing disposable SQLite/TestClient harness and use synchronization
events, rather than timing sleeps, for the takeover race.
"""

import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

from backend.tests.test_contract_decisions import DecisionBase
from backend.tests.test_vertical_slice import ASSESSMENT_KEYS, HAVE_DEPS


ANALYSIS_EVENT_TYPES = {
    "action.recommended",
    "alert.safety",
    "case.structured",
    "dimension.update",
    "escalation.packet",
}


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestP0SafetyHardening(DecisionBase):
    def submit_and_publish(self, session, text):
        from backend.app.core.db import session_factory
        from backend.app.services import intake
        from backend.app.services.events import publish

        async def submit():
            async with session_factory()() as db:
                out = await intake.submit_turn(db, session["session_id"], text, "en")
                await db.commit()
            publish(session["session_id"], session["case_id"], out)
            return out

        return self.client.portal.call(submit)

    def test_pending_and_declined_turns_bypass_every_ai_entry_point(self):
        from backend.app.services import events, intake

        for consent in ("pending", "declined"):
            with self.subTest(consent=consent):
                session = self.new_session(consent=consent, lang="en")
                with ExitStack() as stack:
                    spies = {
                        name: stack.enter_context(
                            patch.object(
                                intake,
                                name,
                                side_effect=AssertionError(
                                    f"{name} must not run without granted consent"
                                ),
                            )
                        )
                        for name in (
                            "crisis_check",
                            "extract",
                            "dialogue_slots",
                            "dialogue_next",
                            "plan_turn",
                        )
                    }
                    provider = stack.enter_context(
                        patch.object(
                            intake,
                            "get_provider",
                            side_effect=AssertionError(
                                "the LLM provider must not be requested"
                            ),
                        )
                    )
                    schedule = stack.enter_context(
                        patch.object(events.runner, "schedule")
                    )
                    out = self.submit_and_publish(
                        session, "Fictional consent-gate test turn."
                    )

                self.assertFalse(out.schedule_assessment)
                self.assertEqual(
                    [event for event, _payload in out.events],
                    ["transcript.line", "session.status"],
                )
                for spy in (*spies.values(), provider, schedule):
                    spy.assert_not_called()
                self.assertEqual(
                    self.db(
                        "SELECT count(*) FROM turns WHERE session_id=? AND speaker='victim'",
                        session["session_id"],
                    ),
                    [(1,)],
                )
                self.assertEqual(
                    self.db(
                        "SELECT count(*) FROM assessments WHERE case_id=?",
                        session["case_id"],
                    ),
                    [(0,)],
                )
                self.assertEqual(
                    self.db(
                        "SELECT count(*) FROM recommendations WHERE case_id=?",
                        session["case_id"],
                    ),
                    [(0,)],
                )

    def test_declined_crisis_like_text_creates_no_ai_artifact_or_event(self):
        from backend.app.services import intake
        from backend.app.ws.hub import hub

        session = self.new_session(consent="declined", lang="en")
        with (
            patch.object(intake, "crisis_check", wraps=intake.crisis_check) as crisis,
            patch.object(hub, "publish", wraps=hub.publish) as published,
        ):
            out = self.submit_and_publish(
                session, "Fictional test speaker says: I want to die."
            )

        crisis.assert_not_called()
        self.assertFalse(out.schedule_assessment)
        self.assertFalse(
            any(
                call.args[1] in ANALYSIS_EVENT_TYPES
                for call in published.call_args_list
            )
        )
        for table in ("alerts", "assessments", "recommendations"):
            self.assertEqual(
                self.db(
                    f"SELECT count(*) FROM {table} WHERE case_id=?", session["case_id"]
                ),
                [(0,)],
            )
        self.assertEqual(
            self.db("SELECT band FROM cases WHERE id=?", session["case_id"]), [(None,)]
        )

    def test_granted_consent_keeps_the_existing_processing_path(self):
        from backend.app.services import intake

        session = self.new_session(consent="granted", lang="en")
        with (
            patch.object(intake, "crisis_check", wraps=intake.crisis_check) as crisis,
            patch.object(intake, "extract", wraps=intake.extract) as extract,
            patch.object(
                intake, "dialogue_slots", wraps=intake.dialogue_slots
            ) as slots,
            patch.object(intake, "plan_turn", wraps=intake.plan_turn) as dialogue,
        ):
            out = self.submit_and_publish(
                session, "Fictional accepted-consent processing turn."
            )
        self.settle()

        for spy in (crisis, extract, slots, dialogue):
            spy.assert_called()
        self.assertTrue(out.schedule_assessment)
        self.assertEqual(
            self.db(
                "SELECT count(*) FROM assessments WHERE case_id=?", session["case_id"]
            ),
            [(1,)],
        )

    def test_post_takeover_turn_bypasses_ai_but_is_retained_for_the_officer(self):
        from backend.app.services import events, intake

        session = self.new_session(consent="granted", lang="en")
        owner = self.login("exec1")
        self.assertEqual(
            self.client.post(
                f"/cases/{session['case_id']}/claim", headers=owner
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/cases/{session['case_id']}/takeover", headers=owner
            ).status_code,
            200,
        )

        with ExitStack() as stack:
            spies = {
                name: stack.enter_context(
                    patch.object(
                        intake,
                        name,
                        side_effect=AssertionError(
                            f"{name} must not run after takeover"
                        ),
                    )
                )
                for name in (
                    "crisis_check",
                    "extract",
                    "dialogue_slots",
                    "dialogue_next",
                    "plan_turn",
                )
            }
            provider = stack.enter_context(
                patch.object(
                    intake,
                    "get_provider",
                    side_effect=AssertionError("LLM access after takeover"),
                )
            )
            schedule = stack.enter_context(patch.object(events.runner, "schedule"))
            out = self.submit_and_publish(
                session, "Fictional post-takeover turn for the officer."
            )

        self.assertFalse(out.schedule_assessment)
        self.assertEqual(
            [event for event, _payload in out.events],
            ["transcript.line", "session.status"],
        )
        for spy in (*spies.values(), provider, schedule):
            spy.assert_not_called()
        self.assertEqual(
            self.db(
                "SELECT speaker FROM turns WHERE session_id=? ORDER BY seq",
                session["session_id"],
            ),
            [("victim",)],
        )
        for table in ("alerts", "assessments", "recommendations"):
            self.assertEqual(
                self.db(
                    f"SELECT count(*) FROM {table} WHERE case_id=?", session["case_id"]
                ),
                [(0,)],
            )

    def test_post_takeover_officer_message_and_access_controls_remain_intact(self):
        session = self.new_session(consent="granted", lang="en")
        owner = self.login("exec1")
        other = self.login("exec2")
        supervisor = self.login("sup1")
        case_id = session["case_id"]
        url = f"/cases/{case_id}/messages"

        self.client.post(f"/cases/{case_id}/claim", headers=owner)
        self.client.post(f"/cases/{case_id}/takeover", headers=owner)
        body = {"text": "Fictional officer test message.", "lang": "en"}
        self.assertEqual(
            self.client.post(url, headers=owner, json=body).status_code, 201
        )
        self.assertEqual(
            self.client.post(url, headers=other, json=body).status_code, 409
        )
        self.assertEqual(
            self.client.post(url, headers=supervisor, json=body).status_code, 403
        )
        self.assertEqual(
            self.db(
                "SELECT count(*) FROM turns WHERE session_id=? AND speaker='officer'",
                session["session_id"],
            ),
            [(1,)],
        )

    def test_in_flight_assessment_is_discarded_when_takeover_completes_first(self):
        from backend.app.adapters.assessment_runner import runner
        from backend.app.ws.hub import hub

        started = threading.Event()
        release = threading.Event()
        session = self.new_session(consent="granted", lang="en")
        owner = self.login("exec1")
        self.client.post(f"/cases/{session['case_id']}/claim", headers=owner)

        async def controlled_slow_operation(fn, *args):
            started.set()
            await asyncio.to_thread(release.wait)
            return fn(*args)

        try:
            with (
                patch.object(runner, "in_thread", new=controlled_slow_operation),
                patch.object(hub, "publish", wraps=hub.publish) as published,
            ):
                self.submit_and_publish(
                    session,
                    "Fictional accepted turn long enough for assessment processing.",
                )
                self.assertTrue(
                    started.wait(timeout=5),
                    "assessment did not reach the controlled slow operation",
                )
                takeover = self.client.post(
                    f"/cases/{session['case_id']}/takeover", headers=owner
                )
                self.assertEqual(takeover.status_code, 200, takeover.text)
                release.set()
                self.settle()
        finally:
            release.set()
            self.settle()

        for table in ("assessments", "alerts", "recommendations"):
            self.assertEqual(
                self.db(
                    f"SELECT count(*) FROM {table} WHERE case_id=?", session["case_id"]
                ),
                [(0,)],
            )
        self.assertEqual(
            self.db("SELECT band, svi FROM cases WHERE id=?", session["case_id"]),
            [(None, None)],
        )
        self.assertFalse(
            any(
                call.args[1] in ANALYSIS_EVENT_TYPES
                for call in published.call_args_list
            )
        )

    def test_assessment_completed_before_takeover_retains_existing_behavior(self):
        from backend.app.ws.hub import hub

        session = self.new_session(consent="granted", lang="en")
        with patch.object(hub, "publish", wraps=hub.publish) as published:
            self.submit_and_publish(
                session, "Fictional accepted turn completed before takeover begins."
            )
            self.settle()
        self.assertEqual(
            self.db(
                "SELECT count(*) FROM assessments WHERE case_id=?", session["case_id"]
            ),
            [(1,)],
        )
        self.assertTrue(
            any(call.args[1] == "dimension.update" for call in published.call_args_list)
        )

        owner = self.login("exec1")
        self.client.post(f"/cases/{session['case_id']}/claim", headers=owner)
        self.assertEqual(
            self.client.post(
                f"/cases/{session['case_id']}/takeover", headers=owner
            ).status_code,
            200,
        )

    def test_non_speakable_dialogue_never_reaches_llm_or_victim_output(self):
        from backend.app.services import turn_loop
        from ml.dialogue.states import State

        llm = Mock()
        llm.phrase.return_value = "Thank you for sharing."
        with patch.object(
            turn_loop, "is_speakable", return_value=False, create=True
        ) as speakable:
            result = turn_loop.plan_turn(
                State.S1_FREE_NARRATIVE,
                {},
                "Fictional non-speakable dialogue test.",
                {"lang": "en"},
                llm,
            )

        speakable.assert_called_once_with("en")
        llm.phrase.assert_not_called()
        self.assertIsNone(result["text"])

        session = self.new_session(consent="granted", lang="en")
        with patch.object(turn_loop, "is_speakable", return_value=False, create=True):
            out = self.submit_and_publish(
                session, "Fictional raw-template suppression turn."
            )
        payloads = [payload for _event, payload in out.events]
        self.assertNotIn("assistant.turn", [event for event, _payload in out.events])
        self.assertNotIn("Thank you for telling me. Please go on.", str(payloads))
        for payload in payloads:
            for key in ASSESSMENT_KEYS:
                self.assertNotIn(key, payload)

    def test_speakable_dialogue_uses_existing_llm_and_guardrail_path(self):
        from backend.app.services import turn_loop
        from ml.dialogue.states import State

        llm = Mock()
        llm.phrase.return_value = "Thank you for sharing."
        with (
            patch.object(
                turn_loop, "is_speakable", return_value=True, create=True
            ) as speakable,
            patch.object(turn_loop, "validate", wraps=turn_loop.validate) as validate,
        ):
            result = turn_loop.plan_turn(
                State.S1_FREE_NARRATIVE,
                {},
                "Fictional speakable dialogue test.",
                {"lang": "en"},
                llm,
            )

        speakable.assert_called_once_with("en")
        llm.phrase.assert_called_once()
        validate.assert_called_once()
        self.assertEqual(result["text"], "Thank you for sharing.")
        self.assertFalse(result["was_fallback"])

    def test_human_request_remains_available_when_dialogue_fails_closed(self):
        from backend.app.core.db import session_factory
        from backend.app.services import intake

        session = self.new_session(consent="pending", lang="en")
        self.assertTrue(session["human_request_available"])

        async def request():
            async with session_factory()() as db:
                out = await intake.request_human(db, session["session_id"])
                await db.commit()
            return out

        out = self.client.portal.call(request)
        self.assertEqual([event for event, _payload in out.events], ["session.status"])
        self.assertEqual(out.events[0][1]["state"], "SH")
        self.assertFalse(out.events[0][1]["human_joined"])

    def test_health_exposes_only_generic_readiness_values(self):
        from backend.app import main

        marker = "synthetic-private-db-marker"
        synthetic = SimpleNamespace(
            APP_ENV="synthetic-environment-marker",
            LLM_PROVIDER="synthetic-provider-marker",
            ASSESSMENT_RUNNER="synthetic-runner-marker",
            DATABASE_URL=f"postgresql://synthetic-user:synthetic-password@private-host/{marker}?mode=test",
        )
        with patch.object(main, "settings", synthetic):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "status",
                "app_env",
                "llm_provider",
                "assessment_runner",
                "database",
                "fixed_scripts_ready",
                "detail",
            },
        )
        self.assertEqual(body["status"], "ok")
        self.assertEqual(
            {body["app_env"], body["llm_provider"], body["assessment_runner"]},
            {"ready"},
        )
        self.assertEqual(body["database"], "configured")
        serialized = response.text
        for forbidden in (
            synthetic.DATABASE_URL,
            marker,
            "synthetic-user",
            "synthetic-password",
            "private-host",
            "mode=test",
            synthetic.APP_ENV,
            synthetic.LLM_PROVIDER,
            synthetic.ASSESSMENT_RUNNER,
            "Traceback",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
