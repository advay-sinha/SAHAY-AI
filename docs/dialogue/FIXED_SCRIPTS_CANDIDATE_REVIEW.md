# Fixed scripts — bilingual candidate review packet

Status: **PENDING HUMAN REVIEW — NOT APPROVED, NOT ACTIVE**

This packet contains candidate victim-facing wording authorized by Controlled
MVP Task 5C. It is documentation for human review only. It does not populate
`ml/dialogue/scripts/fixed_scripts.py`, create audio, change runtime behaviour,
or satisfy the approval gate in `FIXED_SCRIPTS_REVIEW.md`.

All reviewer names, reviewer qualifications, decisions, dates, and comments
are intentionally blank. A required review capacity names the kind of review
needed; it is not evidence that a reviewer has performed it.

## Hash and review-invalidation rule

Each language hash is lowercase SHA-256 of the UTF-8 bytes of the exact text in
its wording block, excluding the Markdown fence and excluding any trailing
newline. The `{reference_no}` token is included literally in the S9 hashes.

**Any change to any character in proposed wording invalidates every prior
review of that language version.** The changed wording must receive a new hash,
return to `PENDING`, and be reviewed again by every required reviewer. A review
applies only to the state, language, exact wording, and hash recorded here.

## Shared boundaries

- The scripts are deterministic and non-rephrasable. They remain outside the
  LLM, MuRIL, Task 7B, Whisper, D4, assessment, and generated-TTS paths.
- No script may disclose SVI, band, confidence, alert, emotion, priority,
  recommendation, or any other internal assessment information.
- No script diagnoses, blames, judges credibility, guarantees safety, promises
  an outcome or response time, or makes a jurisdiction-specific claim.
- The Hindi candidates use formal Hindi and no Hinglish. Native-speaker review
  is still required; this packet does not assert linguistic approval.
- A fixed script remains unavailable unless its exact text and all required
  reviews are later activated through a separate implementation task.
- Text readiness and audio readiness are independent. There are no approved or
  verified audio assets for these candidates.

---

## S0 — opening

**Script identifier and state:** `S0:en`, `S0:hi`; `S0 OPENING`

**Review status:** `PENDING`

### Exact proposed English wording

```text
I am the SAHAY automated AI assistant. What you share may be reviewed by a human officer. You can ask for human help at any time. Please describe what happened in your own words.
```

SHA-256: `8296a38a8dde4a9cc1480b82cdc57ec97f3b3421acba49875aebbab38d8e7de2`

### Exact proposed Hindi wording

```text
मैं सहाय स्वचालित कृत्रिम बुद्धिमत्ता सहायक हूँ। आप जो साझा करते हैं, उसकी समीक्षा एक मानव अधिकारी द्वारा की जा सकती है। आप किसी भी समय किसी व्यक्ति से सहायता माँग सकते हैं। कृपया अपने शब्दों में बताइए कि क्या हुआ।
```

SHA-256: `8bf8bed902cd53a2dae73c31cb1e31422049db92f6e3e08f4ae585e9b2efedc5`

### Literal English back-translation of the Hindi candidate

“I am the SAHAY automated artificial-intelligence assistant. What you share
may be reviewed by a human officer. You may ask for help from a person at any
time. Please tell, in your own words, what happened.”

### Trigger and suppression conditions

- Trigger only when a valid session enters S0, the consent disclosure was
  presented, consent is not declined, and no crisis or human-support path has
  precedence.
- Suppress for declined consent, a human request, crisis, SH, SX, verified
  takeover, unsupported language, missing approval metadata, or hash mismatch.
- S0 must not replace or repeat the consent recording disclosure.

### Sentence-by-sentence safety rationale

1. Identifies the owner-selected system and discloses automated AI without
   claiming to be a government officer.
2. Describes possible human review without claiming continuous monitoring.
3. Preserves access to human assistance throughout intake.
4. Invites a free narrative as an instruction, not a leading question.

### Claims deliberately avoided

Recording language; NHAA or 14566; immediate monitoring; officer assignment or
presence; confidentiality or safety guarantees; assessments; outcomes,
response times, legal conclusions, and credibility judgments.

