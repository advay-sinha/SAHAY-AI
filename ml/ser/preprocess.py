"""SER audio preprocessing and the Whisper-encoder feature cache (plan M12c, run R2).

Run inside the private ``sahay-ml-models`` environment, after ``python -m ml.data.ser_corpus build``:

    python -m ml.ser.preprocess audio        # 16 kHz mono, Silero VAD, prosody + quality, trimmed clips
    python -m ml.ser.preprocess whisper      # frozen Whisper Small encoder, mean-pooled per layer (GPU)

Everything stays beneath ``<SAHAY_TRAINING_ROOT>/ser/corpus-v1/``:

    audio16k/<dataset>/<stem>.wav     trimmed 16 kHz mono int16 clips (private; never in Git)
    features.jsonl                    per clip: status, durations, VAD intervals, quality, prosody
    whisper_small/embeddings.npy      (N, 13, 768) float16, one row per usable clip
    whisper_small/index.json          clip order, model revision, pooling rule
    reports/*.json                    counts, timings, versions and peak VRAM: no audio, no names

Every step runs with network connections blocked. Each source file's sha256 is checked
against the corpus manifest before use. Prosody and VAD outputs are measurements. They are
never labels, emotions or D4 values.
"""

import argparse
import hashlib
import importlib
import io
import json
import math
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from ..acoustics import prosody
from ..runtime import config as rc
from ..runtime.offline import apply_offline_env, network_blocked

SAMPLE_RATE = 16000
TRIM_PAD_S = 0.10
#: Whisper's encoder emits one frame per 20 ms (320 samples) and always sees 30 s (1500 frames).
WHISPER_FRAME_SAMPLES = 320
WHISPER_MAX_FRAMES = 1500
WHISPER_BATCH = 16
CORPUS_DIR = ("ser", "corpus-v1")
PREPROCESS_VERSION = "ser-preprocess-1.0"


class PreprocessError(Exception):
    """A refusal with a fixed message: no path, no audio."""


# --- pure helpers (tested without numpy) -------------------------------------------------------


def trim_window(intervals: Sequence[Tuple[float, float]], duration_s: float,
                pad_s: float = TRIM_PAD_S) -> Optional[Tuple[float, float]]:
    """From the first speech onset to the last offset, padded; None when there is no speech."""
    if not intervals:
        return None
    start = max(0.0, intervals[0][0] - pad_s)
    end = min(duration_s, intervals[-1][1] + pad_s)
    return (round(start, 4), round(end, 4)) if end > start else None


def shift_intervals(intervals: Sequence[Tuple[float, float]], offset_s: float,
                    duration_s: float) -> List[Tuple[float, float]]:
    """Intervals re-expressed relative to a trimmed clip that starts at ``offset_s``."""
    out = []
    for s, e in intervals:
        # Round first, then clamp: rounding must never push an end past the clip's real length.
        s2 = max(0.0, round(s - offset_s, 4))
        e2 = min(duration_s, round(e - offset_s, 4))
        if e2 > s2:
            out.append((s2, e2))
    return out


def whisper_valid_frames(n_samples: int) -> int:
    """Encoder frames that cover real audio; the rest of the 30 s window is padding."""
    return int(min(WHISPER_MAX_FRAMES, max(1, math.ceil(n_samples / WHISPER_FRAME_SAMPLES))))


def output_rel(clip_id: str) -> str:
    dataset, stem = clip_id.split(":", 1)
    if not stem or any(c in stem for c in "/\\:") or stem.startswith("."):
        raise PreprocessError("unsafe clip id")
    return f"audio16k/{dataset}/{stem}.wav"


# --- paths --------------------------------------------------------------------------------------


def corpus_dir(training_root: Path) -> Path:
    from ..training import paths
    return paths.confined(training_root, *CORPUS_DIR)


def read_clips(directory: Path) -> List[Dict[str, Any]]:
    path = directory / "clips.jsonl"
    if not path.is_file():
        raise PreprocessError("clips.jsonl is missing; run `python -m ml.data.ser_corpus build` first")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != manifest.get("clips_sha256"):
        raise PreprocessError("clips.jsonl does not match its manifest hash")
    return [json.loads(line) for line in body.decode("utf-8").splitlines() if line.strip()]


