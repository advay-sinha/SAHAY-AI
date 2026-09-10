# ml/ — Team A (AI/ML)

> Root `CLAUDE.md` governs this directory. Its STOP RULES override anything here.
> Subagent: `ai-ml-engineer`. Safety review: `dialogue-safety-reviewer`.

## What this directory owns

Everything the system **says** and everything it **concludes**: the dialogue state machine, the guardrail layer, ASR, VAD, TTS, acoustics, the detectors, the SVI engine, the LLM prompts, the evaluation, and both corpora.

## The three pure modules — do not add I/O to these

```python
dialogue.next(state, slots, utterance, safety_flags)
    -> {next_state, intent, licensed_question, fallback_text}
guardrails.validate(text, intent, lang)
    -> {ok, reason, safe_text}
svi.compute(dimension_scores, confidences, quality)
    -> {svi, band, needs_human, breakdown, overrides_applied}
```

Standard library only. No `torch`, no `requests`, no file reads at call time. Backend imports them without any ML dependency and manual verification tests them in seconds. This is deliberate — protect it.

## Layout

```
dialogue/    states.py · policy.py · intents.py · scripts/ · prompts/
guardrails/  validator.py · lexicons/ · banned_patterns.py
svi/         engine.py · dimensions.py · overrides.py
asr/         transcribe.py · vad.py · langid.py
tts/         synthesize.py · presynth.py
acoustics/   features.py · quality.py
nlp/         detectors.py · classifiers.py · extraction.py
eval/        run_eval.py · metrics.py · results/
tests/       one file per pure module, plus detector tests
```

## Phases

**P0 — Day 1**
- Datasets identified and access requests sent (IEMOCAP, DAIC-WOZ take days — ask before downloading anything, STOP RULE 2.1)
- Ten scenario scripts started, written as **two-sided dialogues**, not monologues

**P1 — Days 2–4 → Day 4 gate**
- 12-state machine implemented, pure, unit-tested; crisis interrupt unconditional
- All fixed scripts (S0, S9, SX) written in Hindi and English, reviewed, pre-synthesised — **due end of Day 3, this blocks Backend and Frontend**
- Guardrail lexicons and output validator v1
- Endpointed ASR returning Hindi text; VAD tuned; TTS producing audio
- Ten scenario scripts finalised and recorded (hi/en, quiet/noisy) — **due end of Day 4**

**P2 — Days 5–8 → Day 8 gate**
- Crisis interrupt working end to end with Backend
- LLM phrasing with per-intent fallbacks; structured extraction schema
- MuRIL distress and crisis classifiers; threat, isolation, medical, legal, coercion detectors
- Acoustics and the D4 scorer; SVI engine complete with overrides and abstention; uncertainty engine
- Interpretable baselines (LogReg, XGBoost) for the comparison table

**P3 — Days 9–11**
- SAFE-SIGNAL divergence rule and thresholds
- Full evaluation: WER by language and condition, detector P/R/F1, **critical-event miss rate**, calibration, fairness slices, ablations (text-only / voice-only / both / full)
- Guardrail red-team with the table for the deck
- LLM offline cache

**P4 — Days 12–13** — freeze, judge-defence document, evaluation table finalised.

## Checks before you call anything done

- [ ] `pytest ml/tests/` green; the three pure modules have no I/O
- [ ] Every prohibition in root `CLAUDE.md` §2.3 has a guardrail test in both languages
- [ ] Any dialogue or guardrail change updates `docs/dialogue/STATES.md` in the same commit, labelled `type:dialogue`, two reviewers
- [ ] Every intent has a pre-written Hindi and English fallback — the system must run with the LLM off
- [ ] Numbers reported are **measured**, never estimated
- [ ] No model, dataset or package added without asking (STOP RULE 2.1)

## Never

- Let the LLM choose the next state or ask an unlicensed question
- Make the crisis interrupt conditional, resumable, or model-decided
- Fabricate a score when confidence is low — return `needs_human`
- Present a favourable slice as the headline result. If a model is weak, say so with the number
- Commit audio, model weights, or datasets. Manifests only