### Dynamic fields

None.

### Required reviewers and unresolved fields

| Required review capacity | Reviewer name | Reviewer role/qualification | Decision | Date | Comments |
|---|---|---|---|---|---|
| Project owner |  |  |  |  |  |
| Legal review |  |  |  |  |  |
| Team A / dialogue owner |  |  |  |  |  |
| Dialogue reviewer 1 |  |  |  |  |  |
| Dialogue reviewer 2 / safety review |  |  |  |  |  |
| Native Hindi-language reviewer |  |  |  |  |  |

---

## SH — human-support transition

**Script identifier and state:** `SH:en`, `SH:hi`; `SH HUMAN HANDOFF`

**Review status:** `PENDING`

### Exact proposed English wording

```text
The AI assistant will not continue this conversation. Your session has been routed for human support. No officer has joined this session yet. Please stay in this session if you are able.
```

SHA-256: `d883bbddf6975370f68a6529b745a459c1f3fd033160c3a09ac22fa789c981c9`

### Exact proposed Hindi wording

```text
कृत्रिम बुद्धिमत्ता सहायक अब यह बातचीत जारी नहीं रखेगा। आपके सत्र को मानव सहायता के लिए भेज दिया गया है। अभी कोई अधिकारी इस सत्र में शामिल नहीं हुआ है। यदि आप सक्षम हों, तो कृपया इस सत्र में बने रहें।
```

SHA-256: `da39efc28d4f22c2c967c1f383bb2b8bb7dabdc158f574f91ea95010cda35de8`

### Literal English back-translation of the Hindi candidate

“The artificial-intelligence assistant will no longer continue this
conversation. Your session has been sent for human assistance. No officer has
yet joined this session. If you are able, please remain in this session.”

### Trigger and suppression conditions

- Trigger when the session atomically enters SH through an explicit human
  request, a non-crisis escalation, or declined consent, while AI is muted and
  `human_joined` is false.
- Suppress when crisis precedence applies, takeover is verified,
  `human_joined` is true, the session ended, routing failed, approval metadata
  is incomplete, or the hash differs.
- Actual presence must use a separate validated takeover/officer event.

One generic candidate covers every pre-takeover SH entry path because it names
the route rather than its reason and explicitly says no officer has joined. It
does not cover verified human presence.

### Sentence-by-sentence safety rationale

1. Makes AI muting explicit without claiming the conversation ended.
2. Describes the common human-support route for request, escalation, and
   declined-consent paths.
3. Prevents a false impression that transfer is complete.
4. Conditionally asks the person to remain without promising a wait duration.

### Claims deliberately avoided

Completed transfer; officer presence or assignment; wait duration; response or
outcome; escalation reason; consent inference; assessment data; advice,
diagnosis, safety guarantees, phone numbers, URLs, and jurisdictional claims.

### Dynamic fields

None. A verified-takeover notification requires separate frozen wording and
review and must not be simulated through SH.

### Required reviewers and unresolved fields

| Required review capacity | Reviewer name | Reviewer role/qualification | Decision | Date | Comments |
|---|---|---|---|---|---|
| Project owner |  |  |  |  |  |
| Legal review |  |  |  |  |  |
| Team A / dialogue owner |  |  |  |  |  |
| Team C / takeover-event verification |  |  |  |  |  |
| Dialogue reviewer 1 |  |  |  |  |  |
| Dialogue reviewer 2 / safety review |  |  |  |  |  |
| Native Hindi-language reviewer |  |  |  |  |  |

---

## SX — crisis interruption

**Script identifier and state:** `SX:en`, `SX:hi`; `SX CRISIS INTERRUPT`

**Review status:** `PENDING`

### Exact proposed English wording

```text
Thank you for telling me. Urgent human support has been requested. If you can, stay away from immediate danger and remain near a person you trust. Please stay in this session.
```

SHA-256: `2e8aad0e51696f6789b7ba57db3b34483c7a812029e55a460f1d6933ed3ad8c5`

### Exact proposed Hindi wording

