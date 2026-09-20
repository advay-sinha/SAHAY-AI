---
name: dialogue-authoring
description: Use when writing or changing dialogue states, licensed questions, intents, fallback sentences or fixed scripts (S0, S9, SX) for the intake assistant.
---

# Authoring dialogue for the intake assistant

The people on the other side are victims of caste atrocities, sexual violence and bereavement. Every sentence is written for the worst plausible state of the listener, not the average one.

## Structure

The assistant is a **bounded intake instrument**, not a chatbot. A deterministic state machine chooses one approved intent; the LLM phrases it; a validator checks the output before synthesis. If the validator rejects it, the intent's pre-written fallback is spoken instead.

Every intent needs: an id, the state it belongs to, the single licensed question (or none), the slots it fills, and a pre-written fallback sentence in **both Hindi and English**. No intent ships without its fallback — the system must run with the LLM off.

## Writing rules

- **One sentence.** Plain words. No compound questions.
- **One question per turn**, and only the question the state licenses.
- **Acknowledge without interpreting.** "I've noted that" — not "that must have been terrifying".
- **Never ask a victim "why".** Not why they went there, why they waited, why they didn't complain.
- **Never ask for detail** about an assault, an injury, or a death. The narrative state captures what the person volunteers; nothing probes for more.
- **No advice, no promises, no diagnosis.** Not legal, not medical, not psychological, not procedural predictions.
- **Banned comfort language**, both languages: calm down, don't worry, be strong, I understand how you feel, everything will be fine, at least…
- **Skip states already answered** by the free narrative. Asking what was just said is the fastest way to lose trust.
- **Hindi first, then English.** Write the Hindi natively; do not translate an English sentence into stiff Hindi. Hinglish input must be understood, and the reply matches the user's register.

## Fixed scripts

S0 (opening), S9 (closing) and SX (crisis) are **fixed text, pre-recorded, never model-generated**.

- **S0** must: identify the assistant as an AI, state that a human officer reviews everything, state the right to a human at any time, and invite the person to speak in their own words.
- **S9** must: confirm the account is recorded, give the reference number, state what happens next and roughly when. It must not promise an outcome.
- **SX** must: acknowledge, state plainly that a person will speak with them now, and ask them to stay. Nothing else. No advice, no assessment, no questions.

**Have a counsellor or psychology faculty member read SX before Day 8, and name that review in the deck.**

## Process

Any change here updates `docs/dialogue/STATES.md` in the same commit, is labelled `type:dialogue`, and requires two reviewers including the `dialogue-safety-reviewer` agent. It changes what the system says to a victim.
