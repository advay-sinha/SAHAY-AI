---
name: external-dependency-protocol
description: Use whenever work requires a new package, model, dataset, API, credential, service or any network fetch. Defines the mandatory ask-first procedure and the fallback behaviour if the user declines.
---

# External dependency protocol

Nothing external enters this codebase without the user's explicit decision. This is not bureaucracy — in a 14-day sprint an unplanned 4 GB model download, a paid API, or a GPU-only dependency can cost a day, and on demo day an external call can cost the demo.

## When this triggers

- A package not already in `requirements.txt` / `requirements-ci.txt` / `package.json`
- A model, checkpoint, tokenizer, voice or embedding to download
- A dataset (RAVDESS, CREMA-D, Common Voice, Kathbath, IEMOCAP, DAIC-WOZ, anything)
- Any external API — LLM, speech, translation, telephony, messaging, maps
- An environment variable, API key, credential, endpoint URL or secret
- A new database, cache, queue, object store or container image
- Any network fetch at build time or run time
- A native mobile module or a new device permission

If you are unsure whether it triggers, it triggers.

## The ask

Post exactly this and then **stop**:

```
EXTERNAL DEPENDENCY — decision needed

What I need:      <name and version>
Why:              <the specific task it unblocks>
Where it's used:  <file and function>
Licence / cost:   <MIT / Apache-2.0 / paid / unknown>
Size / runtime:   <download size, RAM, CPU or GPU, cold-start time>
Demo-day risk:    <works offline? needs a key? rate limited?>
If you say no:    <the fallback I will implement instead>

Proceed?
```

## While waiting

- Do not install. Do not download. Do not add the key. Do not `pip install` "just to test".
- Do write the interface, the docstring and the tests around it, with `raise NotImplementedError` and a comment naming the pending decision.
- Do continue with unrelated work.

## If the user declines

Implement the stated fallback and record it in the file:

```python
# EXTERNAL DEPENDENCY DECLINED (2026-xx-xx): <thing>
# Fallback in use: <what this does instead>
# Consequence: <what is degraded>
```

Never silently substitute a different external thing for the declined one. That is the same decision, taken without asking.

## Standing rules for this project

| Category | Default |
|---|---|
| Speech (ASR, TTS), acoustics, classifiers | **Self-hosted only.** No cloud speech APIs. Victim audio never leaves the machine — this is the privacy claim in the pitch |
| Telephony, SMS, WhatsApp, push | **Not in the MVP.** `telephony_adapter.py` stays a documented stub |
| LLM | Allowed, behind `llm_adapter.py`, with a mock that returns per-intent fallback text. The system must run with it disabled |
| Datasets | Ask every time, including open ones. Licence and size both matter |
| Anything needing a GPU at demo time | Refuse and say why. The demo runs on CPU |

## Production-time asks

The same protocol applies during deployment: hosting, domains, TLS certificates, storage buckets, monitoring, or connecting a real service. Ask before provisioning anything that costs money or holds data.