```text
यह बताने के लिए धन्यवाद। तत्काल मानव सहायता का अनुरोध किया गया है। यदि संभव हो, तो तत्काल खतरे से दूर रहें और किसी भरोसेमंद व्यक्ति के पास रहें। कृपया इस सत्र में बने रहें।
```

SHA-256: `68a40e233eb01a1a12592c559487c9520f8f70fb402e6233c5917ec09f473b9b`

### Literal English back-translation of the Hindi candidate

“Thank you for telling this. Urgent human assistance has been requested. If
possible, stay away from immediate danger and remain near a trusted person.
Please remain in this session.”

### Trigger and suppression conditions

- Trigger only when the synchronous deterministic crisis pre-check fires from
  an active state. SX retains precedence, existing Critical routing, takeover
  request, and no-resumption behaviour.
- Suppress when no crisis pre-check fired; assessment, band, confidence,
  emotion, or model output must never trigger it.
- Suppress after session end or verified takeover. Do not automatically repeat
  while already in SX without a separately reviewed held-line policy.
- Suppress for incomplete approval metadata or a hash mismatch.

The wording is neutral about whether danger concerns the speaker or another
person and does not identify what the system matched.

### Sentence-by-sentence safety rationale

1. Acknowledges disclosure without agreeing with facts, judging credibility,
   minimizing, diagnosing, or naming the danger source.
2. States only the committed urgent-support request, not that support arrived.
3. Gives brief conditional general guidance without medical, legal, or
   jurisdiction-specific direction and without guaranteeing safety.
4. Asks the person to remain connected without promising response time.

### Claims deliberately avoided

Detection, emotion, diagnosis, who is in danger, current safety, officer
presence, guaranteed help, response time, outcome, emergency number, NHAA,
14566, URL, legal or medical advice, and assessment information.

### Dynamic fields

None.

### Required reviewers and unresolved fields

| Required review capacity | Reviewer name | Reviewer role/qualification | Decision | Date | Comments |
|---|---|---|---|---|---|
| Named counsellor or psychology faculty reviewer |  |  |  |  |  |
| Project owner |  |  |  |  |  |
| Legal review |  |  |  |  |  |
| Team A / dialogue owner |  |  |  |  |  |
| Team B / takeover availability verification |  |  |  |  |  |
| Team C / held-session behaviour verification |  |  |  |  |  |
| Dialogue reviewer 1 |  |  |  |  |  |
| Dialogue reviewer 2 / safety review |  |  |  |  |  |
| Native Hindi crisis-language reviewer |  |  |  |  |  |

---

## S9 — closing

**Script identifier and state:** `S9:en`, `S9:hi`; `S9 CLOSING`

**Review status:** `PENDING`

### Exact proposed English wording

```text
What you shared has been recorded. Your session reference number is {reference_no}. Authorized human officers can review your request. You can ask for human help if you need it.
```

SHA-256: `dc3094445f87503a1cd1541d9cf427630ea45a25463ccb94838bf50a6fee1349`

### Exact proposed Hindi wording

```text
आपने जो साझा किया है, उसे दर्ज कर लिया गया है। आपके सत्र की संदर्भ संख्या {reference_no} है। अधिकृत मानव अधिकारी आपके अनुरोध की समीक्षा कर सकते हैं। आवश्यकता होने पर आप किसी व्यक्ति से सहायता माँग सकते हैं।
```

SHA-256: `fccc6bfeb3f0ffc11bf1c314ce4ac13608a382d5702c7f8866a8e75141b4509a`

### Literal English back-translation of the Hindi candidate

“What you shared has been recorded. Your session's reference number is
`{reference_no}`. Authorized human officers may review your request. If needed,
you may ask for help from a person.”

### Trigger and suppression conditions

- Trigger only after session-end persistence succeeds and the server supplies
  the persisted reference for that same authenticated session.
- Suppress if the session is not ended, the reference is missing, invalid,
  user-supplied, or belongs to another session, or if SX, SH, or verified
  takeover requires a different closing policy.
- Suppress for incomplete approval metadata or a hash mismatch.

### Sentence-by-sentence safety rationale

1. Confirms only the persistence action supported by the application.
2. Presents the validated victim reference without treating it as a score,
   queue position, or promise.
