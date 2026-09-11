# Proposals from the 2026-09-11 evaluation

Each item states its status. As of the safety-hardening phase (2026-09-11, branch `feat/ml-safety-hardening`), P-GR-1, part of P-DET-1 and the evidence half of P-DET-3 are **implemented, pending two human reviews** (`reviews/safety-hardening-review.md`). Everything else is proposal only.

Each proposal lists its evidence (fixture IDs or measured values), its compatibility impact and the approvers it needs.
- Frozen values (weights, bands, overrides, enums, contracts) are unchanged.
- Guardrail and lexicon changes are `type:dialogue` changes. They need two reviewers, one of whom runs `dialogue-safety-reviewer`.

---

## P-SVI-1 — Without an override, the Critical band is unreachable on text *(contract §7 — all four leads)*

**Evidence** (`svi_sensitivity.ceilings`, `weak_combinations`):
- The highest text SVI without a hard override is **71.8 (High)**.
- D2 is binary in the text pipeline, and a D2 of 100 always forces Critical. So D2's 0.18 weight only ever contributes 0 to a band that the weights decide.
- D1 below the override tops out at 69, the future-threat ceiling.
- Seven lexicon dimensions at their tier-1 ceiling reach 50.91 (Moderate).

**Consequence.** On text, Critical comes only from a hard override (crisis, or confirmed imminent danger). The weighted score cannot produce it however many severe signals combine. This may be the intended design, since rules beat weights. But the frozen spec presents 75–100 as a reachable band, and it isn't reachable on text.

**Options for the leads** (none recommended here):
1. Accept it and document it in CONTRACTS §7.
2. Treat D2 as a routing rule rather than a weighted dimension on text.
3. Revisit the weights.

**Compatibility.**
- Options 2 and 3 change scores, bands and `SCORING_VERSION`.
- They affect the scenario expectations and the backend tests.
- Option 1 is documentation only.

## P-SVI-2 — Band is applied after rounding *(low; AI/ML and Safety plus Backend)*

The SVI is rounded to 2 dp before `band_for`, so a raw 29.995 is shown as 30.00 and banded Moderate. This is consistent with what the console displays. Recorded here; no change proposed unless the leads want the band computed on the raw value.

---

## P-GR-1 — Validator markers for the red-team failures *(type:dialogue)*

19 known failures; the full table is in `results/eval-baseline-2026-09-11.md`.

- **Proposed:** add the missing marker families in English, Hindi *and romanised Hinglish*.
  - Hinglish advice: "police ke paas jaana chahiye", "lawyer karna chahiye".
  - Diagnoses: "you have PTSD", "depressed lag rahe", "डिप्रेशन".
  - Promise variants: "will arrest them".
  - Legal conclusions: "offence under", "case banta hai".
  - Minimising: "tension mat lo".
  - Blaming: "you provoked".
  - Escalation suppression: "no need to involve", "batane ki zaroorat nahi".
  - Assessment vocabulary: "priority is", "जोखिम स्कोर".
  - Instruction residue: "ignore previous instructions".
- **Compatibility.** The validator only becomes stricter. Rejected sentences fall back to the pre-written text, which the LLM-off check already validates.
- **Owner:** AI/ML and Safety.
- **Status (safety hardening): IMPLEMENTED, pending review.** Implemented as category phrase rules (`ml/guardrails/lexicons/output_rules.py`, 87 rules in 13 categories, English, Hindi and Hinglish, including 5 urgency-level rules added after review). All 19 failures pass as regressions.

## P-GR-2 — Semantic check that the licensed question was asked *(type:dialogue)*

- **Evidence:** RT-EN-011 and RT-HI-005, leading questions accepted for `ask_immediate_safety`. Today the validator only checks that *a* question mark is present.
- **Proposed:** a deterministic check that the model's question keeps the licensed question's key terms, or that it stays within a small approved set of paraphrases.
- **Compatibility:** more fallbacks when the LLM is on. No change with the LLM off.

## P-DET-1 — Crisis lexicon coverage *(type:dialogue; AI/ML and Safety)*

**Candidate misses** (evidence only; these candidates must not be used as tuning targets):
- indirect method-and-plan statements — CAND-EN-003;
- first-person self-harm in Hindi — CAND-HI-003;
- misspellings — CAND-EN-019, CAND-HG-003.

