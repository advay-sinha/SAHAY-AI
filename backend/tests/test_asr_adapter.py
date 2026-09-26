"""Speech-recognition adapter (EXT-120, PC-11).

Uses a stub HTTP server on 127.0.0.1 in a background thread: no model and no real audio.
The endpoint itself stays unwired (501) until PC-11 is confirmed by the leads.
"""

import asyncio
import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from backend.app.adapters import asr

HAVE_SETTINGS = importlib.util.find_spec("pydantic_settings") is not None


class _Stub(BaseHTTPRequestHandler):
    reply = (200, {"status": "transcribed", "text": "mujhe madad chahiye", "lang": "hi", "asr_confidence": 0.8,
                   "quality": {"snr_db": 30.0}, "poor_audio": False, "secret_extra": "dropped"})
    seen = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _Stub.seen = {"path": self.path, "type": self.headers.get("Content-Type"), "bytes": len(self.rfile.read(length))}
        status, payload = _Stub.reply
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        return


class TestLocalService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Stub)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_transcript_is_forwarded_and_unknown_fields_dropped(self):
        _Stub.reply = (200, {"status": "transcribed", "text": "mujhe madad chahiye", "lang": "hi",
                             "asr_confidence": 0.8, "poor_audio": False, "secret_extra": "x"})
        out = self.run_async(asr.LocalServiceASR(self.url).transcribe(b"RIFFdata", "audio/wav", "hi"))
        self.assertEqual((out["status"], out["text"], out["asr_confidence"]), ("transcribed", "mujhe madad chahiye", 0.8))
        self.assertNotIn("secret_extra", out)
        self.assertEqual(_Stub.seen, {"path": "/transcribe?lang=hi", "type": "audio/wav", "bytes": 8})

    def test_no_speech_never_carries_text(self):
        _Stub.reply = (200, {"status": "no_speech", "text": "ghost words"})
        out = self.run_async(asr.LocalServiceASR(self.url).transcribe(b"x", "audio/wav", "en"))
        self.assertEqual((out["status"], out["text"]), ("no_speech", ""))

    def test_refusals_and_failures(self):
        _Stub.reply = (413, {"error": "too_long"})
        with self.assertRaises(asr.ASRRejected) as ctx:
            self.run_async(asr.LocalServiceASR(self.url).transcribe(b"x", "audio/wav", "en"))
        self.assertEqual((ctx.exception.status, ctx.exception.code), (413, "too_long"))
        _Stub.reply = (500, {"error": "inference_failed"})
        with self.assertRaises(asr.ASRUnavailable):
            self.run_async(asr.LocalServiceASR(self.url).transcribe(b"x", "audio/wav", "en"))
        _Stub.reply = (200, {"status": "something_new"})
        with self.assertRaises(asr.ASRUnavailable):
            self.run_async(asr.LocalServiceASR(self.url).transcribe(b"x", "audio/wav", "en"))

    def test_unreachable_service_is_unavailable(self):
        with self.assertRaises(asr.ASRUnavailable):
            self.run_async(asr.LocalServiceASR("http://127.0.0.1:9", timeout_s=2).transcribe(b"x", "audio/wav", "en"))


class TestMock(unittest.TestCase):
    def test_default_mock_needs_nothing_running(self):
        out = asyncio.run(asr.MockASR().transcribe(b"x", "audio/wav", "hi"))
        self.assertEqual((out["status"], out["text"]), ("no_speech", ""))

    def test_queued_responses(self):
        mock = asr.MockASR([{"status": "transcribed", "text": "help"}, asr.ASRUnavailable("down")])
        self.assertEqual(asyncio.run(mock.transcribe(b"x", "audio/wav", "en"))["text"], "help")
        with self.assertRaises(asr.ASRUnavailable):
            asyncio.run(mock.transcribe(b"x", "audio/wav", "en"))


@unittest.skipUnless(HAVE_SETTINGS, "pydantic-settings is not installed")
class TestSettings(unittest.TestCase):
    def _settings(self, **kw):
        from backend.app.core.config import Settings
        return Settings(DATABASE_URL="sqlite+aiosqlite:///:memory:", **kw)

    def test_defaults_are_mock_and_loopback(self):
        s = self._settings()
        self.assertEqual((s.ASR_PROVIDER, s.ASR_SERVICE_URL), ("mock", "http://127.0.0.1:8765"))
        self.assertIsInstance(asr.get_provider(s), asr.MockASR)
        self.assertIsInstance(asr.get_provider(self._settings(ASR_PROVIDER="local_service")), asr.LocalServiceASR)

    def test_non_loopback_service_urls_are_refused(self):
        for bad in ("http://192.168.1.10:8765", "http://0.0.0.0:8765", "https://127.0.0.1:8765",
                    "http://localhost:8765", "http://127.0.0.1:8765/other"):
            with self.assertRaises(Exception, msg=bad):
                self._settings(ASR_SERVICE_URL=bad)


if __name__ == "__main__":
    unittest.main()
