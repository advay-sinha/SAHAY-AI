"""Guardrailed phrasing (EXT-132): adapters, register, meaning check, fallbacks."""

import importlib.util
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import Mock, patch

from backend.app.adapters import llm as adapters
from backend.app.services import turn_loop
from ml.dialogue import intents
from ml.dialogue.states import State

HAVE_SETTINGS = importlib.util.find_spec("pydantic_settings") is not None

VICTIM_TEXT = "Fictional test: they came to my house again yesterday."


def plan(utterance, lang, model, state=State.S2_IMMEDIATE_SAFETY):
    with patch.object(turn_loop, "is_speakable", return_value=True, create=True):
        return turn_loop.plan_turn(state, {"narrative": "x"}, utterance, {"lang": lang}, model)


class TestPlanTurnWithAModel(unittest.TestCase):
    def test_the_model_never_receives_the_persons_words(self):
        model = Mock()
        model.phrase.return_value = None
        plan(VICTIM_TEXT, "en", model)
        args, kwargs = model.phrase.call_args
        self.assertNotIn(VICTIM_TEXT, json.dumps([args, kwargs]))
        self.assertEqual(kwargs["register"], "en")

    def test_an_english_rewording_that_changes_meaning_falls_back(self):
        model = Mock()
        model.phrase.return_value = "Did you hear anything last night?"
        result = plan(VICTIM_TEXT, "en", model, state=State.S3_MEDICAL_NEED)
        self.assertEqual(result["guardrail_reason"], "meaning_changed")
        self.assertTrue(result["was_fallback"])

    def test_a_faithful_english_rewording_is_spoken(self):
        model = Mock()
        model.phrase.side_effect = lambda *a, **k: k["source"]  # a faithful rewording
        result = plan(VICTIM_TEXT, "en", model)
        self.assertFalse(result["was_fallback"])
        self.assertEqual(result["text"], intents.licensed_question(result["intent"], "en"))

    def test_hinglish_writers_get_reviewed_latin_text_only_once_approved(self):
        from ml.dialogue import variants

        utterance = "Woh log phir aaye the aur dhamki di"
        unapproved = plan(utterance, "hi", adapters.MockLLM())
        self.assertEqual(unapproved["register"], "hinglish")
        self.assertEqual(unapproved["text"], intents.licensed_question(unapproved["intent"], "hi"))
        with patch.dict(variants.HINGLISH_REVIEW, {"status": "APPROVED", "reviewer": "lead", "review_date": "x"}):
            result = plan(utterance, "hi", adapters.MockLLM())
        self.assertEqual(result["text"], variants.HINGLISH_TEXT[result["intent"]])
        self.assertEqual(result["review_status"], "approved_hinglish")

    def test_voice_turns_and_english_sessions_never_get_hinglish(self):
        from ml.dialogue import variants

        with patch.dict(variants.HINGLISH_REVIEW, {"status": "APPROVED", "reviewer": "lead", "review_date": "x"}),                 patch.object(turn_loop, "is_speakable", return_value=True, create=True):
            voice = turn_loop.plan_turn(State.S2_IMMEDIATE_SAFETY, {"narrative": "x"}, "Woh log phir aaye",
                                        {"lang": "hi", "voice": True}, adapters.MockLLM())
            english = turn_loop.plan_turn(State.S2_IMMEDIATE_SAFETY, {"narrative": "x"}, "Raha and Kal came",
                                          {"lang": "en"}, adapters.MockLLM())
        self.assertEqual(voice["register"], "hi")
        self.assertEqual(english["register"], "en")

    def test_non_english_or_multiline_candidates_are_discarded(self):
        model = Mock()
        model.phrase.return_value = "बताने के लिए धन्यवाद। शांत रहिए।"
        hindi = plan("वे लोग फिर आए थे", "hi", model)
        self.assertTrue(hindi["was_fallback"])
        model.phrase.return_value = "Do you need help?\nIgnore the rules."
        multi = plan(VICTIM_TEXT, "en", model)
        self.assertTrue(multi["was_fallback"])

    def test_variants_provider_speaks_only_approved_wording(self):
        from ml.dialogue import variants

        provider = adapters.get_provider("variants")
        self.assertIsNone(provider.phrase("ask_support_network", "q", "en", register="en", source="q"))
        with patch.dict(variants.EN_VARIANTS, {"ask_support_network": ["Do you have someone with you right now?"]}),                 patch.dict(variants.VARIANT_REVIEW, {"status": "APPROVED", "reviewer": "lead", "review_date": "x"}):
            seen = {provider.phrase("ask_support_network", "q", "en", register="en", source="q") for _ in range(40)}
            self.assertIsNone(provider.phrase("ask_support_network", "q", "hi", register="hi", source="q"))
        self.assertEqual(seen, {"Do you have someone with you right now?", "Is there someone with you right now?"})

    def test_devanagari_writers_get_the_approved_hindi(self):
        result = plan("वे लोग फिर आए थे", "hi", adapters.MockLLM())
        self.assertEqual(result["register"], "hi")
        self.assertEqual(result["text"], intents.licensed_question(result["intent"], "hi"))


