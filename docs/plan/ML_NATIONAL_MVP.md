# SAHAY-AI ML — national-level MVP phase plan

Status as of 2026-09-24. **All decisions D-1 to D-15 approved by the owner on 2026-09-24**; see `docs/EXTERNAL_DECISIONS.md` (EXT-120 to EXT-128). **EXT-129 (2026-09-26):** every downloaded dataset is open for MVP model research, training and validation, and source labels may act as weak-supervision training labels. Dataset content still never reaches the product, the demo, a victim or the official locked set. Owner: AI/ML and Safety lead. Scope: everything under `ml/` plus the ML side of the backend voice path.

This file records which ML phases are finished (with evidence), how far each Problem Statement 26093 requirement is met, and the phases still needed for a national-finale MVP supporting at least three language varieties. It sits under `docs/plan/PHASES.md` and does not change any frozen contract. Any contract, dialogue or external-dependency change listed below goes through its normal process (`contract-change`, `dialogue-authoring` and `docs/EXTERNAL_DECISIONS.md`).

Every number in this file was measured. "Unmeasured" means nobody has measured it yet. It does not mean zero.

---

## 1. Target: what the national MVP must demonstrate

| # | Capability | Minimum for the national MVP |
|---|---|---|
| T1 | Languages | **Hindi, English and Hinglish** (code-mixed, in Roman or Devanagari script) end to end for text. Hindi and English for voice. An optional fourth, regional language (§5, D-1) starts as text-only. |
| T2 | Voice analysis | Speech is transcribed locally. Pauses, pitch variation, energy and speech rate are measured. **Speech emotion recognition** (SER, audio) runs alongside a **MuRIL text-affect** branch. D4 (acute distress) is scored on voice sessions instead of always abstaining. |
| T3 | Text analysis | Every indicator the Problem Statement names is covered in every shipped language, with evidence links. |
| T4 | SVI and bands | 0–100 SVI, Low/Moderate/High/Critical and Needs Human Assessment, with breakdown and confidence. Already done. |
| T5 | Recommendations | Counselling, legal aid, medical, police, witness protection and emergency. Already done. They stay `awaiting_decision` until a human acts. |
| T6 | Voice output | Human-approved fixed scripts (S0, S9, SX, SH) in every shipped language, with audio. Generated turns are validated before synthesis. |
| T7 | Evidence | A per-language evaluation table: critical-event miss rate, detector P/R/F1, WER/CER and latency. Each number carries its evidence class (exposed, locked or blind). |
| T8 | Safety invariants | All eight invariants in root `CLAUDE.md` §2 are still intact and tested. |

---

## 2. Problem Statement 26093: requirement coverage

| PS requirement | Status | Evidence | Gap |
|---|---|---|---|
| Analyse textual narratives | **Done (deterministic)** | `ml/assessment.py`: lexicon detectors for D1, D3, D5–D9, crisis pre-check D2 and hi/en/Hinglish lexicons | Lexicons are small. For example, D5 has about 14 terms. |
| Analyse voice interactions | **Partial** | `ml/runtime`: Silero VAD → Whisper Small through `GatedTranscriber`, qualified offline on the RTX 4060 (EXT-118) | Not wired into the product: `POST /sessions/{id}/audio` returns 501. WER is unmeasured. |
| Speech patterns, pauses, pitch variation | **Not started** | Interfaces only: `ml/acoustics/features.py` and `quality.py` | D4 abstains on every voice channel (PC-08). |
| Emotional indicators / emotion AI | **Text only, partial** | D3 fear lexicon and D5 trauma-associated lexicon. MuRIL Stage B EmoInHindi head (macro-F1 0.355, isolated diagnostic). | No SER. CREMA-D media are LFS pointers. RAVDESS is still PROPOSED. Planned in M12. |
| Stress, trauma, fear, anxiety | **Partial** | D3 (fear) and D5 (sleep, flashback, shaking) | No anxiety or low-mood phrasing (e.g. hopelessness, panic) outside the crisis lexicon |
| Depression, suicidal ideation | **Crisis done; depression by design only as linguistic indicators** | Crisis pre-check (`crisis-v1.2`) is synchronous, runs before policy and forces SX | Low-mood indicators are missing (see above). A diagnosis must never be output. |
| Intimidation | **Done** | D3 and `continuing_threat`: dev recall 0.80, candidate recall 0.917 (baseline) | Breadth |
| Social isolation | **Done** | D6: dev recall 0.80, candidate recall 0.50 | Recall on unseen phrasing |
| Extreme vulnerability | **Done** | SVI with hard overrides, abstention and trajectory | Weights are PROVISIONAL and uncalibrated by experts |
| SVI on a predefined scale, four bands | **Done** | `ml/svi` is pure and tested | — |
| Auto-recommend counselling, legal aid, medical, police, witness protection, emergency | **Done** | `ml/nlp/recommend.py`: 6 pathways with rationale and evidence | Policy citations need a real policy corpus (EXT-108, backend) |
| Major Indian languages and dialects | **Partial** | Text: hi, en and Hinglish. Voice: hi and en qualified, not measured. | No regional language. Hinglish voice is unmeasured. |
| Privacy, consent, confidentiality, ethical AI | **Done for the MVP** | Consent gating and suppression, offline models, label firewall, no-leakage tests, red-team | Licences for the external datasets are still `licence_pending` (shadow model only) |
| Real-time | **Text: yes. Voice: unmeasured.** | The pure modules run synchronously | M2/M3 latency has never been measured on a voice turn |

