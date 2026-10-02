---
title: SAHAY-AI models
emoji: 🛡️
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: 6.29.0
python_version: "3.12"
app_file: app.py
pinned: false
license: apache-2.0
short_description: Guardrailed phrasing and advisory signals (prototype)
---

Model service for the SAHAY-AI hosted tester demo. **Prototype: fictional test data only.**

Two API endpoints, both refusing to answer without the shared key (`SAHAY_SPACE_KEY` secret):

- `phrase(source, register, key)`: rewords one approved English sentence (Qwen3-4B-Instruct-2507).
  The SAHAY backend validates every output and checks its meaning before anyone sees it.
- `signals(texts, key)`: an experimental classifier's advisory, uncalibrated reading for
  officers (crisis/self-harm, coercion, legal urgency). Never decisive.

The classifier weights live in a private model repository (`SAHAY_SIGNALS_REPO`, read with the
`HF_TOKEN` secret). Inputs are never logged.