**Proposed process:**
1. Write *new dev fixtures* for each pattern.
2. Draft lexicon entries and a bounded misspelling rule from those dev fixtures.
3. Re-measure the candidate set without editing it.

**Compatibility.** Recall rises. False positives route to a person.

**Status (safety hardening): PARTLY IMPLEMENTED, pending review.**
- Added: Unicode, spacing and hyphen normalisation, plus 30 explicit variants (misspellings, transliterations, and Hindi/Hinglish counterparts of existing English entries). CAND-EN-019, CAND-HI-003 and CAND-HG-003 pass as *regressions*.
- Not added: indirect statements (P-DET-4) and past tense (P-DET-5).

## P-DET-2 — Reported speech without a cue word *(leads' policy decision first)*

- **Evidence:** DEV-EN-011, DEV-HI-012, CAND-EN-012 and CAND-HI-009. A crisis phrase inside a TV show or someone else's story fires the pre-check.
- **Decision needed:** should quoted-only fictional content still interrupt to SX (recall first), or only flag it for an officer?
- **Available now:** D2 already records `attributed_turn_ids` when a cue word is present; the ML change is additive.

## P-DET-3 — Coercion evidence precision and conditional clauses

- **Evidence precision:** the coercion alert cites every D3 turn instead of only the withdrawal turn (DEV-EN-003).
- **Conditional clauses:** "shikayat wapas nahi li to …" is treated as a negation (CAND-HG-004).
- **Proposed:**
  - cite only the turns that matched the coercion terms;
  - exclude conditional patterns ("nahi … to", "if … not") from negation.
- ML-only change, but it affects alert evidence, so Backend review is needed.
- **Status (safety hardening):**
  - Evidence precision is **implemented, pending review**. The coercion alert now cites only turns whose own D3 match is a coercion term. The firing condition is unchanged. DEV-EN-003 now cites `t2` only.
  - Conditional clauses: **not changed**. This would alter detector meaning, so it stays a proposal.

## P-DET-4 — Ambiguous indirect language *(leads' safety decision; no rule added)*

| Phrase | Current behaviour (tested) | Why it is ambiguous |
|---|---|---|
| "I will not be here tomorrow." | pre-check does not fire | May mean suicide, leaving the village, a hospital stay or travel |
| "I have decided to take the pills tonight and not wake up." (CAND-EN-003) | does not fire | Strongly suggestive (method, time, intent), but has no stock phrase. A rule for it would be the first *method-plan* rule and needs an approved safety definition. |

**Proposed:** do **not** add a hard crisis override. Instead, add a separate `possible_indirect_risk` signal that routes to **Needs Human Assessment**, plus an officer-visible flag. It would never force SX or Critical on its own. This needs a leads' decision and a Backend route, because today only the crisis flag interrupts.

**Tests:** current behaviour is pinned in `test_hardening.py::test_documented_current_behaviour_for_ambiguous_phrases`.

## P-DET-5 — "killed myself" *(documented gap; not fixed)*

"nobody would care if I killed myself" does not fire, because "killed myself" is not a phrase and substring matching finds no "kill myself" in it. Adding "killed myself" blindly is unsafe in both directions:
- "I almost/nearly killed myself" is an attempt disclosure. That is high risk, and it should route.
- "I nearly killed myself laughing" is figurative.
- "he said I should have killed myself" is quoted abuse.

**Proposed context-aware rule, for review:**
- Fire on "killed myself" only when preceded, in the same clause, by an attempt marker ("almost", "nearly", "tried to", "wanted to", "would care if", "should have", "if I") and not followed by a figurative marker ("laughing", "joke").
- Keep attribution metadata as today.

It is not implemented, because no reviewed fixture set demonstrates an acceptable rule yet.

## P-DET-6 — Misspelt imminent return (DEV-EN-022) *(detector meaning; not changed)*

"They threatend us and said they wil come back tonite." is still a critical miss. Fixing it needs two things:
- spelling normalisation in the *detectors* ("wil", "tonite");
- a new D1 tier-3 phrase, "come back tonight".

