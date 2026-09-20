---
description: Run the 90-second demo path end to end and report exactly where it breaks
allowed-tools: Read, Bash, Glob, Grep
---

# Demo rehearsal

Run every beat of the demo. Report **PASS / FAIL / CANNOT VERIFY** with timings.

1. Consent screen shows AI disclosure and the right to a human; accept works.
2. Assistant greets in Hindi, identifies itself as AI. Time to first audio.
3. Victim narrative → assistant acknowledges and asks the licensed safety question. **Turn latency measured.**
4. Console: transcript streams both sides; structured record fills; dimensions and SVI update; evidence spans link to utterances.
5. Scripted crisis line → intake stops → fixed crisis script plays → band Critical → alert at top of queue with audible cue.
6. Executive opens the packet: transcript, assessment, evidence, confidence, recommendations with policy citations.
7. Confirm two recommendations, reject one with a reason. Audit rows written to `decisions_human`.
8. Takeover: assistant muted, victim informed in Hindi.
9. Victim timeline shows "officer assigned" — and contains **no** assessment field. Verify this by inspecting the payload, not the UI.
10. LLM-off mode: repeat beats 2–5 with the mock adapter. Must still complete.

Then report: total runtime, the slowest turn, every failure with its cause, and whether the fallback paths (whole-utterance upload, pre-recorded scripts, mock LLM) are working. If any beat fails, that is the top priority regardless of what else is planned today.
