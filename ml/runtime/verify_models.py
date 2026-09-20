"""Explicit real-model verification. Never part of the default test suite.

    python -m ml.runtime.verify_models status
    python -m ml.runtime.verify_models integrity
    python -m ml.runtime.verify_models offline-reload
    python -m ml.runtime.verify_models smoke --model muril|xlmr|whisper|vad|pipeline|all
    python -m ml.runtime.verify_models smoke --model whisper --audio <private 16 kHz mono WAV> --language hi

Every command except ``status`` and ``integrity`` runs with the network actively blocked and
counts connection attempts. Output is aggregate only: no text, transcript, audio or absolute
path is printed. Set ``SAHAY_MODEL_REPORTS_ROOT`` (or ``--reports-dir``) to also write the
JSON privately. A private recording passed with ``--audio`` is read in memory, never copied,
and only processing status, language, duration and latency are reported.
"""

import argparse
import importlib
import importlib.util
import json
import math
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import audio as au, config, device as dev
from .asr import WhisperASR
from .fixtures import SENTENCES
from .offline import network_blocked
from .pipeline import GatedTranscriber
from .status import RuntimeFailure, assert_no_decision_keys
from .text_encoder import TextEncoder
from .vad import FUNCTIONAL_ONLY, SileroVAD

ENCODERS = ("muril", "xlmr")


def status(root_arg: Optional[str] = None) -> Dict[str, Any]:
    rows = [TextEncoder(m, models_root=root_arg).status().as_dict() for m in ENCODERS]
    rows.append(WhisperASR(models_root=root_arg).status().as_dict())
    rows.append(SileroVAD().status().as_dict())
    return {"models": rows}


def silero_inventory() -> Dict[str, Any]:
    if not dev.package_available("silero_vad"):
        return {"installed": False}
    meta = importlib.import_module("importlib.metadata")
    package_dir = Path(importlib.util.find_spec("silero_vad").origin).parent
    files = sorted(p for p in (package_dir / "data").glob("*") if p.is_file())
    return {"installed": True, "version": meta.version("silero-vad"),
            "bundled_models": [{"file": p.name, "bytes": p.stat().st_size, "sha256": config.sha256_file(p)}
                               for p in files if p.suffix in (".jit", ".onnx")]}


def integrity(root_arg: Optional[str] = None) -> Dict[str, Any]:
    root = config.models_root(root_arg)
    manifest = config.load_manifest()
    out: Dict[str, Any] = {"models": []}
    for entry in manifest["models"]:
        if entry["source"] == "huggingface":
            check = config.verify_files(config.model_dir(root, entry), entry["files"], full_hash=True)
            out["models"].append({"model": entry["logical_id"], "revision": entry["revision"], **check})
        if entry.get("derived"):
            ddir = config.derived_dir(root, entry)
            record_path = ddir / "conversion.json"
            row: Dict[str, Any] = {"model": entry["logical_id"] + ":" + entry["derived"]["name"]}
            if not record_path.is_file():
                row.update({"ok": False, "missing": ["conversion.json"]})
            else:
                record = json.loads(record_path.read_text(encoding="utf-8"))
                bad = [r["path"] for r in record["files"]
                       if config.sha256_file(config.confined(root, *r["path"].split("/")[1:])) != r["sha256"]]
                row.update({"ok": not bad and record["source_revision"] == entry["revision"],
                            "files": len(record["files"]), "bytes": record["bytes"], "hash_mismatch": bad,
                            "source_revision_matches": record["source_revision"] == entry["revision"]})
            out["models"].append(row)
        if entry["logical_id"] == "silero_vad":
            inv = silero_inventory()
            inv["ok"] = inv.get("installed") and inv.get("version") == entry["package_version"]
            out["models"].append({"model": "silero_vad", **inv})
    out["ok"] = all(m.get("ok") for m in out["models"])
    return out


# --- smoke checks --------------------------------------------------------------------------------


def smoke_encoder(name: str, root_arg: Optional[str] = None, device: str = "auto") -> Dict[str, Any]:
    enc = TextEncoder(name, models_root=root_arg, device=device)
    enc.load()
    try:
        texts = [SENTENCES[lang][0] for lang in ("en", "hi", "hinglish")]
        first = enc.encode(texts, max_length=128)
        second = enc.encode(texts, max_length=128)
        diff = max(abs(a - b) for u, v in zip(first.embeddings, second.embeddings) for a, b in zip(u, v))
        finite = all(math.isfinite(x) for row in first.embeddings for x in row)
        summary = first.summary()
        assert_no_decision_keys(summary)
        return {"model": enc.logical_id, "load_seconds": round(enc.load_seconds, 3), "dimension": first.dimension,
                "batch": len(texts), "token_counts": first.token_counts, "all_finite": finite,
                "max_abs_diff_between_runs": diff, "deterministic": diff == 0.0, "device": first.device,
                "precision": first.precision, "degraded": first.degraded, "note": first.note}
    finally:
        enc.unload()