That second part changes D1 meaning and can force a Critical override. Proposed for the AI/ML and Safety plus Backend leads; not implemented here.

## P-BND-1 — Structural boundary so the response generator never sees internal scores *(Backend, AI/ML and Safety; contract change)*

**Limitation, deliberately not "fixed" with a rule.** The validator can reject explicit score or priority wording, such as "your risk score is 82" or "your priority number is 82". It cannot reject a bare number. "Your number is 82" might be:
- a case or request reference;
- the helpline number;
- a queue or token id;
- a date or time.

A rule blocking bare numbers would reject legitimate victim-facing references, so none is added. `test_hardening.py::TestBareNumberBoundary` pins both sides: explicit wording is rejected, approved references are accepted.

**Proposed mitigation:** prevent the leak structurally instead of guessing afterwards.
1. **Input boundary.** The phrasing adapter (backend `adapters/llm`) receives only victim-safe context:
   - the licensed intent;
   - the language;
   - approved slots such as `reference_no`.

   It never receives SVI, band, dimensions, confidence, alerts or recommendations. This mirrors the victim-socket allowlist, applied to the LLM input.
2. **Typed provenance.** Every outgoing sentence carries response metadata, for example `{template_id, slots: {reference_no: {type: "victim_reference", value}}}`. The validator allows a number only when it equals a typed victim-safe slot value, and rejects any other digit run in a generated sentence.
3. **Tests.**
   - A contract test that the phrasing adapter's input schema has no assessment field.
   - Validator tests for an allowed typed reference versus an untyped number.
   - A backend test that no assessment value reaches the adapter.

**Compatibility.**
- It needs a new internal adapter input schema, response-metadata fields and a Backend change, so it is not implemented here.
- With the LLM off (the default), victims only receive pre-written text, so there is no generated number today.

## P-REV-1 — Fixture-review roles and adjudication cannot be checked by code *(documentation ambiguity; no policy change made)*

- **The rules today.** `ml/eval/schema.py::required_reviews` encodes a count: two real approvals for crisis or immediate-danger fixtures, one otherwise. `ml/eval/README.md` (reviewer checklist, step 5) adds more for crisis and immediate-danger fixtures: two reviewers "from the safety and helpline side, working independently, with any disagreement adjudicated and noted".
- **Why this is not a conflict.** The two rules don't contradict each other. The documentation is stricter, and code can't verify roles or independence.
- **What the workflow does.** `ml/eval/review_workflow.py` requires a `reviewer_role` on every record and counts distinct reviewers, as in the schema. It does **not** decide whether a role qualifies. Adjudication shows up as `needs_discussion` or `reject` records, which block completion.
- **Proposal.** The leads should decide whether qualifying roles and an adjudication record become machine-checked fields. For example, a reviewer allowlist with roles in a lead-owned file, and an `adjudication` record type. Until then, a human must confirm the roles before any fixture is locked.
- **Current effect.** None. No candidate is lock-eligible, because every candidate in corpus `2026.09.11-1` is exposed (CONTAMINATION.md).

## P-HR-1 — Text request for a human *(contract change; Backend, Mobile, AI/ML and Safety)*

The persistent app button (`request_human` event) is and remains the authoritative mechanism. **No detector is implemented.**

| Item | Proposal |
|---|---|
| Phrases | English: "talk to a (real) person", "speak to a human", "I want an officer", "connect me to someone", "not a machine". Hindi: "किसी इंसान से बात", "अधिकारी से बात करवाइए", "किसी व्यक्ति से". Hinglish: "insaan se baat", "officer se baat karwa do", "kisi insaan se baat karni hai". Exact phrase list only; each needs review. |
| Coverage today | 6 labelled fixtures (DEV-EN-013, DEV-HI-009, DEV-HG-011, CAND-EN-013, CAND-HI-010, CAND-HG-009), excluded from metrics. |
| False-positive risk | Reported speech ("the officer said to talk to a person"), negation ("I don't want to talk to anyone"), and questions *about* the service ("can I talk to a person later?"). A false positive routes to a person, which is cheap; a false negative leaves the button as the safety net. |
| Output signal | `request_human_text: {turn_id, phrase_id}`, emitted by ML beside the crisis pre-check. It must never be a score input. |
| Backend routing | Treat it exactly like the `request_human` event: state SH, takeover requested, officer alert. Needs a frozen signal in CONTRACTS §2/§3 and an intake change. |
| Scoring effect | None. It must not change SVI, band or alerts. |
| Contract changes | A new ML-to-Backend signal (CONTRACTS §5 pure-interface output or §3 event), plus a PC entry and a mirror update. |
| Tests required | Phrase/negation/quotation tables in three scripts; the backend integration test that the text request reaches SH; a no-score-change test; a victim-socket leakage test. |

