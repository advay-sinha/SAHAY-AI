"""Explicit local benchmarks. Never part of the default test suite.

    python -m ml.runtime.benchmark text --model muril|xlmr
    python -m ml.runtime.benchmark asr
    python -m ml.runtime.benchmark asr-worst-case    (ungated synthetic worst case; private decoder)
    python -m ml.runtime.benchmark vad
    python -m ml.runtime.benchmark pipeline
    python -m ml.runtime.benchmark coexist
    python -m ml.runtime.benchmark all

Benchmarks run strictly one model at a time, with the network blocked, on fictional text
(``fixtures.py``) and synthetic signals (``audio.py``). They measure tokenisation, latency and
memory only; they say nothing about model quality or recognition accuracy. ``all`` runs MuRIL,
then XLM-R, then Whisper, VAD and the pipeline, unloading each before the next; XLM-R is
never resident alongside the production stack. ``coexist`` loads MuRIL and Whisper together
only when the device reports enough free memory, and otherwise records why it was skipped.
"""

import argparse
import json
import statistics
import sys
import time
from typing import Any, Callable, Dict, List, Optional

from . import audio as au, config, device as dev
from .asr import WhisperASR, _transcribe_ungated_for_benchmark
from .fixtures import LANGUAGES, SENTENCES, TARGET_TOKENS, build_text
from .offline import network_blocked
from .pipeline import GatedTranscriber
from .status import RuntimeFailure
from .text_encoder import TextEncoder
from .vad import FUNCTIONAL_ONLY, SileroVAD
from .verify_models import write_report

#: MuRIL FP16 plus Whisper Small FP16 plus working memory is far below this; the margin
#: keeps a laptop display and other processes safe.
COEXIST_MIN_FREE_MB = 4096
THROUGHPUT_BATCH = 8
NOTE = "latency and memory on fictional text and synthetic signals; not a quality measurement"


def _percentiles(samples: List[float]) -> Dict[str, float]:
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"p50_ms": round(statistics.median(ordered) * 1000, 2), "p95_ms": round(p95 * 1000, 2),
            "mean_ms": round(statistics.fmean(ordered) * 1000, 2)}


def _timed(fn: Callable[[], Any], torch: Any, device: str) -> float:
    dev.synchronize(torch, device)
    started = time.perf_counter()
    fn()
    dev.synchronize(torch, device)
    return time.perf_counter() - started


def bench_text(model: str, runs: int, root_arg: Optional[str], device: str) -> Dict[str, Any]:
    torch = dev.import_torch()
    choice = dev.select_device(device)
    dev.release(torch)
    dev.reset_peak(torch, choice.device)
    rss_before = dev.process_rss_mb()
    enc = TextEncoder(model, models_root=root_arg, device_choice=choice)
    dev.synchronize(torch, choice.device)
    started = time.perf_counter()
    enc.load()
    dev.synchronize(torch, choice.device)
    cold_load = time.perf_counter() - started
    try:
        rows = []
        for lang in LANGUAGES:
            for target in TARGET_TOKENS:
                text = build_text(lang, target, lambda t: enc.token_stats([t])[0].token_count)
                stats = enc.token_stats([text])[0]
                max_len = min(512, stats.token_count)
                enc.encode([text], max_length=max_len)  # warm-up
                times = [_timed(lambda: enc.encode([text], max_length=max_len), torch, choice.device)
                         for _ in range(runs)]
                batch = [text] * THROUGHPUT_BATCH
                batch_time = statistics.median(
                    _timed(lambda: enc.encode(batch, max_length=max_len), torch, choice.device) for _ in range(5))
                a = enc.encode([text], max_length=max_len).embeddings[0]
                b = enc.encode([text], max_length=max_len).embeddings[0]
                rows.append({"language": lang, "target_tokens": target, "tokens": stats.token_count,
                             "characters": stats.characters,
                             "tokens_per_char": round(stats.tokens_per_character, 3),
                             "unknown_rate": None if stats.unknown_rate is None else round(stats.unknown_rate, 4),
                             **_percentiles(times),
                             "samples_per_s_batch8": round(THROUGHPUT_BATCH / batch_time, 1),
                             "deterministic": a == b})
        memory = dev.cuda_memory(torch, choice.device)
        return {"model": enc.logical_id, "role": enc.role, "device": choice.device, "precision": choice.precision,
                "degraded": choice.degraded, "cold_load_s": round(cold_load, 3), "runs_per_cell": runs,
                "rows": rows, **memory, "rss_mb_before": rss_before, "rss_mb_loaded": dev.process_rss_mb(),
                "note": NOTE}
    finally:
        enc.unload()