---

## 3. Phases achieved

| Phase | What was built | Evidence |
|---|---|---|
| **M0 — Pure core** | 12-state dialogue policy (`dialogue.next`), output validator (`guardrails.validate`), SVI engine (`svi.compute`) with overrides, abstention and missing-modality renormalisation. Standard library only. | `ml/tests/test_pure_modules.py`, `test_dialogue.py`, `test_svi.py`, `test_svi_normalization.py` |
| **M1 — Crisis pre-check** | Synchronous hi/en/Hinglish crisis lexicon with negation and quotation handling. Forces SX, Critical and human takeover. Two code-level reviews. | `ml/guardrails/crisis_precheck.py`, `ml/eval/reviews/crisis-precheck-review.md` |
| **M2 — Deterministic assessment** | `assess()`: text detectors with evidence turn ids, heuristic language ID, structured extraction (`extracted` vs `answered` slots), recommendations, alerts, uncertainty and PC-08 D4 handling. Backend imports it through intake, turn_loop and the assessment worker. | `ml/assessment.py`, `backend/app/workers/assessment.py` |
| **M3 — Evaluation harness** | Label schema 1.0.0, dev (57), candidate (48) and red-team (39 + 75 + 29) corpora, metrics, contamination ledger and baseline report | `ml/eval/results/eval-baseline-2026-09-11.md`: dev critical misses 1/17, candidate 4/14 |
| **M4 — Safety hardening** | Crisis lexicon v1.2 and 87 output rules (`guardrails-v1.1`). Red-team 39/39 on the exposed set (20/39 before). Three crisis misses fixed. | `ml/eval/results/safety-hardening-2026-09-11.md`. These are regression results, not generalisation. |
| **M5 — Blind-evaluation infrastructure** | Author/reviewer workflow, assignment, adjudication, freeze, leakage checks and coverage plan | `ml/eval/BLIND_EVALUATION.md`. Locked count **0** because no human-authored samples exist yet. |
| **M6 — Dataset governance** | Registry, data cards, label firewall, archive safety and privacy processing of 5 external text datasets (Task 5) | `ml/data/`: all datasets `licence_pending` and quarantined |
| **M7 — Local model runtime** | MuRIL, XLM-R, Whisper Small (CTranslate2 FP16) and Silero VAD. Offline, lazy-loaded and firewalled from the product. VAD gating is enforced in code (Task 6/6A). | EXT-118, `ml/runtime/README.md` |
| **M8 — MuRIL shadow classifier** | Stage A domain adaptation, Stage C fictional-supervised 8-label head, Task 7B hardening | `ml/shadow/MODEL_CARD.md`: **rejected for product integration** (macro-F1 0.6747 < 0.70; deterministic micro-F1 0.91 vs 0.59 on dev). Local CLI demo only. |

**Test suite, measured 2026-09-24:** `pytest ml/tests` gives **827 passed, 2 failed**. Both failures are static-scan tests (`test_hardening.py::...test_no_external_corpus_network_or_model_access` and `test_model_runtime.py::...test_only_the_benchmark_references_the_bypass`). They walk into the untracked `ml/.venv/` and flag pip's own files. No product code is at fault.

---

## 4. Phases remaining

The phases are ordered by dependency. ⛔ marks a human-only step: no model or code agent may author or approve it. 🔑 marks an external-dependency decision that is needed first (§5).

### M9 — Hygiene and truthful status — **DONE 2026-09-24**

- Make the static-scan tests skip `.venv/`, `__pycache__/` and other untracked environments. Target: 829/829 green.
- Update stale status text. `ml/requirements.txt` and `ml/asr/*.py` docstrings still say faster-whisper and Silero are PROPOSED. Record that EXT-118 superseded them, and mark EXT-002 to EXT-005 in the decision table accordingly. The phase list in `ml/CLAUDE.md` should point here.
- **Exit:** full ML suite green, and no document contradicts `EXTERNAL_DECISIONS.md`.

### M10 — Language scope and victim-facing text (critical path; human-gated)

