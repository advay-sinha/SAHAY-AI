"""Voice output (M13, EXT-103): fixed-script registry rules and the synthesiser wrapper.

No voice is started here except in the Windows-only test, which is skipped elsewhere.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ml.tts import presynth as ps
from ml.tts import synthesize as sy

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt fictional-recording"
TEXT = "Fictional approved script text."


class RegistryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "fixed"
        self.src = Path(self.tmp.name) / "rec.wav"
        self.src.write_bytes(WAV)

    def tearDown(self):
        self.tmp.cleanup()


class TestRegistry(RegistryBase):
    def test_nothing_is_servable_today(self):
        # Every fixed script is still unapproved, so nothing may play.
        self.assertEqual(set(ps.missing(self.root)), set(ps.KEYS))
        self.assertIsNone(ps.servable("SX", "hi", self.root))

    def test_only_approved_text_can_be_recorded(self):
        with self.assertRaises(ps.AudioRegistryError):
            ps.register("SX:hi", self.src, "recorder", self.root)

    def test_full_lifecycle_under_an_approved_script(self):
        with mock.patch.object(ps, "approved_text", return_value=TEXT):
            entry = ps.register("SX:hi", self.src, "Recorder A", self.root)
            self.assertEqual(entry["status"], "recorded")
            self.assertIsNone(ps.servable("SX", "hi", self.root))         # recorded, not approved
            with self.assertRaises(ps.AudioRegistryError):
                ps.approve("SX:hi", "recorder a", self.root)             # recorder cannot approve
            ps.approve("SX:hi", "Reviewer B", self.root)
            path = ps.servable("SX", "hi", self.root)
            self.assertEqual(path.read_bytes(), WAV)
        with mock.patch.object(ps, "approved_text", return_value=TEXT + " Revised."):
            self.assertIsNone(ps.servable("SX", "hi", self.root))         # text changed since recording
            self.assertIn("recording is of a different text version", ps.check("SX:hi", self.root)["reasons"])

    def test_a_changed_file_is_refused(self):
        with mock.patch.object(ps, "approved_text", return_value=TEXT):
            ps.register("S0:en", self.src, "Recorder A", self.root)
            ps.approve("S0:en", "Reviewer B", self.root)
            (self.root / "S0-en.wav").write_bytes(WAV + b"tampered")
            self.assertIsNone(ps.servable("S0", "en", self.root))

    def test_non_wav_and_unknown_keys_are_refused(self):
        bad = Path(self.tmp.name) / "x.mp3"
        bad.write_bytes(b"ID3fictional")
        with mock.patch.object(ps, "approved_text", return_value=TEXT):
            with self.assertRaises(ps.AudioRegistryError):
                ps.register("S0:en", bad, "Recorder A", self.root)
        self.assertIsNone(ps.servable("S3", "en", self.root))
        with self.assertRaises(ps.AudioRegistryError):
            ps.approved_text("S3:en")


class TestSynthesizer(unittest.TestCase):
    def test_voice_choice_never_crosses_languages(self):
        installed = ("Microsoft Heera", "Microsoft Zira Desktop")
        self.assertEqual(sy.pick_voice("en", installed), "Microsoft Heera")
        self.assertIsNone(sy.pick_voice("hi", installed))
        self.assertIsNone(sy.pick_voice("fr", installed))

    def test_null_synthesizer_gives_no_audio(self):
        self.assertEqual(sy.NullSynthesizer().synthesize("hello", "en"), b"")

    @unittest.skipUnless(sys.platform == "win32" and (shutil.which("pwsh") or shutil.which("powershell"))
                         and os.environ.get("SAHAY_TTS_LIVE") == "1", "set SAHAY_TTS_LIVE=1 on Windows")
    def test_windows_voice_live(self):
        synth = sy.WindowsVoiceSynthesizer()
        try:
            audio, ms = sy.timed(synth, "Can you tell me when this happened?", "en")
            self.assertTrue(audio.startswith(b"RIFF"))
            self.assertEqual(synth.synthesize("Kya aap surakshit hain?", "hi"), b"")
        finally:
            synth.close()


if __name__ == "__main__":
    unittest.main()