---

## Backend or contract capabilities still required

1. **Text request for a human.** No text detector exists.
   - If ML adds one (6 labelled fixtures are waiting), the backend must turn the flag into `request_human`.
   - Today intake acts only on the socket event.
   - Owners: Backend, Mobile/Victim Experience, AI/ML and Safety.
2. **Showing attribution in the console.** `D2.basis = crisis_precheck_attributed` and `attributed_turn_ids` exist in the stored breakdown, but the console does not show them. Owner: Executive Web.
3. **Recording reviews.** Real reviewer approvals for the locked set need a place to be recorded.
   - Today this is `build_corpus.py` plus Git history.
   - A GitHub review workflow or an issue per batch would give an auditable trail.
   - Owners: all four leads.
4. **The crisis pre-check change** (clause-scoped negation) has two recorded code-level reviews in `reviews/crisis-precheck-review.md`. Two things remain open:
   - The packet's header line still reads "APPROVED. No review has taken place", which contradicts its records.
   - Both records list the same role, "AI/ML and Safety Lead". The second reviewer was meant to be a lead familiar with backend escalation.

   The humans concerned should reconcile these. An administrative correction note, and an explicit PENDING second-reviewer confirmation field, were **added** to that packet on 2026-09-11. Neither reviewer's record was edited.
5. **The safety-hardening changes** (output rules, crisis variants, coercion evidence) need two new human reviews: `reviews/safety-hardening-review.md`.

---

## Next dependency or dataset request — evidence does not justify one yet

**Recommendation: do not request a model or dataset now.**

The deterministic baseline's misses are dominated by lexical coverage:
- misspellings;
- romanised or regional forms;
- missing phrases.

Those should be fixed and measured first (P-DET-1, P-GR-1). There is also no reviewed locked set yet. With 0 lock-eligible samples, a model's benefit could not be measured honestly, and adding one now would produce an unmeasurable claim.

**The request to make once there are at least 50 reviewed critical-safety samples and the lexicon fixes have been measured.** This is recorded for planning only; nothing has been downloaded or installed.

| Field | Value |
|---|---|
| Item | `google/muril-base-cased` (EXT-106, currently PROPOSED). The exact revision must be pinned at request time. |
| Purpose | A second-stage crisis/self-harm and threat classifier for indirect statements that no lexicon catches (CAND-EN-003, CAND-HI-003). It would only *add* flags and never suppress the lexicon pre-check. |
| Size | Around 240M parameters; a download on the order of 1 GB. Estimate: verify on the model card before requesting. |
| Licence | Apache-2.0, per the model card. Verify at request time. |
| Languages | 17 Indian languages plus English, including transliterated text, per the model card. |
| Hardware | CPU inference plausible with a few GB of RAM; no GPU required for single-utterance inference. Unmeasured here. |
| Latency | Unmeasured. It must fit the parallel assessment path, never the ≤ 0.05 s synchronous pre-check. |
| Privacy | Local inference only. No text leaves the machine. |
| Offline | Fully offline once the weights are stored under `DATA_ROOT` (outside Git). |
| Failure fallback | The lexicon pipeline unchanged. If the model is missing, the assessment records `classifier_unavailable` and never abstains on that alone. |
| Why the deterministic logic is insufficient | Indirect intent ("take the pills tonight and not wake up") has no stable surface phrase. This only matters once lexical coverage is fixed. |
| Evaluation plan | Locked-set recall and precision for crisis and threat, per language and per slice, compared with the lexicon-only baseline. Critical misses and false escalations listed by fixture. Also: a fine-tuning dataset licence review, calibration and latency. |
| Rollback | Remove the adapter flag. The lexicon path is the default, and removing the model changes no stored contract. |
