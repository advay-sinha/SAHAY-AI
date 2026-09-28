"""Local speech-to-text service: 127.0.0.1 only (plan M11, EXT-120, PC-11).

    python -m ml.voice.service [--port 8765] [--device auto|cuda|cpu]

Run in the private ``sahay-ml-models`` environment. The backend's ASR adapter
(``ASR_PROVIDER=local_service``) calls it.

    GET  /health                     {"status": "ready"|"loading", ...}
    POST /transcribe?lang=hi|en      body = audio bytes, Content-Type audio/wav | audio/mp4 | audio/aac

Pipeline: decode (PyAV via faster-whisper's decoder; WAV or M4A/AAC) -> 16 kHz mono ->
``GatedTranscriber`` (Silero VAD, then Whisper on the speech intervals only). If no speech is
found, Whisper never runs. The response carries the transcript for the backend, plus
console-only measurements: an uncalibrated ASR confidence, audio quality and prosody. The
backend never forwards those to a victim client.

Guarantees:
* binds to a loopback address only; anything else is refused before the socket opens;
* model loading happens with network connections blocked; there is no download path;
* audio and transcript text are never logged or written to disk; the log line is counts only;
* one request at a time (a single GPU worker); requests over 5 MB or 60 s are refused.
"""

import argparse
import importlib
import io
import json
import math
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse

SERVICE_VERSION = "voice-service-1.0"
DEFAULT_PORT = 8765
LOOPBACK_HOSTS = ("127.0.0.1", "::1")
SAMPLE_RATE = 16000
MAX_BYTES = 5 * 1024 * 1024
MAX_SECONDS = 60.0
LANGUAGES = ("hi", "en")
ACCEPTED_TYPES = {
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/vnd.wave": "wav",
    "audio/mp4": "m4a", "audio/m4a": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac",
}
#: Below this uncalibrated mean token probability the backend treats the audio as poor
#: (needs_human, invariant 6). A conservative floor, not a tuned threshold.
ASR_CONFIDENCE_FLOOR = 0.5
CONFIDENCE_NOTE = "uncalibrated: duration-weighted mean of exp(avg_logprob) over Whisper segments"