3. Describes supported review capability without claiming assignment or action.
4. Preserves human assistance without implying a callback.

### Claims deliberately avoided

Callback or response time; assigned officer; guaranteed review or action;
arrest, compensation, legal result, safety, assessment outcome; phone numbers,
URLs, and jurisdiction-specific process claims.

### Dynamic fields and strict templating boundary

- The sole token is the exact literal `{reference_no}`. No other placeholder,
  expression, object lookup, or arbitrary substitution is permitted.
- The value must be the persisted case reference for the authenticated session,
  never victim text, model output, query input, or client substitution.
- Current source generates `SAH-` plus exactly six uppercase hexadecimal
  characters (`^SAH-[0-9A-F]{6}$`). A later contract task must reconcile this
  with the different example in `CONTRACTS.md` before activation.
- A typed operation must validate format, ownership, equality with persisted
  data, and exactly one token occurrence. Failure suppresses S9 and records a
  non-sensitive audit reason.
- The dynamic reference is displayed or rendered separately and is excluded
  from prerecorded audio.

### Required reviewers and unresolved fields

| Required review capacity | Reviewer name | Reviewer role/qualification | Decision | Date | Comments |
|---|---|---|---|---|---|
| Project owner |  |  |  |  |  |
| Legal review |  |  |  |  |  |
| Team A / dialogue owner |  |  |  |  |  |
| Team B / current-process verification |  |  |  |  |  |
| Dialogue reviewer 1 |  |  |  |  |  |
| Dialogue reviewer 2 / safety review |  |  |  |  |  |
| Native Hindi-language reviewer |  |  |  |  |  |

---

## Proposed contract and runtime resolutions for a later task

These are proposals only. Task 5C makes none of these source or contract
changes.

1. **Include SH in the central fixed-state set.** Add
   `State.SH_HUMAN_HANDOFF` to `FIXED_SCRIPT_STATES` so state definitions,
   registry, and policy agree.
2. **Use one central loader for S0, S9, SH, and SX.** Replace direct handling in
   session creation, session end, and human request with one fixed-script
   service. It must load by state/language, require exact-hash approval and all
   reviewer metadata, remain non-rephrasable, and preserve crisis precedence.
3. **Keep declined-consent SH truthful and analysis-free.** Commit routing
   before emission, do not inspect declined-consent text with AI, and use this
   generic candidate only while `human_joined` is false. Verified takeover uses
   a distinct validated event.
4. **Freeze safe S9 templating.** Reconcile the runtime format with the contract
   example, then implement the typed, session-owned, single-slot boundary above.
   Keep the dynamic reference outside model phrasing and prerecorded audio.
5. **Represent multiple reviews.** Replace the single reviewer/date fields with
   reviews keyed by required capacity. Activation requires a nonblank human
   name, qualification, explicit approval, date, and matching content hash for
   every capacity. Reject duplicates, placeholders, partial or stale reviews,
   and invented identities.
6. **Separate text and audio readiness.** Text readiness means all eight exact
   language records are approved and activated. Audio readiness separately
   requires approved assets verified against text, language, voice approval,
   and hash. Audio failure must not alter text approval.
7. **Never claim prerecorded audio without an asset.** Emit
   `audio:prerecorded` only when the registry is non-null and startup checks
   verify the exact approved asset. Otherwise use an explicitly supported
   text-only presentation or another separately approved contract behaviour.
8. **Keep health fail-closed.** `fixed_scripts_ready` remains false until all
   eight text records have complete approvals, matching hashes, and later
   activation. Add a separate audio-readiness signal only through the contract
   process, false until every separately approved asset verifies.
9. **Update documentation and tests together.** Later activation must update
   `STATES.md`, the canonical record, runtime, contract mirrors if needed, and
   tests for triggers, suppression, exact bilingual output, hash invalidation,
   templating, takeover truthfulness, privacy, and audio claims. Preserve the
   LLM/MuRIL/Task 7B/Whisper/D4 separation.

## Packet-level approval status

No script or language version in this packet is approved. All reviewer name,
role/qualification, decision, date, and comments cells remain blank.
`fixed_scripts_ready` must remain false, and audio readiness remains false.