def bench_asr(runs: int, root_arg: Optional[str], device: str) -> Dict[str, Any]:
    """Gated ASR latency: VAD intervals first, then Whisper on those regions only."""
    torch = dev.import_torch()
    choice = dev.select_device(device)
    dev.release(torch)
    free_before = dev.device_free_mb(torch)
    gated = GatedTranscriber(SileroVAD(), WhisperASR(models_root=root_arg, device_choice=choice))
    started = time.perf_counter()
    gated.asr.load()
    cold_load = time.perf_counter() - started
    free_loaded = dev.device_free_mb(torch)
    try:
        rows, low_free = [], free_loaded
        for seconds in (5, 15, 30):
            signal = au.concat(au.silence(1), au.voiced_pattern(seconds - 2), au.silence(1))
            for lang in ("hi", "en"):
                gated.transcribe(signal, lang)  # warm-up
                times, decoded = [], []
                for _ in range(runs):
                    t0 = time.perf_counter()
                    r = gated.transcribe(signal, lang)
                    times.append(time.perf_counter() - t0)
                    decoded.append(r.intervals_decoded)
                    f = dev.device_free_mb(torch)
                    low_free = min(low_free, f) if (f is not None and low_free is not None) else low_free
                p = _percentiles(times)
                rows.append({"audio_s": seconds, "language": lang, **p,
                             "real_time_factor_p50": round(p["p50_ms"] / 1000 / seconds, 3),
                             "intervals_decoded_median": statistics.median(decoded), "vad_gated": r.vad_gated,
                             "vad_speech_s": r.runtime.get("vad_speech_s")})
        used = None if free_before is None or low_free is None else round(free_before - low_free, 1)
        return {"model": "whisper_small", "path": "Silero VAD -> validated intervals -> Whisper",
                "device": choice.device, "compute_type": gated.asr.compute_type, "degraded": choice.degraded,
                "cold_load_s": round(cold_load, 3), "runs_per_cell": runs, "rows": rows,
                "device_free_mb_before": free_before, "device_free_mb_loaded": free_loaded,
                "device_mb_used_peak_observed": used, "rss_mb_loaded": dev.process_rss_mb(),
                "note": NOTE + "; latency includes the VAD pass"}
    finally:
        gated.unload()


def bench_asr_ungated_worst_case(runs: int, root_arg: Optional[str], device: str) -> Dict[str, Any]:
    """UNGATED SYNTHETIC WORST-CASE BENCHMARK. Private decoder, never an application path.

    Forces Whisper to decode synthetic non-speech to measure what the VAD gate prevents. Only
    output lengths are recorded; no text is printed or stored.
    """
    asr = WhisperASR(models_root=root_arg, device=device)
    asr.load()
    try:
        rows = []
        for label, signal in (("silence_5s", au.silence(5)), ("tone_5s", au.tone(5)),
                              ("voiced_pattern_5s", au.voiced_pattern(5))):
            for lang in ("hi", "en"):
                times, chars = [], []
                for _ in range(runs):
                    t0 = time.perf_counter()
                    r = _transcribe_ungated_for_benchmark(asr, signal, lang)
                    times.append(time.perf_counter() - t0)
                    chars.append(len(r.text))
                rows.append({"signal": label, "language": lang, **_percentiles(times),
                             "output_characters_median": statistics.median(chars),
                             "vad_gated": r.vad_gated, "benchmark_only": r.benchmark_only})
        return {"label": "ungated synthetic worst-case benchmark (benchmark_only; not an application path)",
                "rows": rows,
                "note": "non-zero output on silence or a tone is hallucination that the public VAD gate prevents"}
    finally:
        asr.unload()


def bench_vad(runs: int) -> Dict[str, Any]:
    vad = SileroVAD()
    started = time.perf_counter()
    vad.load()
    cold = time.perf_counter() - started
    try:
        rows = []
        for seconds in (5, 30, 60):
            signal = au.concat(au.silence(seconds / 4), au.voiced_pattern(seconds / 2), au.silence(seconds / 4))
            vad.intervals(signal)
            times = []
            for _ in range(runs):
                t0 = time.perf_counter()
                r = vad.intervals(signal)
                times.append(time.perf_counter() - t0)
            rows.append({"audio_s": seconds, **_percentiles(times), "intervals": len(r.intervals),
                         "speech_s": r.speech_s})
        return {"model": "silero_vad", "device": "cpu", "cold_load_s": round(cold, 3), "runs_per_cell": runs,
                "rows": rows, "note": FUNCTIONAL_ONLY}
    finally:
        vad.unload()


