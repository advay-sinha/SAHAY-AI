"""Local speech-to-text service (plan M11, EXT-120, PC-11).

The pure checks run everywhere. The request tests need numpy (prosody and quality measurement)
and use a fake transcriber and decoder: no model, no network, no real audio.
"""

import importlib.util
import math
import unittest
from types import SimpleNamespace

from ml.voice import service as vs

HAS_NUMPY = importlib.util.find_spec("numpy") is not None


class TestPureChecks(unittest.TestCase):
    def test_loopback_only(self):
        for ok in ("127.0.0.1", "::1"):
            self.assertEqual(vs.check_bind_host(ok), ok)
        for bad in ("0.0.0.0", "192.168.1.5", "localhost", "", "::"):
            with self.assertRaises(vs.ServiceError):
                vs.check_bind_host(bad)

    def test_media_types(self):
        self.assertEqual(vs.media_kind("audio/wav"), "wav")
        self.assertEqual(vs.media_kind("audio/mp4; codecs=mp4a.40.2"), "m4a")
        self.assertEqual(vs.media_kind("AUDIO/AAC"), "aac")
        for bad in (None, "", "text/plain", "audio/mpeg", "video/mp4"):
            with self.assertRaises(vs.ServiceError) as ctx:
                vs.media_kind(bad)
            self.assertEqual(ctx.exception.status, 415)

    def test_languages(self):
        self.assertEqual(vs.check_language("hi"), "hi")
        for bad in (None, "fr", "hinglish", "HI"):
            with self.assertRaises(vs.ServiceError):
                vs.check_language(bad)

    def test_confidence_is_duration_weighted_and_bounded(self):
        seg = lambda s, e, lp: SimpleNamespace(start=s, end=e, avg_logprob=lp)
        self.assertIsNone(vs.asr_confidence([]))
        self.assertIsNone(vs.asr_confidence([seg(0, 1, None)]))
        self.assertAlmostEqual(vs.asr_confidence([seg(0, 1, 0.0)]), 1.0)
        c = vs.asr_confidence([seg(0, 3, math.log(0.9)), seg(3, 4, math.log(0.3))])
        self.assertAlmostEqual(c, (0.9 * 3 + 0.3 * 1) / 4, places=4)
        self.assertLessEqual(vs.asr_confidence([seg(0, 1, 0.5)]), 1.0)  # positive logprob clamped

    def test_service_has_no_heavy_imports_at_module_scope(self):
        import ast
        from pathlib import Path
        src = (Path(vs.__file__)).read_text(encoding="utf-8")
        for node in ast.parse(src).body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for name in names:
                    self.assertNotIn(name.split(".")[0], {"torch", "numpy", "faster_whisper", "av", "transformers"})


class _FakeTranscriber:
    def __init__(self, text, status="transcribed", intervals=((0.2, 1.8),), logprob=-0.2):
        self.text, self.status, self.intervals, self.logprob = text, status, list(intervals), logprob
        self.calls = 0

    def transcribe(self, samples, language):
        self.calls += 1
        speech = sum(e - s for s, e in self.intervals)
        segs = [SimpleNamespace(start=s, end=e, avg_logprob=self.logprob) for s, e in self.intervals] \
            if self.status == "transcribed" else []
        return SimpleNamespace(text=self.text, status=self.status, segments=segs,
                               runtime={"vad_intervals": self.intervals, "vad_speech_s": speech})