class ServiceError(Exception):
    """A refusal with an HTTP status and a fixed message: no audio, no text, no path."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# --- pure helpers ---------------------------------------------------------------------------------


def check_bind_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        raise ServiceError(400, "not_loopback", "the voice service binds to 127.0.0.1 or ::1 only")
    return host


def media_kind(content_type: Optional[str]) -> str:
    kind = ACCEPTED_TYPES.get(str(content_type or "").split(";")[0].strip().lower())
    if kind is None:
        raise ServiceError(415, "unsupported_media_type", "send audio/wav, audio/mp4 or audio/aac")
    return kind


def check_language(lang: Optional[str]) -> str:
    if lang not in LANGUAGES:
        raise ServiceError(400, "unsupported_language", "lang must be hi or en")
    return str(lang)


def asr_confidence(segments: Sequence[Any]) -> Optional[float]:
    """Duration-weighted mean of exp(avg_logprob); None when no segment carries one."""
    num = den = 0.0
    for seg in segments:
        lp = getattr(seg, "avg_logprob", None)
        if lp is None:
            continue
        weight = max(float(seg.end) - float(seg.start), 1e-3)
        num += math.exp(min(0.0, float(lp))) * weight
        den += weight
    return round(num / den, 4) if den else None


# --- engine --------------------------------------------------------------------------------------


class VoiceEngine:
    """Decoder + GatedTranscriber + measurements. ``transcriber`` is injectable for tests."""

    def __init__(self, transcriber: Any = None, decoder: Any = None, *, models_root: Optional[str] = None,
                 device: str = "auto") -> None:
        self._transcriber = transcriber
        self._decoder = decoder
        self._models_root = models_root
        self._device = device
        self.lock = threading.Lock()
        self.ready = transcriber is not None

    def load(self) -> None:
        from ..runtime.asr import WhisperASR
        from ..runtime.pipeline import GatedTranscriber
        from ..runtime.vad import SileroVAD
        self._transcriber = GatedTranscriber(SileroVAD(), WhisperASR(models_root=self._models_root, device=self._device))
        self._transcriber.vad.load()
        self._transcriber.asr.load()  # load eagerly so the first request is not slow
        self.ready = True

    def decode(self, body: bytes) -> Any:
        if self._decoder is not None:
            return self._decoder(body)
        samples = fast_wav(body)
        if samples is not None:
            return samples
        decode_audio = importlib.import_module("faster_whisper").decode_audio
        return decode_audio(io.BytesIO(body), sampling_rate=SAMPLE_RATE)


def fast_wav(body: bytes) -> Any:
    """16 kHz mono 16-bit PCM WAV read directly, skipping PyAV (about 80 ms per turn measured).

    Returns float32 samples scaled like faster-whisper's decode_audio (int16 / 32768), or None for
    any other format, which then takes the general decoder.
    """
    if body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        return None
    try:
        with wave.open(io.BytesIO(body), "rb") as w:
            if (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
                return None
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return None
    np = importlib.import_module("numpy")
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0

    def transcribe(self, samples: Any, lang: str) -> Any:
        return self._transcriber.transcribe(samples, lang)


def transcribe_request(engine: VoiceEngine, body: bytes, content_type: Optional[str],
                       lang: Optional[str]) -> Tuple[int, Dict[str, Any]]:
    """Validate, decode, transcribe and measure one utterance. Returns (HTTP status, JSON body)."""
    from ..acoustics import prosody, quality, signal
    started = time.perf_counter()
    media_kind(content_type)
    lang = check_language(lang)
    if not body:
        raise ServiceError(400, "empty_body", "the request carried no audio")
    if len(body) > MAX_BYTES:
        raise ServiceError(413, "too_large", "audio is larger than 5 MB")
    try:
        samples = engine.decode(body)
    except Exception:
        return 200, {"status": "audio_unreadable", "version": SERVICE_VERSION}
    duration = len(samples) / SAMPLE_RATE
    if duration > MAX_SECONDS:
        raise ServiceError(413, "too_long", "audio is longer than 60 seconds")
    if duration == 0:
        return 200, {"status": "audio_unreadable", "version": SERVICE_VERSION}
    t_decoded = time.perf_counter()
    result = engine.transcribe(samples, lang)
    t_asr = time.perf_counter()
    intervals: List[Tuple[float, float]] = list(result.runtime.get("vad_intervals") or [])
    text = (result.text or "").strip()
    body_out: Dict[str, Any] = {
        "version": SERVICE_VERSION, "lang": lang, "duration_s": round(duration, 3),
        "speech_s": round(float(result.runtime.get("vad_speech_s") or 0.0), 3),
        "status": "transcribed" if text and result.status == "transcribed" else "no_speech",
        "text": text if result.status == "transcribed" else "",
    }
    measured = signal.measure(samples, intervals)
    q = measured["quality"]
    conf = asr_confidence(result.segments) if body_out["status"] == "transcribed" else None
    summary = prosody.summarize_turn(measured["f0_hz"], measured["rms_db"], intervals, measured["duration_s"],
                                     word_count=len(text.split()) if text else None)
    body_out.update({
        "asr_confidence": conf, "asr_confidence_note": CONFIDENCE_NOTE,
        "low_asr_confidence": conf is not None and conf < ASR_CONFIDENCE_FLOOR,
        "quality": q, "poor_audio": quality.is_poor(q),
        "prosody": summary["features"], "prosody_reasons": summary["reasons"],
        "segments": len(result.segments),
        "timings_ms": {"decode": round(1000 * (t_decoded - started)), "asr": round(1000 * (t_asr - t_decoded)),
                       "total": round(1000 * (time.perf_counter() - started))},
    })
    return 200, body_out


# --- HTTP -----------------------------------------------------------------------------------------


def make_handler(engine: VoiceEngine) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "sahay-voice/1.0"
        sys_version = ""

        def _send(self, status: int, payload: Mapping[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args: Any) -> None:  # counts only: no path query, no body
            return

        def do_GET(self) -> None:
            if urlparse(self.path).path != "/health":
                return self._send(404, {"error": "not_found"})
            self._send(200, {"status": "ready" if engine.ready else "loading", "version": SERVICE_VERSION,
                             "languages": list(LANGUAGES), "max_seconds": MAX_SECONDS})

        def do_POST(self) -> None:
            url = urlparse(self.path)
            if url.path != "/transcribe":
                return self._send(404, {"error": "not_found"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BYTES:
                return self._send(413, {"error": "too_large", "message": "audio is larger than 5 MB"})
            body = self.rfile.read(length) if length else b""
            lang = (parse_qs(url.query).get("lang") or [None])[0]
            try:
                with engine.lock:
                    status, payload = transcribe_request(engine, body, self.headers.get("Content-Type"), lang)
            except ServiceError as exc:
                status, payload = exc.status, {"error": exc.code, "message": exc.message}
            except Exception as exc:  # the type only: never the audio, the text or a path
                status, payload = 500, {"error": "inference_failed", "type": type(exc).__name__}
            self._send(status, payload)
            print(json.dumps({"request": "transcribe", "http": status, "status": payload.get("status"),
                              "duration_s": payload.get("duration_s"),
                              "total_ms": (payload.get("timings_ms") or {}).get("total")}), flush=True)

    return Handler


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.voice.service", description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--models-root", default=None)
    args = parser.parse_args(argv)
    host = check_bind_host(args.host)
    from ..runtime.offline import apply_offline_env, network_blocked
    engine = VoiceEngine(models_root=args.models_root, device=args.device)
    with network_blocked() as net:
        engine.load()
    apply_offline_env()
    if net["attempts"]:
        print(json.dumps({"status": "refused", "reason": "a network attempt was made while loading models"}))
        return 1
    server = HTTPServer((host, args.port), make_handler(engine))
    print(json.dumps({"status": "ready", "listening": f"http://{host}:{args.port}", "version": SERVICE_VERSION,
                      "network_attempts_blocked_while_loading": 0}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
