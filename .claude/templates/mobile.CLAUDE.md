# mobile/ — Team C (Victim App)

> Root `CLAUDE.md` governs this directory. Its STOP RULES override anything here.
> Subagent: `mobile-engineer`.

## What this directory owns

The React Native (Expo) app a victim of a caste atrocity uses at the worst moment of their life: consent, voice conversation with the assistant, text chat, and their request timeline.

## THE RULE THAT OUTRANKS EVERY OTHER DECISION HERE

**This app never displays the SVI, the risk band, the nine dimensions, detected emotions, alerts, or any part of the assessment.**

Telling a distressed person that a machine has rated them "Critical" is harmful, and any judge from the mental-health stakeholder group will say so. The score exists for the executive. This app shows: *you are heard, this is your reference number, this is what happens next.*

There is a test asserting `svi`, `band` and `dimension` do not appear in `mobile/src/`. Do not remove it.

## Layout

```
src/screens/     Language · Consent · Home · Talk · Chat · MyRequests · Offline · Error
src/audio/       capture.ts (16 kHz mono PCM16) · playback.ts (TTS queue) · bargein.ts
src/net/         socket.ts (reconnect + resume) · queue.ts (offline buffer)
src/i18n/        hi.json · en.json — every user-visible string
src/components/  TalkToPersonButton (persistent) · SpeakingIndicator · TimelineList
```

## Phases

**P0 — Day 1 — the highest-uncertainty task in the whole project**
Get an Expo **development build** (not Expo Go) running on a **physical phone** with microphone *and* speaker access. Two people on this, today. If it is not working by end of Day 2, escalate at the checkpoint — do not quietly keep fighting it. The pre-agreed fallback is a mobile-optimised web app, decided at the Day 4 gate.

**P1 — Days 2–4 → Day 4 gate**
- Language, Consent (with AI disclosure), Home screens
- 16 kHz mono PCM capture; whole-utterance upload path **first**, then chunked streaming
- TTS playback queue; barge-in stopping playback on local VAD
- Persistent "Talk to a person" control
- Chat screen; Hindi and English strings complete

**P2 — Days 5–8 → Day 8 gate**
- Streaming both ways; reconnection with resume; offline frame and message queue
- Chat wired to the same dialogue machine
- Consent-declined mode (no analysis, still routes to a human)
- Takeover notification — the victim hears, in their language, that a person has joined
- MyRequests timeline

**P3 — Days 9–11** — APK for judges; permission and battery edge cases; accessibility pass (contrast, target size, font scaling); calm error and offline states; latency tuning with Team A.

**P4 — Days 12–13** — freeze; APK tested on a phone belonging to someone outside the team.

## Design constraints

Assume a distressed user, on a cheap phone, on a poor network, possibly not literate in English, possibly being overheard.

- Large targets, high contrast, minimal words. No gestures to discover, no clever interactions.
- "Talk to a person" on every conversational screen. One tap, immediate, never in a menu.
- AI disclosure on the consent screen and visible in the interface thereafter.
- Barge-in: user speech stops playback immediately and becomes the next turn.
- Never impose a time limit on a turn.
- Errors and offline states are calm, explicit, and in the user's language. Never an English stack trace.
- Chat must work when the network is too weak for audio — that is an accessibility feature, not a fallback.

## Checks before you call anything done

- [ ] Runs on a **physical phone**, not only a simulator
- [ ] No hardcoded user-visible English — everything through `i18n/`
- [ ] No assessment field imported, requested or rendered anywhere
- [ ] Offline: capture continues, queue flushes on reconnect
- [ ] Barge-in verified by hand, with a real voice
- [ ] Consent-declined path still reaches a human

## Never

- Add an Expo module, native dependency, permission or package without asking (STOP RULE 2.1). Native audio modules are a known time sink — flag the risk with the request
- Display any assessment output
- Bury or delay the request for a human
