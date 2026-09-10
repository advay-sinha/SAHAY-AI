# Datasets, Models and Services

This is the decision source for external assets. `docs/EXTERNAL_DECISIONS.md` records approvals. Claude must not infer approval from this plan.

## Download now — recommended initial batch

### 1. Mozilla Common Voice Hindi

- Source: `https://datacollective.mozillafoundation.org/`.
- Purpose: Hindi ASR WER/CER evaluation, clean versus noisy slices.
- Scope: one named release; Hindi validated/dev/test material only. Do not download every language.
- Licence: confirm the exact release terms at download time and record them; Common Voice Hindi is normally offered under CC0.
- Storage: `<DATA_ROOT>/raw/common_voice_hi/<release>/`.
- Git: commit only release metadata, checksums, attribution and derived manifests.
- Use: evaluation first. Do not claim that Common Voice represents distressed NHAA callers.

### 2. RAVDESS audio speech

- Source: `https://zenodo.org/records/1188976`.
- Exact file: `Audio_Speech_Actors_01-24.zip` only, approximately 208.5 MB and 1,440 clips.
- Purpose: auxiliary speech-emotion baseline and acoustic pipeline smoke test.
- Licence: CC BY-NC-SA 4.0; attribution required; reassess before any commercial use.
- Storage: `<DATA_ROOT>/raw/ravdess/`.
- Do not download song or video archives.
- Limitation: English, acted emotion and not evidence of clinical or trauma validity.

### 3. Project scenario corpus — created locally

- No external download.
- Create 10 fictional scenarios across Hindi, English and Hinglish, each in clean and noisy conditions: 60 complete sessions.
- Include immediate danger, crisis, ongoing threat, medical urgency, boycott/displacement, coercion, legal status, low-risk request, negated/quoted crisis language and human request.
- Never record real victim accounts.
- Keep audio outside Git; commit the manifest and anonymised labels only.
- High-consequence labels require two annotators and adjudication.

### 4. faster-whisper small model

- Source: `https://huggingface.co/Systran/faster-whisper-small`; implementation: `https://github.com/SYSTRAN/faster-whisper`.
- Purpose: local Hindi/English/Hinglish ASR using CPU int8.
- Storage: `<DATA_ROOT>/models/asr/faster-whisper-small/`.
- Runtime: benchmark on the actual demo laptop; record p50/p95 latency and WER.
- This is a model download, not a dataset, and needs separate approval.

### 5. Silero VAD

- Source: `https://github.com/snakers4/silero-vad`.
- Purpose: local endpoint detection and barge-in support.
- Storage: `<DATA_ROOT>/models/vad/silero/`.
- Tune silence threshold on the project scenario corpus.
- This model needs separate approval.

## Do not download yet

| Item | Why deferred | Reconsider |
|---|---|---|
| CREMA-D AudioWAV | Useful but larger duplicate auxiliary SER source | P2 after the voice gate |
| Dreaddit | English Reddit domain differs from helpline speech | P2 baseline only |
| GoEmotions | General emotions; weak fit for the target detectors | Only for an explicit experiment |
| MUCS / GramVaani / Kathbath corpora | Access, size and licence must be verified; not needed for first gate | P3 ASR comparison |
| IEMOCAP / DAIC-WOZ | Licence/access friction | Post-MVP research |
| 22-language corpora | MVP supports Hindi, English and Hinglish input | Post-MVP |
| Indic Parler-TTS or Piper voice | Hindi quality/latency must be tested before selection | After fixed prompt audio works |
| MuRIL / IndicBERT / XLM-R | Detector schemas and labelled corpus must be frozen first | P2 |
| Claude or another LLM API | Complete workflow must work with mock adapter | P2 optional |
| Official policy PDFs | Final source list and citations require approval | P2 RAG work |

## Services for the local MVP

No external runtime service is required initially.

| Capability | Initial implementation |
|---|---|
| Database | SQLite local file through SQLAlchemy |
| Assessment jobs | Local background runner |
| Retrieval | Local deterministic/keyword index initially |
| LLM | Mock adapter |
| Audio | Local filesystem |
| Authentication | Local JWT/session implementation |
| WebSocket | FastAPI process |

## Deferred services and infrastructure

Do not set up Docker, GitHub Actions, PostgreSQL, Redis, RQ, pgvector, cloud hosting, telephony, SMS, WhatsApp or push notifications without a new external-dependency decision.

## Dataset directory

Keep data outside the Git repository:

```text
D:/SAHAY-AI/sahay-ai-data/
├── raw/
├── processed/
├── own-corpus/
├── manifests/
├── checksums/
└── models/
```

## Processing contract

Convert evaluation audio to 16 kHz, mono, signed PCM16 WAV when FFmpeg becomes approved and installed. Preserve originals. Split model data by speaker. Keep a locked scenario test set separate from training data. Record source, release, licence, checksum, purpose and limitations for every dataset.
