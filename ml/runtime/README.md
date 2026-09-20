# `ml/runtime` — local model runtime (Task 6)

Lazy, offline adapters for the four approved public models. This package **prepares the
runtime only**. Nothing in it is trained, tuned or connected to a SAHAY decision.

| Logical id | Upstream | Role | Licence |
|---|---|---|---|
| `muril_base_cased` | `google/muril-base-cased` @ `afd9f36c…` | primary text encoder | Apache-2.0 |
| `xlm_roberta_base` | `FacebookAI/xlm-roberta-base` @ `e73636d4…` | comparison encoder only | MIT |
| `whisper_small` | `openai/whisper-small` @ `973afd24…` | speech-to-text (transcribe only) | Apache-2.0 |
| `silero_vad` | `silero-vad` 6.2.1 wheel (tag commit `7e30209a…`) | voice activity detection | MIT |

The exact revisions, required files, sizes and upstream hashes are in `manifest.json`. That file
is portable: it holds no machine path, no token and no weight.

## What it guarantees

- **Nothing loads on import.** Importing any `ml.runtime` module imports no Torch, Transformers,
  CTranslate2, NumPy or Silero. Models load only on an explicit `load()`.
- **Nothing downloads implicitly.** Only `python -m ml.runtime.download fetch` touches the network. It
  downloads anonymously (`token=False`), at the pinned commit, only the files the manifest lists, and
  then verifies every size and hash. Every load uses `local_files_only=True` with the Hugging Face
  offline switches set.
- **No default path.** The root comes from `SAHAY_MODELS_ROOT` or `--models-root`. A missing root is an
  explicit `unavailable` status, never a zero. Paths are confined beneath the root, and a root inside a
  SAHAY checkout is refused.
- **No decisions.** Both encoders are unfine-tuned for SAHAY labels. They return token statistics and
  mean-pooled encoder representations only: no head, no label, no probability. The pooler is not even
  instantiated (`add_pooling_layer=False`), so no randomly initialised layer exists. Whisper returns a
  transcript with `calibrated_confidence = None`, and Silero returns speech intervals. No result may
  carry an SVI, band, D4, crisis, routing, priority or prediction key.
- **Firewalled.** No application module (`assessment`, `dialogue`, `guardrails`, `svi`, `nlp`, `asr`,
  `tts`, `acoustics`, `eval`, `data`) imports this package. No backend, frontend, mobile or contract
  file names it. The deterministic pipeline, including the crisis pre-check, stays authoritative and
  runs unchanged with every model absent.
- **Private by construction.** Inputs, transcripts and audio are never logged. An inference failure
  reports its exception *type* only, and load failures are redacted of paths and tokens.

## ASR rules

- `task="transcribe"` always, so Hindi is never silently translated into English.
- The caller names the language, `hi` or `en`. Anything else is refused, and there is no silent
  auto-detection.
- One worker, CUDA FP16 (`float16`), with a CPU `int8` fallback marked `degraded`.

## VAD is an enforced boundary (Task 6A)

**Whisper is unsafe to call directly on arbitrary audio.** During qualification, Whisper Small
produced fluent text when forced to decode synthetic silence, a pure tone and synthetic non-speech.
That text is deliberately not recorded anywhere in the repository. So Silero VAD is a mandatory
precondition, enforced in code rather than advised:

- `WhisperASR.transcribe(samples, language, speech_intervals, *, sample_rate=16000)` has **no default**
  for `speech_intervals`. Omitting it is a `TypeError`, and `None` raises `vad_required` before any
  decoder work.
- The intervals are the Silero adapter's own output: `(start_s, end_s)` pairs in seconds. The whole
  list is validated before the first decoder call, so a bad later interval stops earlier ones from
  being decoded too. It refuses:
  - anything that isn't a list or tuple of pairs, missing fields, and non-numbers (including booleans);
  - NaN or infinity, negative times, an end before its start, and zero-length intervals (the pinned
    VAD never emits one, since its minimum speech length is 250 ms);
  - an end past the audio duration, or an interval that maps to no sample;
  - intervals out of ascending order, overlapping or duplicated.