- 🔑 D-1: decide whether to add a fourth, regional language.
- ⛔ Write S0, S9, SX and SH for every shipped language. A counsellor or psychology faculty member reviews SX (HANDOVER §8.3). Mark each record `APPROVED` with the reviewer's name and the date. **This blocks voice output and the demo.** The current state is recorded in `docs/dialogue/FIXED_SCRIPTS_REVIEW.md`: every fixed script is unwritten.
- ⛔ Review the per-intent hi/en fallbacks, which are currently `DRAFT_UNREVIEWED`, and promote them to `APPROVED`.
- Hinglish register: make sure fallbacks and validator rules cover Roman-script Hinglish replies (AS-12).
- If a fourth language is approved, the following changes are needed. They are a contract change, so all four leads must agree.
  - Add the language to `SUPPORTED_LANGS` and the contract `lang` enum.
  - Extend the `nlp/langid.py` script detection.
  - Add crisis and detector lexicons, validator output rules and fallbacks in that language.
  - ⛔ A fluent human writes and reviews the fixtures in that language.
- Widen the lexicons to cover the anxiety and low-mood phrasing the PS names. Add it under the existing D5 label ("trauma-associated indicators") so no contract change is needed. Every addition gets negation tests and near-miss tests in every language.
- **Exit:** every `(state, lang)` fixed script is APPROVED, the validator red-team passes in every shipped language, and no language ships without its own fixtures.

### M11 — Voice pipeline in the product (ASR)

- 🔑 D-2: integrate `GatedTranscriber` into the backend. EXT-118 explicitly excludes backend integration, so this needs a new decision (proposed EXT-120).
- Wire the whole-utterance upload path (VF-11): 16 kHz mono → Silero VAD → Whisper on speech intervals only. An empty interval list gives `no_speech`, never a score.
- The language comes from the VF-01 selection. Whisper runs with `task="transcribe"` and never translates.
- Carry Whisper's segment log-probability into the uncertainty block, labelled uncalibrated. Low ASR confidence produces `needs_human` (invariant 6).
- Implement the audio-quality gate (`acoustics/quality.py`): SNR, speech duration and clipping, computed from VAD intervals and samples.
- 🔑 D-3: evaluation audio. Use Common Voice Hindi (EXT-002) and team-recorded **fictional** scripted audio. Recording hi, en and Hinglish in quiet and noisy conditions needs speaker consent.
- Measure WER and CER by language and condition, and M2 turn latency p50 and p95 on the demo laptop.
- **Exit:** a voice session completes end to end in Hindi and English, the WER/CER and latency tables are measured, and the crisis pre-check fires on transcribed speech.

### M12 — Speech emotion recognition, MuRIL text affect and acoustic D4 (PS: pauses, pitch, emotion AI)

**Scope decisions (project owner, 2026-09-24):**
- SER stays in the MVP. MuRIL is used where it fits.
- Text and speech are **separate models trained separately**, each picked for its own task and for the demo laptop:
  - Ryzen 7 7840HS
  - 32 GB RAM
  - RTX 4060 Laptop GPU with 8 GB VRAM (bf16 support verified)
- The owner runs every download, preprocessing and training step personally (see "Run points" below).

#### Model selection

**Audio branch: speech emotion recognition (SER)**

| Role | Model | Why | Laptop fit | Status |
|---|---|---|---|---|
| **Primary candidate** | **emotion2vec+ large** (`emotion2vec/emotion2vec_plus_large`; about 300M params per its card; `model.pt` 1.95 GB; FunASR Model License v1.1), **frozen**. Used two ways: (a) zero-shot, with its own 9-class head mapped to our 5 classes; (b) utterance embeddings with our own 5-class head on top. | Built for emotion: self-supervised pretraining on emotional speech, then trained on a large pseudo-labelled multilingual corpus. The authors report cross-lingual results. It is the strongest open SER representation at this size. | Inference only, no fine-tuning, so it fits 8 GB easily (VRAM measured at run R2b). Features are cached once. | **Conditional**: D-13, D-14, D-15 |
| **Alternate** (primary if emotion2vec is deferred) | `microsoft/wavlm-base-plus` (94M params, CC BY-SA 3.0; 377.6 MB), fine-tuned: CNN feature encoder frozen, top transformer layers trainable, learned weighted sum of layers, attentive-statistics pooling, 5-way head | The strongest general voice-tone features at this size (pretrained with denoising and speaker overlap). Transformers loads it natively, so no new package. | bf16 autocast, clips ≤4 s, batch 16. Expected to fit in 8 GB; measured at run R4. | **New download, D-10** |
| Challenger | Whisper Small encoder (already on disk), frozen; pooled layer features are cached, then a small MLP head | Multilingual and has seen Hindi, so it guards against WavLM's English-only pretraining. No download needed. | The encoder pads every clip to 30 s, so features are cached **once** during preprocessing and training runs on the cache only. | D-7 |
| Interpretable baseline | Prosody features (F0 mean/variability, energy, pause ratio, speech rate) plus logistic regression written in torch | AE-15 baseline, and shows what pitch and pauses alone can do | CPU, seconds | D-4 |
| Not chosen | WavLM Large (316M) | Fine-tuning it in 8 GB is tight, and there is no evidence of cross-lingual gain at this data size | — | — |
| Not chosen | Hugging Face SER checkpoints fine-tuned on IEMOCAP (e.g. SUPERB ER models) | IEMOCAP's licence is restrictive and it is English-only | — | — |
| Not chosen, but the fallback | XLS-R 300M | Only if WavLM fails the Hindi gate; it would need its own approval | — | — |

