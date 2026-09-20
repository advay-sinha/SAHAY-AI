---
name: turn-loop-latency
description: Use when working on the conversational turn loop — VAD endpointing, ASR, dialogue policy, phrasing, TTS, barge-in, or when latency is too high.
---

# Turn loop and latency

**Target: under 3 seconds from the victim finishing speaking to the assistant beginning.** Under 3 s feels attentive. Over 5 s feels broken.

## The loop

```
VAD endpoint (~700 ms silence)
  → ASR final for the utterance          ~0.6 s
  → safety pre-check                     ~0.05 s   → crisis? interrupt, stop here
  → dialogue policy (state machine)      ~0.01 s
  → LLM phrasing (constrained)           ~0.8 s
  → output validator                     ~0.02 s   → fail? use fallback text
  → TTS first chunk                      ~0.5 s    → fixed turns: ~0 s (pre-synthesised)
```

## Rules

1. **The assessment path is parallel and never blocks the reply.** Acoustics, detectors, extraction and SVI are queued. The only assessment output allowed to interrupt the conversation is the crisis pre-check, which is deliberately a fast lexicon-plus-classifier check, not the full pipeline. If anyone puts SVI computation on the reply path, the assistant hesitates for seconds at emotionally critical moments.
2. **Pre-synthesise every fixed turn at build time.** S0, S9, SX and every intent fallback become WAV files. This removes TTS from the critical path for roughly half of all turns and makes the crisis script instantaneous.
3. **Barge-in is client-side.** When the app's local VAD detects the user speaking, it stops the playback queue immediately and treats the speech as the next turn. Distressed people interrupt; a bot that talks over them is unusable.
4. **Endpoint on silence, never on duration.** Never cut a victim off.
5. **Silence over ~15 s** ⇒ one gentle prompt, then wait. Never loop.
6. **"I want to talk to a person"** is matched by lexicon in both languages, never left to the model, and transfers immediately.

## The two levers when it is too slow

- ASR model size (faster-whisper small, int8, CPU) and endpoint threshold
- How many turns are pre-synthesised rather than generated

Measure before optimising. Instrument every stage and report the actual distribution, not an average — the slowest turn is what the panel notices.