@unittest.skipUnless(HAS_NUMPY, "numpy is available only in the private model environment")
class TestTranscribeRequest(unittest.TestCase):
    def setUp(self):
        import numpy as np
        t = np.arange(2 * vs.SAMPLE_RATE) / vs.SAMPLE_RATE
        self.tone = (0.3 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
        self.np = np

    def _engine(self, transcriber, samples=None, fail=False):
        def decoder(body):
            if fail:
                raise ValueError("not audio")
            return self.tone if samples is None else samples
        return vs.VoiceEngine(transcriber=transcriber, decoder=decoder)

    def test_transcribed_response_carries_measurements_not_decisions(self):
        status, body = vs.transcribe_request(self._engine(_FakeTranscriber("I need help")), b"x", "audio/wav", "en")
        self.assertEqual((status, body["status"], body["text"]), (200, "transcribed", "I need help"))
        self.assertAlmostEqual(body["asr_confidence"], round(math.exp(-0.2), 4))
        for key in ("quality", "poor_audio", "prosody", "timings_ms", "speech_s", "duration_s"):
            self.assertIn(key, body)
        for forbidden in ("svi", "band", "emotion", "affect", "crisis", "d4", "alert"):
            self.assertNotIn(forbidden, body)

    def test_no_speech_and_low_confidence(self):
        _, body = vs.transcribe_request(self._engine(_FakeTranscriber("", status="no_speech", intervals=())),
                                        b"x", "audio/wav", "hi")
        self.assertEqual((body["status"], body["text"], body["asr_confidence"]), ("no_speech", "", None))
        _, low = vs.transcribe_request(self._engine(_FakeTranscriber("kuch", logprob=math.log(0.3))),
                                       b"x", "audio/wav", "hi")
        self.assertTrue(low["low_asr_confidence"])

    def test_unreadable_too_large_too_long(self):
        self.assertEqual(vs.transcribe_request(self._engine(_FakeTranscriber("x"), fail=True), b"x", "audio/wav", "en"),
                         (200, {"status": "audio_unreadable", "version": vs.SERVICE_VERSION}))
        with self.assertRaises(vs.ServiceError) as ctx:
            vs.transcribe_request(self._engine(_FakeTranscriber("x")), b"x" * (vs.MAX_BYTES + 1), "audio/wav", "en")
        self.assertEqual(ctx.exception.status, 413)
        long = self.np.zeros(int(61 * vs.SAMPLE_RATE), dtype=self.np.float32)
        fake = _FakeTranscriber("x")
        with self.assertRaises(vs.ServiceError):
            vs.transcribe_request(self._engine(fake, samples=long), b"x", "audio/wav", "en")
        self.assertEqual(fake.calls, 0)  # refused before any transcription

    def test_validation_happens_before_decoding(self):
        fake = _FakeTranscriber("x")
        with self.assertRaises(vs.ServiceError):
            vs.transcribe_request(self._engine(fake), b"x", "text/plain", "en")
        with self.assertRaises(vs.ServiceError):
            vs.transcribe_request(self._engine(fake), b"x", "audio/wav", "fr")
        self.assertEqual(fake.calls, 0)


if __name__ == "__main__":
    unittest.main()


class TestFastWav(unittest.TestCase):
    """The PyAV-free path for 16 kHz mono 16-bit WAV (M2: about 80 ms saved per turn)."""

    @staticmethod
    def wav(rate=16000, channels=1, width=2, frames=b"\x00\x10\x00\xf0" * 50):
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(frames)
        return buf.getvalue()

    def test_other_formats_take_the_general_decoder(self):
        from ml.voice.service import fast_wav
        self.assertIsNone(fast_wav(self.wav(rate=44100)))
        self.assertIsNone(fast_wav(self.wav(channels=2)))
        self.assertIsNone(fast_wav(self.wav(width=1, frames=b"\x80" * 100)))
        self.assertIsNone(fast_wav(b"ID3 not a wav at all"))
        self.assertIsNone(fast_wav(b"RIFF\x00\x00\x00\x00WAVEbroken"))

    def test_samples_are_scaled_like_faster_whisper(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy is only in the model environment")
        from ml.voice.service import fast_wav
        out = fast_wav(self.wav())
        self.assertEqual(len(out), 100)
        self.assertAlmostEqual(float(out[0]), 4096 / 32768)
        self.assertAlmostEqual(float(out[1]), -4096 / 32768)