- **Training data:** RAVDESS speech (1,440 clips, 24 actors) and CREMA-D (7,442 clips, 91 actors).
- **Label space:** 5 shared classes, `affect:neutral|happy|sad|angry|fearful`. "Happy" is kept so that loud, high-arousal speech is not learned as distress. RAVDESS calm and surprised and CREMA-D disgust are dropped.
- **Splits:** actor-disjoint train, validation and test.
- **Cross-corpus check:** train on CREMA-D and test on RAVDESS.
- **Metric:** unweighted average recall (UAR), plus a confusion matrix.

**Text branch: MuRIL text affect (shadow)**

| Role | Model | Why | Laptop fit | Status |
|---|---|---|---|---|
| **Primary** | **MuRIL base**, full fine-tune, initialised from the Stage A domain-adapted encoder, with base MuRIL as an ablation | Its pretraining includes **transliterated (Roman-script) Indian text**, which is the best fit for Hindi plus Hinglish. It is already on disk. | Max length 128, batch 32, bf16. Expected well under 8 GB; measured at run R7. | D-9a |
| Challenger | XLM-R base (already on disk) | Standard multilingual comparison. EXT-118 allows it only for comparison, so training it is a new use. | Same | D-9a |
| Not chosen | IndicBERT v2, mDeBERTa-v3 | Each is a new download, and neither is clearly better for Roman-script Hinglish | — | — |

- **Data:**
  - EmoInHindi (hi, already local), mapped to the same 5 `affect:` classes.
  - A deterministic Devanagari→Roman transliterated copy for Hinglish. The transliteration uses a stdlib table, so no package is needed.
  - English: GoEmotions (optional, D-11). Without it, English falls back to the existing Dreaddit stress head, which is binary and separate.
- **Status:** shadow-only (D-9b not recommended).

**Training stack for both branches.** Everything **except emotion2vec** uses the existing private environment `sahay-ml-models` (EXT-118 pins), so **no new Python package is needed**:
- torch 2.11 (CUDA 12.8), transformers 5.17 and accelerate, with bf16 autocast.
- The repository's own loop in `ml/training/torchkit.py`, run offline with a socket block, like Stages A–C.
- WAV is read with the stdlib `wave` module. `torchaudio.load` needs TorchCodec, which is not installed, so it is avoided. Resampling uses `torchaudio.functional.resample` and pitch uses `detect_pitch_frequency`; both were verified working in the environment on 2026-09-24.
- Metrics use `ml/training/metrics.py`.

#### emotion2vec: how it is used, and when it is deferred

**Why it needs an isolated environment.** emotion2vec's official loader is **FunASR**, which brings a large dependency tree (audio I/O, config and tokenizer packages). Installing it into the approved `sahay-ml-models` environment could move the EXT-118 pins for torch, transformers or numpy. So it gets its own environment, `sahay-ser-e2v`, with its own pinned `requirements-e2v.txt`. The approved environment is never touched.

**Running it in the product.** In order of preference:
1. Export the frozen encoder and head to **ONNX** in the isolated environment. The product then runs it with `onnxruntime` 1.30, which is already pinned in EXT-118, and FunASR is not needed at runtime.
2. If the export fails, run emotion2vec as a **local sidecar process** in `sahay-ser-e2v`, listening on 127.0.0.1 only and called by the assessment runner. That adds process management, and the demo-risk section must record it.
3. If neither works reliably on the demo laptop, emotion2vec stays a **research and shadow** result, and the alternate feeds D4.

**Labels.** Its 9 classes map to our 5: angry, fearful, happy, neutral and sad map to themselves. Disgusted, surprised, other and unknown map to **abstain for that clip**. They are never folded into another class.

**Deferral triggers.** emotion2vec is deferred, and **WavLM Base+ fine-tuned becomes the primary**, if any of these hold:

| # | Trigger | Checked at |
|---|---|---|
| X1 | The weights' licence does not allow local, non-commercial research and demo use, or cannot be determined | D-15 lookup |
| X2 | No immutable revision or per-file hashes can be pinned | D-15 lookup, then R1 |
| X3 | FunASR cannot be installed with CUDA torch on Windows and Python 3.12 in the isolated environment | R1 |
| X4 | The model cannot load with networking blocked (it insists on a hub download at load time) | R1 load test |
| X5 | It loses to WavLM on the team-dev slice | R6b |

- **If X1–X4 hit:** WavLM Base+ is primary and the Whisper-encoder head is the challenger. Nothing else in the plan changes.
- **If WavLM is also unavailable (D-10 declined):** the Whisper-encoder head becomes primary. It needs no download, but it is expected to be weaker.
- **Last resort:** the prosody-only baseline.
- **If X5 hits:** emotion2vec is still reported in the comparison table; it just isn't the model that feeds D4.