def bench_pipeline(runs: int, root_arg: Optional[str], device: str) -> Dict[str, Any]:
    gated = GatedTranscriber(SileroVAD(), WhisperASR(models_root=root_arg, device=device))
    try:
        rows = []
        for label, signal in (("silence_10s", au.silence(10)),
                              ("silence_voiced_silence_10s",
                               au.concat(au.silence(3), au.voiced_pattern(4), au.silence(3)))):
            times, decoder_runs = [], 0
            for _ in range(runs):
                t0 = time.perf_counter()
                r = gated.transcribe(signal, "hi")
                times.append(time.perf_counter() - t0)
                decoder_runs += r.decoder_invoked
            rows.append({"signal": label, **_percentiles(times), "vad_intervals": r.intervals_detected,
                         "decoder_runs": decoder_runs, "runs": runs, "vad_gated": r.vad_gated})
        return {"pipeline": "Silero VAD -> validated intervals -> Whisper Small", "rows": rows,
                "note": FUNCTIONAL_ONLY}
    finally:
        gated.unload()


def bench_coexist(root_arg: Optional[str], device: str) -> Dict[str, Any]:
    torch = dev.import_torch()
    choice = dev.select_device(device)
    if choice.device != "cuda":
        return {"tested": False, "reason": "CUDA unavailable; coexistence is a GPU question"}
    dev.release(torch)
    free = dev.device_free_mb(torch)
    if free is None or free < COEXIST_MIN_FREE_MB:
        return {"tested": False, "reason": f"only {free} MiB free; need {COEXIST_MIN_FREE_MB} MiB for a safe test"}
    enc = TextEncoder("muril", models_root=root_arg, device_choice=choice)
    gated = GatedTranscriber(SileroVAD(), WhisperASR(models_root=root_arg, device_choice=choice))
    try:
        enc.load()
        after_muril = dev.device_free_mb(torch)
        gated.asr.load()
        after_both = dev.device_free_mb(torch)
        text = " ".join(SENTENCES["hinglish"])
        signal = au.concat(au.silence(3), au.voiced_pattern(4), au.silence(3))
        enc.encode([text], max_length=128)
        gated.transcribe(signal, "hi")
        t_enc = [_timed(lambda: enc.encode([text], max_length=128), torch, "cuda") for _ in range(20)]
        t_asr = []
        for _ in range(3):
            t0 = time.perf_counter()
            gated.transcribe(signal, "hi")
            t_asr.append(time.perf_counter() - t0)
        low = dev.device_free_mb(torch)
        return {"tested": True, "device_free_mb_before": free, "device_free_mb_muril_loaded": after_muril,
                "device_free_mb_both_loaded": after_both, "device_free_mb_after_inference": low,
                "device_mb_used_by_both": round(free - min(after_both, low), 1),
                "muril_encode_128": _percentiles(t_enc), "gated_whisper_10s_hi": _percentiles(t_asr),
                "coexist_ok": True, "headroom_mb": low}
    except RuntimeFailure as exc:
        return {"tested": True, "coexist_ok": False, "failure": exc.code}
    finally:
        gated.unload()
        enc.unload()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.runtime.benchmark", description=__doc__.split("\n")[0])
    parser.add_argument("--models-root", help=f"overrides {config.ROOT_ENV}; there is no default")
    parser.add_argument("--reports-dir", help=f"overrides {config.REPORTS_ENV}; omit to print only")
    parser.add_argument("--device", default="auto", choices=dev.DEVICE_CHOICES)
    parser.add_argument("--runs", type=int, default=20)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("text")
    p.add_argument("--model", required=True, choices=("muril", "xlmr"))
    for name in ("asr", "asr-worst-case", "vad", "pipeline", "coexist", "all"):
        sub.add_parser(name)
    args = parser.parse_args(argv)
    payload: Dict[str, Any] = {}
    try:
        with network_blocked() as net:
            if args.command in ("text", "all"):
                for m in ((args.model,) if args.command == "text" else ("muril", "xlmr")):
                    payload[f"text_{m}"] = bench_text(m, args.runs, args.models_root, args.device)
            if args.command in ("asr", "all"):
                payload["asr"] = bench_asr(max(3, args.runs // 4), args.models_root, args.device)
            if args.command in ("asr-worst-case", "all"):
                payload["asr_ungated_worst_case_benchmark"] = bench_asr_ungated_worst_case(
                    3, args.models_root, args.device)
            if args.command in ("vad", "all"):
                payload["vad"] = bench_vad(args.runs)
            if args.command in ("pipeline", "all"):
                payload["pipeline"] = bench_pipeline(max(3, args.runs // 4), args.models_root, args.device)
            if args.command in ("coexist", "all"):
                payload["coexist"] = bench_coexist(args.models_root, args.device)
        payload["network_attempts_blocked"] = net["attempts"]
        written = write_report(f"benchmark-{args.command}", payload, args.reports_dir)
    except (config.RuntimeConfigError, RuntimeFailure) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=1, ensure_ascii=False))
    if written:
        print(f"private report written: {config.REPORTS_ENV}/{written}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
