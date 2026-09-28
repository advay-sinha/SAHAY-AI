"""Speech synthesis interface.

EXT-103 (approved 2026-09-24): fixed scripts use human-recorded audio (``presynth``); validated
generated turns may use a built-in offline OS voice. No TTS model is downloaded, so the demo path
needs no online TTS.

Nothing may be synthesised unless guardrails.validate returned ok, or the text is approved
fallback text that was allowed to be shown. The backend adapter enforces that; this module only
turns text into audio.
"""

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Protocol, Sequence, Tuple

FIRST_CHUNK_TARGET_MS = 500

#: Voices tried in order per language. No Hindi voice ships with the demo laptop's Windows, so
#: Hindi returns no audio and the client shows the text (checked 2026-09-29; H5 covers Hindi).
VOICES: Dict[str, Tuple[str, ...]] = {
    "en": ("Microsoft Heera", "Microsoft Ravi", "Microsoft Zira Desktop", "Microsoft David Desktop"),
    "hi": ("Microsoft Kalpana", "Microsoft Hemant"),
}
MAX_CHARS = 600

# A small, persistent PowerShell loop around System.Speech. One JSON request per line on stdin:
# {"voice": ..., "out": ..., "text": ...}; one line back: "ok" or "err <reason>". Local only.
_WORKER = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$names = @($s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name })
[Console]::Out.WriteLine('voices ' + ($names -join '|'))
[Console]::Out.Flush()
while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    try {
        $req = $line | ConvertFrom-Json
        $s.SelectVoice($req.voice)
        $s.SetOutputToWaveFile($req.out, $fmt)
        $s.Speak($req.text)
        $s.SetOutputToNull()
        [Console]::Out.WriteLine('ok')
    } catch {
        try { $s.SetOutputToNull() } catch {}
        [Console]::Out.WriteLine('err ' + $_.Exception.GetType().Name)
    }
    [Console]::Out.Flush()
}
"""


class Synthesizer(Protocol):
    def synthesize(self, text: str, lang: str) -> bytes:
        ...


class NullSynthesizer:
    """Produces no audio. The client falls back to displaying the text."""

    name = "none"

    def synthesize(self, text: str, lang: str) -> bytes:
        return b""


class SynthesisUnavailable(RuntimeError):
    """The OS voice could not be started or failed. The client shows the text."""


def pick_voice(lang: str, installed: Sequence[str]) -> Optional[str]:
    return next((v for v in VOICES.get(lang, ()) if v in installed), None)


class WindowsVoiceSynthesizer:
    """Built-in Windows voices through one warm PowerShell process (EXT-103). Returns WAV bytes.

    Languages without an installed voice return ``b""`` (text fallback), never another language's
    voice. Thread-safe: one request at a time through the worker.
    """

    name = "windows_voice"

    def __init__(self, shell: Optional[str] = None, timeout_s: float = 10.0) -> None:
        self.shell = shell or ("pwsh" if _on_path("pwsh") else "powershell")
        self.timeout_s = timeout_s
        self._proc: Optional[subprocess.Popen] = None
        self._installed: Tuple[str, ...] = ()
        self._lock = threading.Lock()

    def _start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen([self.shell, "-NoProfile", "-NonInteractive", "-Command", _WORKER],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        except OSError as exc:
            raise SynthesisUnavailable("the OS voice process could not start") from exc
        first = self._readline()
        if not first.startswith("voices "):
            self.close()
            raise SynthesisUnavailable("the OS voice process did not report its voices")
        self._installed = tuple(v for v in first[len("voices "):].split("|") if v)

    def _readline(self) -> str:
        assert self._proc is not None and self._proc.stdout is not None
        box: Dict[str, str] = {}
        reader = threading.Thread(target=lambda: box.setdefault("line", self._proc.stdout.readline()), daemon=True)
        reader.start()
        reader.join(self.timeout_s)
        if "line" not in box:
            self.close()
            raise SynthesisUnavailable("the OS voice process timed out")
        return box["line"].strip()

    @property
    def installed(self) -> Tuple[str, ...]:
        with self._lock:
            self._start()
            return self._installed

    def synthesize(self, text: str, lang: str) -> bytes:
        text = " ".join(str(text or "").split())[:MAX_CHARS]
        if not text:
            return b""
        with self._lock:
            self._start()
            voice = pick_voice(lang, self._installed)
            if voice is None:
                return b""
            fd, out = tempfile.mkstemp(suffix=".wav", prefix="sahay-tts-")
            os.close(fd)
            try:
                assert self._proc is not None and self._proc.stdin is not None
                self._proc.stdin.write(json.dumps({"voice": voice, "out": out, "text": text}) + "\n")
                self._proc.stdin.flush()
                reply = self._readline()
                if reply != "ok":
                    raise SynthesisUnavailable(f"the OS voice failed ({reply[:40]})")
                return Path(out).read_bytes()
            finally:
                try:
                    os.unlink(out)
                except OSError:
                    pass

    def close(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass
            self._proc = None


def timed(synth: Synthesizer, text: str, lang: str) -> Tuple[bytes, float]:
    """Synthesise and return (audio, milliseconds). The whole file is the first chunk here."""
    started = time.perf_counter()
    audio = synth.synthesize(text, lang)
    return audio, round(1000 * (time.perf_counter() - started), 1)


def _on_path(exe: str) -> bool:
    """True when ``exe`` is on PATH (Windows extensions included)."""
    exts = [""] + [e.lower() for e in os.environ.get("PATHEXT", ".EXE").split(os.pathsep) if e]
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if folder and any(Path(folder, exe + ext).is_file() for ext in exts):
            return True
    return False