def source_root(directory: Path) -> Path:
    """The audio source root recorded by ``ml.data.ser_corpus`` in its private manifest."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    raw = manifest.get("datasets_root") or ""
    root = Path(raw).resolve() if raw else None
    if root is None or not root.is_dir():
        raise PreprocessError("the corpus manifest does not name an existing source root; rebuild the corpus")
    return root


def resolve_under(root: Path, rel: str) -> Path:
    """A corpus-relative source path, refused if it is absolute or escapes the source root."""
    if not rel or rel.startswith(("/", "\\")) or ":" in rel or ".." in rel.replace("\\", "/").split("/"):
        raise PreprocessError("unsafe source path in the clip list")
    target = (root / rel).resolve()
    if root not in target.parents:
        raise PreprocessError("source path escapes the source root")
    return target


# --- audio I/O ------------------------------------------------------------------------------------


def read_wav(data: bytes) -> Tuple[Any, int]:
    """16-bit PCM WAV bytes -> (float32 mono in [-1, 1], sample rate). stdlib wave + numpy."""
    np = importlib.import_module("numpy")
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise PreprocessError("only 16-bit PCM WAV is supported")
        channels, rate, frames = w.getnchannels(), w.getframerate(), w.readframes(w.getnframes())
    x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return x, rate


def to_16k(x: Any, rate: int) -> Any:
    if rate == SAMPLE_RATE:
        return x
    torch = importlib.import_module("torch")
    functional = importlib.import_module("torchaudio.functional")
    return functional.resample(torch.from_numpy(x), rate, SAMPLE_RATE).numpy()


def write_wav(path: Path, x: Any) -> None:
    np = importlib.import_module("numpy")
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    tmp.replace(path)


# --- step 1: audio --------------------------------------------------------------------------------


def run_audio(out: Path) -> Dict[str, Any]:
    from ..acoustics import signal
    from ..runtime.vad import SileroVAD

    clips = read_clips(out)
    sources = source_root(out)
    vad = SileroVAD()
    vad.load()
    started = time.perf_counter()
    counts: Dict[str, int] = {}
    rows: List[str] = []
    try:
        for i, clip in enumerate(clips, 1):
            row = {"clip_id": clip["clip_id"], "split": clip["split"], "label": clip["label"]}
            try:
                data = resolve_under(sources, clip["source_rel"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != clip["source_sha256"]:
                    raise PreprocessError("source hash mismatch")
                x, rate = read_wav(data)
                x = to_16k(x, rate)
                duration = x.size / SAMPLE_RATE
                spans = vad.intervals(x).intervals
                window = trim_window(spans, duration)
                row.update({"duration_s": round(duration, 4), "source_rate": rate})
                if window is None:
                    row["status"] = "no_speech"
                else:
                    a, b = int(window[0] * SAMPLE_RATE), int(window[1] * SAMPLE_RATE)
                    y = x[a:b]
                    ivals = shift_intervals(spans, window[0], y.size / SAMPLE_RATE)
                    m = signal.measure(y, ivals)
                    summary = prosody.summarize_turn(m["f0_hz"], m["rms_db"], ivals, m["duration_s"])
                    write_wav(out / output_rel(clip["clip_id"]), y)
                    row.update({
                        "status": "ok", "audio_rel": output_rel(clip["clip_id"]),
                        "trimmed_s": round(y.size / SAMPLE_RATE, 4), "intervals": ivals,
                        "speech_s": summary["speech_s"], "quality": m["quality"],
                        "prosody": summary["features"], "prosody_reasons": summary["reasons"],
                    })
            except PreprocessError as exc:
                row["status"] = f"refused:{exc}"
            except Exception as exc:  # the type only: no path, no audio
                row["status"] = f"error:{type(exc).__name__}"
            counts[row["status"]] = counts.get(row["status"], 0) + 1
            rows.append(json.dumps(row, sort_keys=True))
            if i % 500 == 0:
                print(json.dumps({"progress": i, "of": len(clips), "seconds": round(time.perf_counter() - started, 1)}),
                      flush=True)
    finally:
        vad.unload()
    (out / "features.jsonl").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
    return {"step": "audio", "version": PREPROCESS_VERSION, "clips": len(clips), "status_counts": counts,
            "seconds": round(time.perf_counter() - started, 1)}


# --- step 2: Whisper encoder features ---------------------------------------------------------------


def _usable(out: Path) -> List[Dict[str, Any]]:
    path = out / "features.jsonl"
    if not path.is_file():
        raise PreprocessError("features.jsonl is missing; run the audio step first")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r.get("status") == "ok"]


def run_whisper(models_root: Path, out: Path, batch: int = WHISPER_BATCH) -> Dict[str, Any]:
    np = importlib.import_module("numpy")
    torch = importlib.import_module("torch")
    apply_offline_env()
    transformers = importlib.import_module("transformers")
    entry = rc.get_model(rc.load_manifest(), "whisper_small")
    directory = rc.model_dir(models_root, entry)
    check = rc.verify_files(directory, entry["files"], full_hash=False)
    if not check["ok"]:
        raise PreprocessError("Whisper Small files are missing or the wrong size")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    extractor = transformers.WhisperFeatureExtractor.from_pretrained(str(directory), local_files_only=True)
    model = transformers.WhisperModel.from_pretrained(str(directory), local_files_only=True, torch_dtype=dtype)
    encoder = model.get_encoder().to(device).eval()
    del model
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    rows = _usable(out)
    feats = np.zeros((len(rows), 13, 768), dtype=np.float16)
    started = time.perf_counter()
    with torch.inference_mode():
        for start in range(0, len(rows), batch):
            chunk = rows[start:start + batch]
            audio = [read_wav((out / r["audio_rel"]).read_bytes())[0] for r in chunk]
            inputs = extractor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt")
            hidden = encoder(inputs.input_features.to(device, dtype), output_hidden_states=True).hidden_states
            stacked = torch.stack(hidden, dim=1)  # (B, 13, 1500, 768)
            for j, x in enumerate(audio):
                n = whisper_valid_frames(x.size)
                feats[start + j] = stacked[j, :, :n, :].float().mean(dim=1).cpu().numpy().astype(np.float16)
            if (start // batch) % 50 == 0:
                print(json.dumps({"progress": start + len(chunk), "of": len(rows),
                                  "seconds": round(time.perf_counter() - started, 1)}), flush=True)
    target = out / "whisper_small"
    target.mkdir(parents=True, exist_ok=True)
    np.save(target / "embeddings.npy", feats)
    index = {"clip_ids": [r["clip_id"] for r in rows], "shape": list(feats.shape), "dtype": "float16",
             "model": "whisper_small", "revision": entry["revision"], "layers": "embedding output + 12 encoder layers",
             "pooling": "mean over the encoder frames covering real audio (20 ms per frame); padding excluded",
             "version": PREPROCESS_VERSION}
    (target / "index.json").write_bytes((json.dumps(index, indent=1) + "\n").encode("utf-8"))
    report = {"step": "whisper", "clips": len(rows), "device": device, "dtype": str(dtype).replace("torch.", ""),
              "seconds": round(time.perf_counter() - started, 1), "torch": torch.__version__,
              "transformers": transformers.__version__}
    if device == "cuda":
        report["peak_vram_mib"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
    return report


# --- CLI --------------------------------------------------------------------------------------------


def _write_report(out: Path, name: str, report: Dict[str, Any]) -> None:
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "reports" / f"{name}.json").write_bytes((json.dumps(report, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ml.ser.preprocess", description=__doc__.split("\n")[0])
    parser.add_argument("--models-root", default=None)
    parser.add_argument("--training-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audio")
    w = sub.add_parser("whisper")
    w.add_argument("--batch", type=int, default=WHISPER_BATCH)
    args = parser.parse_args(argv)

    from ..training import paths
    out = corpus_dir(paths.training_root(args.training_root))
    with network_blocked() as net:
        if args.cmd == "audio":
            report = run_audio(out)
        else:
            report = run_whisper(rc.models_root(args.models_root), out, args.batch)
        report["network_attempts_blocked"] = net["attempts"]
    _write_report(out, args.cmd, report)
    print(json.dumps(report, indent=1))
    return 0 if net["attempts"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