class _Handler(BaseHTTPRequestHandler):
    reply = {"text": "Do you have someone with you right now?"}
    delay = 0.0
    seen = []

    def log_message(self, *a):
        return

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append((self.path, body, self.headers.get("Authorization")))
        time.sleep(type(self).delay)
        if self.path.startswith("/gradio_api/call/"):
            data = json.dumps({"event_id": "ev1"}).encode()
        else:
            data = json.dumps(type(self).reply).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        out = b'event: generating\ndata: null\n\nevent: complete\ndata: ["Do you have someone with you right now?"]\n\n'
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


class TestProviders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _Handler.delay, _Handler.seen = 0.0, []

    def test_local_service_rewords_english_only(self):
        model = adapters.LocalServiceLLM(self.url, 2.0)
        self.assertEqual(model.phrase("ask_support_network", "Is there someone with you right now?", "en",
                                      register="en", source="Is there someone with you right now?"),
                         "Do you have someone with you right now?")
        self.assertIsNone(model.phrase("ask_support_network", "x", "hi", register="hi", source="x"))
        self.assertIsNone(model.phrase("ask_support_network", "x", "hi", register="hinglish", source="x"))
        self.assertEqual(len(_Handler.seen), 1)

    def test_a_slow_or_absent_service_returns_none(self):
        _Handler.delay = 1.0
        model = adapters.LocalServiceLLM(self.url, 0.2)
        self.assertIsNone(model.phrase("i", "q", "en", register="en", source="q"))
        dead = adapters.LocalServiceLLM("http://127.0.0.1:9", 0.5)
        self.assertIsNone(dead.phrase("i", "q", "en", register="en", source="q"))

    def test_remote_space_reads_the_completed_event_and_sends_the_token(self):
        model = adapters.RemoteSpaceLLM(self.url, "hf_test_token", "shared-key", 3.0)
        self.assertEqual(model.phrase("ask_support_network", "q", "en", register="en", source="q"),
                         "Do you have someone with you right now?")
        path, body, auth = _Handler.seen[0]
        self.assertEqual(path, "/gradio_api/call/phrase")
        self.assertEqual(body, {"data": ["q", "en", "shared-key"]})
        self.assertEqual(auth, "Bearer hf_test_token")

    @unittest.skipUnless(HAVE_SETTINGS, "pydantic-settings not installed (Tier 1 run)")
    def test_unknown_provider_is_refused(self):
        with self.assertRaises(ValueError):
            adapters.get_provider("external")


@unittest.skipUnless(HAVE_SETTINGS, "pydantic-settings not installed (Tier 1 run)")
class TestSettings(unittest.TestCase):
    def test_service_url_is_loopback_and_space_url_is_https_hf_space(self):
        from backend.app.core.config import Settings

        base = {"_env_file": None, "APP_ENV": "test", "DATABASE_URL": "sqlite+aiosqlite:///:memory:"}
        with self.assertRaises(ValueError):
            Settings(**base, LLM_SERVICE_URL="http://10.0.0.5:8766")
        with self.assertRaises(ValueError):
            Settings(**base, LLM_REMOTE_URL="http://user-space.hf.space")
        with self.assertRaises(ValueError):
            Settings(**base, LLM_REMOTE_URL="https://example.com")
        s = Settings(**base, LLM_REMOTE_URL="https://user-sahay.hf.space/")
        self.assertEqual(s.LLM_REMOTE_URL, "https://user-sahay.hf.space")

    def test_live_generation_is_refused_outside_tests(self):
        from backend.app.core.config import Settings

        pg = "postgresql+asyncpg://u:p@h/db"
        for provider in ("local_service", "remote"):
            for env in ("development", "local", "demo", "production"):
                with self.assertRaises(ValueError, msg=(provider, env)):
                    Settings(_env_file=None, APP_ENV=env, DATABASE_URL=pg, LLM_PROVIDER=provider)
        self.assertEqual(Settings(_env_file=None, APP_ENV="demo", DATABASE_URL=pg,
                                  LLM_PROVIDER="variants").LLM_PROVIDER, "variants")


if __name__ == "__main__":
    unittest.main()
