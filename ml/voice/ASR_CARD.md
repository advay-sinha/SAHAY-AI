# Component card — speech-to-text service

| Field | Value |
|---|---|
| Component | `ml/voice/service.py`: a loopback-only HTTP process (127.0.0.1), reached by the backend through the ASR adapter (PC-11, EXT-120) |
| Models | Whisper Small (`openai/whisper-small`, pinned, converted locally for faster-whisper, GPU or CPU int8) and Silero VAD v6 (pinned wheel). Nothing is downloaded at run time; loading happens with the network blocked. |
| Pipeline | Decode (a fast path for 16 kHz mono PCM WAV, PyAV otherwise), then VAD speech regions, then Whisper on those regions only (Hindi or English, beam 5), then a confidence summary, audio-quality measures and prosody for D4 |
| Output to the backend | Transcript, status, ASR confidence, quality flags, prosody and timings. **The victim never receives any of it except the transcript line.** |

## Safeguards

- Only `hi` and `en` are accepted. Audio is capped at 60 s and 5 MB, and must be WAV, M4A or AAC.
- **Low confidence or poor audio makes the assessment abstain** (`needs_human`, invariant 6). The confidence floor is 0.5, a conservative value that was not tuned.
- Silence returns `no_speech` without running Whisper.
- The crisis pre-check runs on the transcript exactly as on typed text.

## Measured (`ml/eval/results/latency-2026-09-29.md`)

Setup: laptop GPU, synthetic Indian-English speech from built-in Windows voices, 70 turns.

| Measure | p50 | p95 | Budget |
|---|---|---|---|
| Speech-to-text request | 463 ms | 572 ms | 600 ms |
| Whole server-side voice turn | 476 ms | 581 ms | — |

- The fast WAV path then removed about 50 ms of decoding per clip. That was measured on one clip; the benchmark has not been rerun since.
- The word error rate on that synthetic speech was 0.0. This is a sanity check only, **not M6**.

## Not measured yet

- WER on real Hindi and English speech, by condition (M6). It needs Common Voice or team recordings (H5).
- Phone microphones, noise and code-switched speech.
- Latency from a real phone over Wi-Fi.