#### Architecture at inference

```text
16 kHz mono ─► Silero VAD ─► speech intervals (empty → no_speech, no score)
   ├─► Whisper Small (CT2) ─► transcript ─► crisis pre-check (authoritative, unchanged)
   │                                   │                  └─► deterministic assess() (D1–D3, D5–D9)
   │                                   └─► MuRIL text-affect head ──────────────────── shadow display only
   ├─► prosody ─► deviation from this caller's in-session baseline ─┐
   └─► selected SER: emotion2vec+ (ONNX) · else WavLM · else Whisper-enc ┼─► D4 fusion (deterministic)
                                                                    ┘   · confidence-gated
                                                                        · SER ≤30% of D4 (≤3.6 SVI pts)
                                                                        · abstains on poor audio
   SER vs text-severity disagreement ─► SAFE-SIGNAL neutral verification card (AE-12)
```

#### Safety rules

These bind the code and are tested:

- SER and text affect never feed the crisis pre-check, routing, hard overrides or forced bands.
- The victim client never receives affect output (invariant 3; a new payload test covers it).
- On the console, affect output appears only inside the D4 breakdown, labelled "auxiliary signal, uncalibrated". It never names a feeling as a fact about the caller and never names a condition.
- Poor audio, less than 800 ms of speech, or low ASR confidence makes SER abstain.
- Affect labels stay in the `affect:` and source namespaces. The only route into D4 is the D-8 mapping.

#### Selection rule and promotion gate

Both are predeclared before any training (D-8).

- **Selection:** the candidate with the highest UAR on the **team-dev slice** wins; on a tie, the smaller model wins. The team-dev slice is 2 of the team speakers, and those speakers are never used in the gate. RAVDESS and CREMA-D validation UAR is reported too, but it **cannot pick between candidates**, because emotion2vec+ may have seen those corpora in training. The gate speakers are never used for selection.
- **emotion2vec contamination rule:** RAVDESS and CREMA-D numbers for emotion2vec+ are labelled `possibly_seen_in_pretraining` until its training-data list is checked (D-15). Only the team recordings are clean evidence for it.
- **Promotion gate:** SER may feed D4 in the product only if all of these hold:
  - (i) UAR over the 5 classes is at least **0.45** (chance 0.20) on the team's Hindi recordings;
  - (ii) the same holds on the team's English recordings;
  - (iii) no class has recall below 0.20;
  - (iv) negative control: on neutral team recordings, the SER contribution to D4 stays at or below Moderate.
- **If the gate fails:** SER is shown only as a shadow display, D4 uses prosody only, and the number is reported as it is.

#### Tasks and run points

**R = a run the owner does by hand.** At each R, work pauses and the owner gets the exact command, the expected outputs and what to report back. The owner runs it, checks the results, then resumes the session.