def _asr_row(label: str, result: Any) -> Dict[str, Any]:
    s = result.summary()
    assert_no_decision_keys(s)
    return {"signal": label, "status": s["status"], "requested_language": s["requested_language"], "task": s["task"],
            "vad_gated": s["vad_gated"], "benchmark_only": s["benchmark_only"],
            "intervals_detected": s["intervals_detected"], "intervals_decoded": s["intervals_decoded"],
            "decoder_invoked": s["decoder_invoked"], "segments": len(s["segments"]), "characters": s["characters"],
            "duration_s": s["duration_s"], "latency_s": s["runtime"].get("latency_s"),
            "detected_language": s["detected_language"], "calibrated_confidence": s["calibrated_confidence"]}


def smoke_whisper(root_arg: Optional[str] = None, device: str = "auto") -> Dict[str, Any]:
    """Whisper is reached only through the gated pipeline, exactly as an application would."""
    gated = GatedTranscriber(SileroVAD(), WhisperASR(models_root=root_arg, device=device))
    try:
        rows = [_asr_row("empty", gated.transcribe(au.silence(0), "hi"))]
        for lang in ("hi", "en"):
            for label_, signal in (("silence_5s", au.silence(5)), ("tone_5s", au.tone(5)),
                                   ("silence_voiced_silence_6s", au.concat(au.silence(1.5), au.voiced_pattern(3),
                                                                            au.silence(1.5)))):
                rows.append(_asr_row(label_, gated.transcribe(signal, lang)))
        asr = gated.asr
        return {"model": "whisper_small", "path": "Silero VAD -> validated intervals -> Whisper (transcribe)",
                "loaded": asr.loaded, "load_seconds": None if asr.load_seconds is None else round(asr.load_seconds, 3),
                "device": asr.status().device, "compute_type": asr.compute_type, "runs": rows,
                "note": "synthetic signals contain no speech: this proves operation, not recognition"}
    finally:
        gated.unload()


def smoke_vad() -> Dict[str, Any]:
    vad = SileroVAD()
    vad.load()
    try:
        rows = []
        for label_, signal in (("empty", au.silence(0)), ("silence_5s", au.silence(5)), ("tone_5s", au.tone(5)),
                               ("voiced_pattern_5s", au.voiced_pattern(5))):
            r = vad.intervals(signal)
            rows.append({"signal": label_, "intervals": len(r.intervals), "speech_s": r.speech_s,
                         "duration_s": r.duration_s})
        try:
            vad.intervals(au.silence(1), sample_rate=8000)
            rate_check = "accepted (unexpected)"
        except RuntimeFailure as exc:
            rate_check = exc.code
        return {"model": "silero_vad", "runs": rows, "8khz_input": rate_check, "note": FUNCTIONAL_ONLY}
    finally:
        vad.unload()


def smoke_pipeline(root_arg: Optional[str] = None, device: str = "auto") -> Dict[str, Any]:
    gated = GatedTranscriber(SileroVAD(), WhisperASR(models_root=root_arg, device=device))
    try:
        rows = []
        for label_, signal in (("silence_6s", au.silence(6)),
                               ("silence_voiced_silence_6s", au.concat(au.silence(1.5), au.voiced_pattern(3),
                                                                        au.silence(1.5)))):
            started = time.perf_counter()
            loaded_before = gated.asr.loaded
            row = _asr_row(label_, gated.transcribe(signal, "hi"))
            row.update({"whisper_loaded_before": loaded_before, "whisper_loaded_after": gated.asr.loaded,
                        "pipeline_latency_s": round(time.perf_counter() - started, 4)})
            rows.append(row)
        return {"pipeline": "audio -> Silero VAD -> validated intervals -> Whisper Small (transcribe)", "runs": rows,
                "note": FUNCTIONAL_ONLY}
    finally:
        gated.unload()


