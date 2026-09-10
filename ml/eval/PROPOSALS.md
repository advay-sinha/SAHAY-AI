# Proposals from the 2026-09-11 evaluation — NONE IMPLEMENTED

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
4. **The crisis pre-check change** (clause-scoped negation) needs its `type:dialogue` sign-off before the next `dev` promotion.

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