| Step | Work | Who | Needs |
|---|---|---|---|
| M12a ✅ | Prosody extractor (YIN-style F0 in numpy, energy, pauses from VAD intervals, speech rate, response latency), unit-tested on synthetic tones and gaps | ML lead | D-4 |
| M12b ✅ | Manifest entries (pinned revision and hashes) for emotion2vec+ large and WavLM Base+. Pinned `requirements-e2v.txt` for the isolated emotion2vec environment. Registry entries and data cards for RAVDESS and CREMA-D. Fetch and verify commands. | ML lead | D-5, D-10, D-13, D-14 |
| **R1** ✅ | ① `snapshot-crema-pointers`. ② Download RAVDESS (`ml.data.ser_audio fetch-ravdess`). ③ Fresh sparse clone of CREMA-D plus `git lfs pull --include "AudioWAV/*"`, then `verify-crema`. (The existing local copy is an extracted archive of pointers, not a git clone.) ④ `ml.ser.models fetch --model all`. ⑤ Create the isolated `sahay-ser-e2v` environment, install `ml/ser/requirements-e2v.txt`, `pip freeze` → lock. ⑥ `ml.ser.e2v_check`: offline load test with networking blocked. | **Owner** | Network |
| M12c ✅ | SER preprocessing code: `ml.data.ser_corpus build` (labels, CREMA-D demographics, actor-disjoint sex-stratified splits: RAVDESS 16/4/4 actors, CREMA-D 65/13/13); `ml.ser.preprocess audio` (16 kHz mono, Silero VAD trim, prosody and quality); `ml.ser.preprocess whisper` (frozen encoder, 13×768 per clip); `ml.ser.e2v_features` (1024-d embeddings plus 9 native scores). Smoke-tested on 6 real clips in a scratch root. | ML lead | — |
| **R2** | `ml.data.ser_corpus build`, then `ml.ser.preprocess audio`, then `ml.ser.preprocess whisper` (model environment) | **Owner** | — |
| **R2b** | `ml.ser.e2v_features` in `sahay-ser-e2v`: embeddings and zero-shot scores. The ONNX export moves to after selection (R6b), because it is needed only if emotion2vec wins. | **Owner** | D-13, D-14 |
| M12d ✅ | `ml.ser.train`: prosody logistic-regression baseline (speaker-normalised and pooled), Whisper-encoder head (learned layer weights), emotion2vec+ zero-shot (forced 5-class and abstaining 9→5), emotion2vec+ head, and WavLM Base+ fine-tune (CNN and lower 6 layers frozen, weighted layers, attentive statistics pooling, bf16). Best epoch by validation UAR; test scored once per corpus and sex; `--regime crema` adds cross-corpus. Smoke-tested on a 240-clip subset: every command ran with 0 network attempts; WavLM used 2.0 GB peak VRAM. | ML lead | D-7 |
| **R3** | Rerun R2 (the interval fix recovers 86 clips), then `baseline`, `whisper-head`, `e2v-zeroshot` and `e2v-head`, each for `--regime both` and `--regime crema`. All short, on cached features. | **Owner** | — |
| **R4** | `wavlm --regime both` (8 epochs, about 20–30 min), then `wavlm --regime crema`. Then `compare`. | **Owner** | — |
| M12e | Text-affect preprocessing code: EmoInHindi to `affect:` mapping, transliteration, optional GoEmotions | ML lead | D-9a, D-11 |
| **R5** | Run text-affect preprocessing | **Owner** | — |
| M12f | MuRIL and XLM-R text-affect training code | ML lead | D-9a |
| **R6** | Train MuRIL (Stage A init, then base init) and XLM-R | **Owner** | — |
| M12g | ⛔ Team recordings (see external help) | **Team** | Consent |
| **R6b** | Selection run on the team-dev slice (2 speakers) | **Owner** | M12g done |
| **R7** | One-shot gate evaluation of the selected SER model and text head on the remaining team speakers | **Owner** | M12g done |
| M12h | D4 fusion scorer, SAFE-SIGNAL, wiring into `assess()` for audio channels, and the payload no-leak test | ML lead | D-8, M11 |
| M12i | Model cards and the evaluation report. Every number states its evidence class. | ML lead | — |

#### R1 results (2026-09-26, verified locally with no network)

| Item | Result |
|---|---|
| RAVDESS | 208,468,073 bytes, md5 matches, archive-safe, 1,440 WAV files; sha256 `5d208e01…a40657`. Moved to `approved_for_training` (SER training and evaluation). |
| CREMA-D | Commit `1658cd34…b1dc`. All 7,442 AudioWAV files match their LFS pointer sha256 and size (605,899,936 bytes). Pointer-manifest sha256 `dc62d2be…449d2a`. Moved to `approved_for_training`. |
| WavLM Base+ | Every file hash verified (377.6 MB). |
| emotion2vec+ large | Every file hash verified (1.95 GB). Loads offline in `sahay-ser-e2v` with 0 network attempts: 164,048,921 parameters as loaded (the card says ~300M), 697 MiB peak VRAM, 1024-d embeddings, 0.44 s for a 3 s clip on the first call. The checkpoint's ninth label is `<unk>` (the card says "unknown"); the mapping now uses it. Missing-key warnings cover only the unused pretraining decoder. |
| `sahay-ser-e2v` | Installed after redirecting pip's temp and cache to D:, because C: had 4.3 GB free. Lock file: `ml/ser/requirements-e2v.lock` (89 packages: funasr 1.4.16, modelscope 1.40.1, torch 2.11.0+cu128, onnx 1.23.0, onnxruntime 1.30.0). |
| Deferral triggers | X1–X4 are clear. emotion2vec stays the primary candidate. X5 is decided at R6b. |

