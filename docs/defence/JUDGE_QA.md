# Judge questions — short, honest answers

Every answer points to where the evidence is. Numbers come from `NUMBERS.md` and the evaluation table; none is typed from memory.

**Does the AI decide who gets help?**
No.
- A deterministic state machine picks every question, and a rule-based crisis pre-check runs first on every turn.
- A human helpline executive decides every action. AI recommendations and human decisions are stored in separate tables.
- The AI output is a triage aid (the SVI) with visible evidence, confidence and provisional weights.

**What happens if someone says they want to end their life?**
- The synchronous crisis pre-check forces the fixed crisis script, Critical priority and an immediate human takeover, and intake never resumes automatically.
- This is tested end to end. On the exposed fixtures the pre-check found 9 of 9 crisis cases on dev and 8 of 9 on candidates.

**Can the language model say something harmful?**
- Every generated sentence goes through the output validator before it can be spoken; on failure the pre-written text is used.
- Red-team: 39 of 39 cases blocked, across English, Hindi and Hinglish. That's regression evidence on published cases (`RED_TEAM.md`).
- The demo runs with the language model off (`LLM_PROVIDER=mock`).

**Does the victim see their risk score?**
- No. The server strips the SVI, band, dimensions, emotion, confidence and alerts from everything the victim app receives, and tests enforce it (M8).
- The new audio endpoint returns audio only.

**How accurate is it?**
- On published development fixtures, the rules miss 0 of 17 critical events (dev) and 1 of 14 (candidates).
- Those fixtures were seen during development, so we call this regression performance.
- Independent accuracy needs the locked set and the blind corpus, which need human reviewers and authors. Both are pending, and we say so on every slide.

**Why not just use a big model?**
We trained one, as a shadow only.
- MuRIL with borrowed labels reaches AUROC 0.99 on Reddit crisis text.
- But on SAHAY's own cases it trails the rules: micro F1 0.60 against 0.93.
- It also fires on harmless sentences like "I won't be here tomorrow, I'm visiting my sister".
- A simple logistic model did worse still.

The numbers justify keeping rules authoritative and the model as a second opinion.

**What about Hindi?**
- The crisis pre-check, detectors and validator cover Hindi and Hinglish, and the speech recogniser accepts Hindi.
- Hindi word error rate is not measured yet; it needs recordings.
- There is no Hindi voice on the demo laptop, so Hindi replies are shown as text rather than read out in the wrong voice.

**Is voice emotion used to judge people?**
- Speech emotion is shadow-only and off in the score.
- Voice distress (D4) compares a caller only with their own earlier turns, and only upward changes count, so a calm voice is never read as "fine".
- A calm voice with crisis words is still Critical.

**How fast is it?**
- On the laptop, a voice turn takes 581 ms at the 95th percentile on the server, most of it speech recognition.
- Adding the phone's 700 ms end-of-speech wait gives about 1.3 s, against a 3 s budget.
- Phone and Wi-Fi timings are not measured yet.

**Is it clinically validated?**
No, and we don't claim it. See `LIMITATIONS.md`.