def read_private_wav(path: str) -> Any:
    """16-bit PCM, mono, 16 kHz WAV only. Read into memory; never copied or retained."""
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getframerate() != au.SAMPLE_RATE or w.getsampwidth() != 2:
            raise RuntimeFailure("unsupported_sample_rate", "private audio must be 16-bit PCM mono 16 kHz WAV")
        frames = w.readframes(w.getnframes())
    np = importlib.import_module("numpy")
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def smoke_private_audio(path: str, language: str, root_arg: Optional[str] = None,
                        device: str = "auto") -> Dict[str, Any]:
    samples = read_private_wav(path)
    gated = GatedTranscriber(SileroVAD(), WhisperASR(models_root=root_arg, device=device))
    try:
        started = time.perf_counter()
        result = gated.transcribe(samples, language)
        return {"processed": True, "requested_language": language, "detected_language": result.detected_language,
                "vad_gated": result.vad_gated, "intervals_decoded": result.intervals_decoded,
                "duration_s": round(result.duration_s, 2), "latency_s": round(time.perf_counter() - started, 3),
                "note": "private recording: transcript deliberately not reported; no WER without an approved reference"}
    finally:
        del samples
        gated.unload()


def offline_reload(root_arg: Optional[str] = None, device: str = "auto") -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    with network_blocked() as net:
        for name in ENCODERS:
            enc = TextEncoder(name, models_root=root_arg, device=device)
            enc.load()
            enc.encode([SENTENCES["en"][1]], max_length=32)
            rows.append({"model": enc.logical_id, "reloaded_offline": True, "load_seconds": round(enc.load_seconds, 3)})
            enc.unload()
        gated = GatedTranscriber(SileroVAD(), WhisperASR(models_root=root_arg, device=device))
        gated.vad.load()
        gated.asr.load()
        result = gated.transcribe(au.concat(au.silence(1.5), au.voiced_pattern(3), au.silence(1.5)), "en")
        rows.append({"model": "whisper_small", "reloaded_offline": True,
                     "load_seconds": round(gated.asr.load_seconds, 3), "decoder_invoked": result.decoder_invoked,
                     "vad_gated": result.vad_gated})
        rows.append({"model": "silero_vad", "reloaded_offline": True})
        gated.unload()
    return {"models": rows, "network_attempts_blocked": net["attempts"], "offline": net["attempts"] == 0,
            "method": "socket connect/connect_ex/create_connection/getaddrinfo replaced; HF offline switches set; "
                      "local_files_only=True"}


def write_report(name: str, payload: Dict[str, Any], reports_arg: Optional[str]) -> Optional[str]:
    out = config.reports_dir(reports_arg)
    if out is None:
        return None
    path = out / f"{name}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path.name


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.runtime.verify_models", description=__doc__.split("\n")[0])
    parser.add_argument("--models-root", help=f"overrides {config.ROOT_ENV}; there is no default")
    parser.add_argument("--reports-dir", help=f"overrides {config.REPORTS_ENV}; omit to print only")
    parser.add_argument("--device", default="auto", choices=dev.DEVICE_CHOICES)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("integrity")
    sub.add_parser("offline-reload")
    p = sub.add_parser("smoke")
    p.add_argument("--model", required=True, choices=("muril", "xlmr", "whisper", "vad", "pipeline", "all"))
    p.add_argument("--audio", help="a private, consented 16 kHz mono WAV (whisper only); never copied or printed")
    p.add_argument("--language", choices=("hi", "en"), default="hi")
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            payload = status(args.models_root)
        elif args.command == "integrity":
            payload = integrity(args.models_root)
        elif args.command == "offline-reload":
            payload = offline_reload(args.models_root, args.device)
        else:
            with network_blocked() as net:
                if args.audio:
                    if args.model != "whisper":
                        raise RuntimeFailure("invalid_input", "--audio is only for the whisper smoke test")
                    payload = {"private_audio": smoke_private_audio(args.audio, args.language, args.models_root,
                                                                    args.device)}
                else:
                    chosen = ("muril", "xlmr", "whisper", "vad", "pipeline") if args.model == "all" else (args.model,)
                    payload = {}
                    for m in chosen:  # strictly sequential: one model resident at a time
                        if m in ENCODERS:
                            payload[m] = smoke_encoder(m, args.models_root, args.device)
                        elif m == "whisper":
                            payload[m] = smoke_whisper(args.models_root, args.device)
                        elif m == "vad":
                            payload[m] = smoke_vad()
                        else:
                            payload[m] = smoke_pipeline(args.models_root, args.device)
            payload["network_attempts_blocked"] = net["attempts"]
        written = write_report(f"verify-{args.command}" + (f"-{args.model}" if args.command == "smoke" else ""),
                               payload, args.reports_dir)
    except (config.RuntimeConfigError, RuntimeFailure) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=1, ensure_ascii=False))
    if written:
        print(f"private report written: {config.REPORTS_ENV}/{written}", file=sys.stderr)
    return 0 if payload.get("ok", True) is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