- Intervals that exactly touch are kept, because Silero padding can produce them. Nothing is merged,
  padded or clipped.
- **An empty interval list skips Whisper entirely.** The result is `status="no_speech"` with an empty
  transcript and no segments, `intervals_decoded=0` and `decoder_invoked=False`, and no confidence.
  Whisper does not even need to be loaded. This is not an error, a score or a risk level.
- Whisper receives only the samples inside each accepted interval, one decoder call per interval. The
  full recording is never decoded as a fallback.
- `vad_gated` is an **enforced invariant**: every result from the public method reports
  `vad_gated=True`. There is no skip, force or unsafe option on the method or the CLI.
- `ml.runtime.pipeline.GatedTranscriber` is the intended path:
  `16 kHz mono → Silero VAD → validated intervals → Whisper on those intervals only`.
  It loads Whisper only when speech was found.
- **Benchmark-only ungated decoding** lives in the private `asr._transcribe_ungated_for_benchmark`. Only
  `ml.runtime.benchmark asr-worst-case` uses it, on synthetic signals, and its results are labelled
  `vad_gated=False, benchmark_only=True`. It is not exported, application callers must never use it,
  and a static test confines it to `asr.py` and `benchmark.py`. The benchmark records output lengths
  only, never text.

What the gate does **not** do:
- VAD is a model and can itself be wrong in both directions: speech missed, or noise passed as speech.
- A VAD interval proves only that the sound resembles speech, not that it is intelligible or
  meaningful.
- Real Hindi and English ASR quality stays unmeasured until there is approved, transcribed evaluation
  audio.
- VAD output is never distress, emotion, danger, crisis, an SVI input or D4, and no transcript from
  this path reaches the assessment pipeline.

## Private layout (outside Git)

```text
<SAHAY_MODELS_ROOT>/
  muril_base_cased/<revision>/                 pinned upstream files
  xlm_roberta_base/<revision>/
  whisper_small/<revision>/
  whisper_small/<revision>-ct2-float16/        local CTranslate2 conversion + conversion.json (hashes)
  .hf-home/                                    Hugging Face cache, redirected here during fetch
<SAHAY_MODEL_REPORTS_ROOT>/                    optional private JSON reports
```

## Commands

The default test suite needs none of these, and no GPU:

```text
python -m unittest discover -s ml/tests -t .
python -m pytest ml -q
```

The private model environment is set up once, outside Git, from `requirements-models.txt`, with
CPython 3.12 and the PyTorch CUDA 12.8 wheels. Set `SAHAY_MODELS_ROOT` and optionally
`SAHAY_MODEL_REPORTS_ROOT`, then run:

```text
python -m ml.runtime.download plan
python -m ml.runtime.download fetch --model all
python -m ml.runtime.download convert-whisper
python -m ml.runtime.hardware
python -m ml.runtime.verify_models status
python -m ml.runtime.verify_models integrity
python -m ml.runtime.verify_models offline-reload
python -m ml.runtime.verify_models smoke --model all
python -m ml.runtime.benchmark all              (includes the labelled ungated worst case)
python -m ml.runtime.benchmark asr-worst-case   (ungated synthetic worst case only; private decoder)
```

- `verify_models` and `benchmark` actively block sockets and report how many connection attempts
  they refused.
- Benchmarks run one model at a time. XLM-R is unloaded before the production-stack measurements.
- `coexist` loads MuRIL and Whisper together only when at least 4 GiB of device memory is free.

A private, consented recording can be smoke-tested:

```text
python -m ml.runtime.verify_models smoke --model whisper --audio <file> --language hi
```

The recording must be 16 kHz mono 16-bit WAV. It is read in memory and never copied. Only
processing status, language, duration and latency are reported, never the transcript, and no WER is
computed without an approved reference.

## What these numbers are not

Tokeniser statistics, latency and memory on fictional text and synthetic signals say nothing about
model quality, Hindi recognition accuracy or detection accuracy, and none may be quoted as such.