**M12c finding (2026-09-26):** the first smoke test showed that the YIN voicing rule, tuned on clean synthetic tones (CMND < 0.15, a fixed −50 dBFS floor), rejected most real voiced frames: loud frames of acted clips have median CMND minima of 0.23 to 0.36. Voicing now uses aperiodicity < 0.45 plus a clip-relative level floor (95th percentile − 35 dB, never below −70 dBFS). Voiced ratios on the smoke clips rose from 0.02–0.31 to 0.48–0.71, and pitch matches an independent tracker (torchaudio: 158 Hz against YIN's 150 Hz on the same clip).

#### External help needed (owner or team actions)

| # | What | Why it needs the owner or team | When |
|---|---|---|---|
| E1 | Set `SAHAY_MODELS_ROOT`, `SAHAY_DATASETS_ROOT` and `SAHAY_TRAINING_ROOT` in your shell. Suggested roots: `D:\Code\sides\sih-dataset\models`, `…\normalized` (or a new `…\audio`) and `…\training`. | Machine setup is the owner's call; the variables are not set yet. | Before R1 |
| E2 | Run the R1 downloads | Your preference. All sources are anonymous, with no account needed. | R1 |
| E3 | **Fallback if CREMA-D's GitHub LFS quota is exhausted** (a common failure for this repository): download `AudioWAV` from a mirror (e.g. Kaggle, which needs your login) into the same folder. `verify-crema` checks every file against the sha256 in the local LFS pointers, so any mirror is safe to use. | Needs your account and login | R1, only if the pull fails |
| E4 | (Optional) Request **IITKGP-SEHSC** (IIT Kharagpur Hindi acted emotional speech) from the institute. It would be the only in-language Hindi SER training data. | Needs an institutional request and a licence agreement | Anytime; only helps if it arrives before the freeze |
| E5 | ⛔ **Team recordings:** **at least 6 speakers** (2 for selection and 4 for the gate) (mixed gender if possible), each recording neutral, happy, sad, angry and fearful on about 10 neutral-content carrier sentences, in Hindi and English (plus Hinglish if possible), quiet and noisy, on a phone mic. Plus a signed consent form. The ML lead can draft the protocol, the consent form and the carrier sentences; the acting must be human. | Human voices; the gate needs in-domain evidence | Start now; needed by R7 |
| E6 | ⛔ About 100 **human-written** fictional Hinglish and Hindi sentences per affect class for the text-affect evaluation | The model developers must not write their own test set | Needed by R7 |

### M13 — Voice output (TTS and fixed audio)

- 🔑 D-6: pick a TTS source. Recommended: **human-recorded audio for the fixed scripts** (S0, S9, SX, SH), which is the most reliable and needs no model, plus an offline voice for generated turns. Candidates are the Windows built-in hi-IN and en-IN voices, which need checking for presence on the demo laptop, or an AI4Bharat Indic TTS model, which is a download with a GPU cost.
- Fill `ml/tts/presynth.py` assets under `runtime/audio/` (outside Git).
- If first-chunk TTS takes more than 500 ms, fall back to showing the text.
- **Exit:** every approved fixed script plays audio, and generated turns reach synthesis only after `validate()`.

### M14 — Detection quality and the evaluation table (headline numbers)

- ⛔ Fixture review: two human reviewers approve the crisis and immediate-danger fixtures, which unlocks a non-empty **locked** set.
- ⛔ Blind corpus: humans (not an LLM or code agent) write it to `coverage_plan_v1.json`. Then freeze it and evaluate once.
- Outstanding exposed failures, fixed only in the ways `ml/eval/CONTAMINATION.md` permits:
  - the missed dev critical event `DEV-EN-022`;
  - false escalations on quotation and attribution (`DEV-EN-011`, `DEV-HI-012`, `CAND-EN-012`, `CAND-HI-009`);
  - coercion recall on candidates (0.40).
- Report by language: M1 critical-event miss rate, M7 P/R/F1, false escalations, abstention coverage, M2 and M3 latency, and M6 WER.
- AE-15 interpretable baseline (P1; cut first if short of time): a stdlib logistic-regression comparison row. It adds no new package.
- **Exit:** the evaluation table ships with its evidence class stated on every number. If the locked or blind count is still 0, the table says so explicitly.

### M15 — Shadow model (optional; not recommended before the finale)

- Keep `experimental_shadow_classifier` as a research slide and CLI demo only.
- Task 8 integration would need a new decision covering invariant 8, the unresolved dataset licences, a richer human-reviewed corpus and passing the promotion gate. None of these is realistic before the finale.

### M16 — Freeze and judge defence

- Model cards for every ML component, a limitations document, the per-language red-team table and the SVI provisional-weights disclaimer.
- Run the demo rehearsal: Hindi voice → assessment → crisis interrupt → Critical alert → human decision → timeline.
- Tag the release. Claims about clinical validity, production readiness or untested languages stay prohibited.

### Critical path

```text
M9 ─► M10 (⛔ scripts + SX counsellor review) ─► M13 (fixed audio) ──────────────────────┐
  │     └─► M11 (🔑 D-2, D-3) ─► M12h D4 fusion (🔑 D-8) ──────────────────────────────────┼─► M14 ─► M16
  └─► M12a prosody ─► M12b ─► R1 ─► M12c ─► R2 ─► M12d ─► R3/R4 (SER) ─┐                   │
        M12e ─► R5 ─► M12f ─► R6 (MuRIL text affect, shadow) ─────────┼─► R7 gate ─► M12i ┘
        M12g ⛔ team recordings + E6 texts (start now) ────────────────┘
```

SER and text-affect work (M12a–g) needs no product wiring, so it runs **in parallel with M10 and M11**. Only M12h needs the M11 voice path. **R1–R7 are the owner's manual runs.** At each one, work pauses and the command is handed to the owner.

### Cut order if time runs short

1. The fourth regional language (fall back to hi + en + Hinglish)
2. The SAFE-SIGNAL card
3. The MuRIL text-affect branch (M12f)
4. Voice TTS for generated turns (text display only)
5. Moving SER from D4 input to shadow-only display (automatic if the promotion gate fails)

Never cut: the crisis pre-check, fixed-script review, abstention, the evaluation table (even when a count is 0), or the no-leakage tests. By owner decision (2026-09-24), SER itself stays in scope. If it fails its gate, it drops to shadow display; it is not removed.

---

## 5. Decisions needed

| ID | Decision | Unblocks | Recommended option | If declined |
|---|---|---|---|---|
| D-1 | Add a fourth, regional language? | M10 | Only if a **fluent human reviewer** is available on the team. Prefer a language with a distinct script (e.g. Bengali, Tamil, Telugu) so language ID stays deterministic. Marathi shares Devanagari with Hindi and would need lexical disambiguation. Start text-only. | Ship hi + en + Hinglish |
| D-2 | EXT-120: backend integration of `GatedTranscriber` | M11 | Approve for whole-utterance upload, local only | Voice stays a CLI demo; product is text-only |
| D-3 | EXT-002 Common Voice Hindi, plus consented team-recorded fictional audio | M11 WER table | Approve one pinned release, eval split only | WER from team recordings only; state the small n |
| D-4 | numpy and torchaudio for prosody and D4 feature extraction | M12a, M12c | Approve (already pinned in EXT-118; new use only) | D4 stays structurally absent and voice sessions abstain |
| D-5 | SER training data: RAVDESS `Audio_Speech_Actors_01-24.zip` (EXT-003) and CREMA-D `AudioWAV` via `git lfs` in the existing clone (EXT-104). CREMA-D is measured from the local LFS pointers: 7,442 files, 577.8 MB, each with a pinned sha256, under ODbL 1.0. | M12b | Approve both, for local training and evaluation only | SER trains on one corpus only, with no cross-corpus check; or SER is not built |
| D-7 | Use the pinned Whisper Small encoder as a frozen **challenger** SER feature extractor (EXT-118 scope is "transcribe only") | M12d | Approve (no download) | WavLM vs prosody baseline only |
| D-8 | SER → D4 mapping, the ≤30% cap, the selection rule and the promotion gate (5-class UAR ≥ 0.45 on the team's Hindi and English recordings, no class recall < 0.20, neutral negative control). Lead decision; the registry requires an approved mapping and validation study. | M12h | Approve as written | SER stays shadow-only; D4 is prosody-only |
| D-9a | Text-affect in **shadow**: fine-tune MuRIL (Stage A init plus a base-MuRIL ablation) and XLM-R base (training it is a new use beyond EXT-118's comparison-only scope) on EmoInHindi mapped to `affect:` classes, plus a transliterated Hinglish copy. Local demo only. | M12e–f | Approve shadow-only | MuRIL is used only as the existing shadow classifier |
| D-9b | MuRIL text-affect in the **product** D4. This needs a Task 8-style decision covering invariant 8, the `licence_pending` EmoInHindi and Dreaddit licences, privacy and rollback. | — | **Not recommended before the finale** | Stays shadow |
| D-10 | Download `microsoft/wavlm-base-plus` at revision `4c66d480…` (CC BY-SA 3.0, 377.6 MB). It is the **alternate** SER backbone, and becomes primary if emotion2vec is deferred. | M12b, R1 | Approve | The Whisper-encoder challenger becomes the primary |
| D-13 | Download **emotion2vec+ large** weights at a pinned revision. Licence, size, revision and training-data list are confirmed by D-15 first. | M12b, R1 | Approve, conditional on D-15 findings | WavLM Base+ becomes primary |
| D-14 | Isolated `sahay-ser-e2v` environment with **FunASR** plus its dependencies at exact pins. It is only for emotion2vec feature extraction and ONNX export, and never touches `sahay-ml-models`. | M12b, R1, R2b | Approve | Same as D-13 declined |
| D-15 | **Read-only metadata lookups** (Hugging Face model card and file listing for emotion2vec+ and WavLM Base+; PyPI metadata for FunASR and its dependencies), to confirm licence, revision, sizes, dependency pins and emotion2vec's training-data list. No file downloads. | D-10, D-13, D-14 | **Approve first**: the facts are reported back before D-10, D-13 and D-14 are final | Owner supplies these facts manually |
| D-11 | (Optional) GoEmotions English text-emotion dataset for the text-affect branch. Licence and size are checked on the source page before fetch. | M12e | Optional | English text affect uses the Dreaddit stress head only |
| D-12 | (Optional) Request IITKGP-SEHSC Hindi emotional speech (E4) | M12d | Optional, if the owner can obtain it | No in-language Hindi training audio; the gate relies on team recordings |
| D-6 | EXT-103 TTS source | M13 | Human-recorded fixed scripts plus a built-in OS voice for generated turns | Text display plus human-recorded fixed scripts |

Recording an approval means adding an entry to `docs/EXTERNAL_DECISIONS.md` in the same change, with the date, scope and exact item.
