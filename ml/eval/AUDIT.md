# Text pipeline audit — 2026-09-11

Scope: the deterministic Hindi, English and Hinglish text pipeline on the integrated `dev` baseline `cd7031b`, plus the two ML fixes in this change.

Sources:
- `ml/assessment.py`, `ml/nlp/*`, `ml/guardrails/*`, `ml/svi/*`, `ml/dialogue/*`
- evidence measured by `python -m ml.eval.run_eval`

Fixture IDs refer to `ml/eval/corpus/`.

Classification key:
- **DT** — deterministic and tested
- **HT** — heuristic and tested
- **HW** — heuristic but weakly validated: tested in code, but the only evidence of accuracy is author-drafted, unreviewed fixtures
- **UA** — unavailable
- **NI** — not implemented
- **OP** — outside the current phase

**No capability here is validated.** Every accuracy figure comes from fictional, author-drafted fixtures that no human has reviewed.

| Capability | Class | What it does and what it outputs | Evidence and known gaps |
|---|---|---|---|
| Crisis/self-harm pre-check (`guardrails/crisis_precheck.py`) | DT (behaviour), HW (recall) | Substring lexicon: 21 English, 16 Hindi and 12 Hinglish phrases. Returns `{crisis, matches[term, lang, context], suppressed[], lexicon_version}` synchronously before dialogue policy. A match forces SX. | **Fixed here:** the negation window crossed sentence boundaries, so "The police never came back. I want to die." was *suppressed*. It is now clause-scoped (below). Remaining misses: indirect statements (CAND-EN-003 "take the pills … not wake up", CAND-HI-003 "खुद को नुकसान"), and misspellings (CAND-EN-019 "kil myself", CAND-HG-003 "atmhatya"). |
| Immediate danger (D1 tier 3 + hard override) | HT | D1 tier-3 phrases (imminent presence, weapons, "tonight") score 85 with confidence 0.70. The engine's D1 ≥ 70 at confidence ≥ 0.60 then forces Critical. | Misspelling miss: DEV-EN-022 ("wil come back tonite"). Beats a conflicting "we are safe" (DEV-EN-014, DEV-HG-016, CAND-EN-014, CAND-HG-013 all Critical). Quoted news of danger elsewhere is not detected as attribution; see the quotation row. |
| Threat / intimidation (D1 tier ≤ 2, D3) | HW | Future threats and threat words; pressure-to-withdraw phrases. | Misses: regional (DEV-HI-011 "मार देब"), misspellings (DEV-HG-010 "dhamaki", "maar dalenge"), word order (DEV-EN-012 "take the complaint back"), synonyms (CAND-EN-004 "warning us"). |
| Medical urgency (D7) | HW | Injury, bleeding and unconsciousness terms. Tier 1 ("pain") does not count as urgency. | Miss: CAND-EN-005 "fainted … not responding". |
| Isolation / boycott / displacement (D6) | HW | Boycott, water and shop denial, forced departure. | Misses: CAND-HG-006 "biradari se nikaal diya" (regional), CAND-EN-022 "hiding at my sister's house", DEV-EN-023 "don't talk to us much". |
| Legal urgency (D8) | HT | FIR, complaint, police station, court, hearing. Deliberately not negation-sensitive. | Miss: CAND-HG-012 "dhara" (legal section). |
| Communication safety / coercion (D9 + coercion alert) | HW | D9 phrases ("someone is listening"); the coercion alert also fires on D3 withdrawal terms. | Misses: chat abbreviations (CAND-HG-014 "sun rha … nhi bol skti"), and a conditional read as negation (CAND-HG-004 "shikayat wapas nahi li to …"). **Evidence imprecision:** the coercion alert cites every D3 turn, not only the withdrawal turn (DEV-EN-003 cites t1 and t2; expected t2). |
| Explicit request for a human (text) | NI | None. The app sends `request_human` from a button, and the dialogue policy honours it from every state. | Excluded from metrics with that reason; 6 labelled fixtures are waiting for a detector. |
| Negation handling — detectors | DT | An 18-character window, cut at clause breaks; applies to D1, D3, D5, D7 and D9. | Clause-scoped and tested (`test_assessment`). Conditional clauses are mis-read as negation (CAND-HG-004). The Hindi negation list is short. |
| Negation handling — crisis pre-check | DT (changed here, pending review) | A 40-character window, now cut to the clause containing the match. | Tests: `TestCrisisNegationIsClauseScoped`. The fix can only make the pre-check fire more often. Trade-off: "I would never, ever kill myself" now fires, because the comma splits the clause. That is a false positive that routes to a person. |
| Quotation / attribution — crisis | DT (routing), HT (context) | Attribution cues ("he told me", "उसने कहा") are recorded as context and never suppress the flag (recall first). | **Changed here:** D2 now carries `matched_terms`, `attributed_turn_ids` and basis `crisis_precheck_attributed`, so an attributed match no longer reads as a first-person claim. Reported speech without a cue word (TV, a neighbour, a film) is not recognised: DEV-EN-011, DEV-HI-012, CAND-EN-012 and CAND-HI-009 are false escalations. |
| Quotation / attribution — other detectors | NI | None. | A reported threat ("my neighbour said the landlord's men will kill us") correctly counts as a threat (DEV-EN-027). A quoted danger elsewhere would also count. |
| Hindi and Hinglish lexicons | HW | Lexicon sizes: D1 32, D3 22, D5 14, D6 22, D7 23, D8 17, D9 12. Crisis: 16 Devanagari and 12 romanised phrases. | Development lexicons, not reviewed by native-speaker safety reviewers. |
| Misspelling and regional vocabulary | NI | Exact phrase or word-boundary matching only. No fuzzy or transliteration matching. | 8 of the misses above are misspellings, abbreviations or regional forms. |
| Evidence-turn extraction | DT | Every positive result carries the victim turn IDs that produced it. | 136/136 (dev) and 77/77 (candidate) cited IDs are real victim turns. Labelled-evidence exact agreement: dev 0.981, candidate 1.000. |
| Abstention | DT | Aggregate-confidence floor 0.45, poor or unreadable input, low language confidence, conflicting safety statements, and `acoustic_not_measured` on voice. Returns Needs Human Assessment with no number. | All expected abstentions abstain (dev 4/4, candidate 1/1). Single-turn samples mostly abstain by design (36 of 57 dev samples), so band-level metrics are thin. |
| Guardrail validator (`guardrails.validate`) | DT (marker list), HW (coverage) | Structural bans plus prohibition markers in English and Hindi, checked in both languages. Fails closed to the pre-written fallback. | Every listed marker is rejected (10/10 prohibitions covered in both languages). The red-team passes 20/39: no romanised-Hinglish markers, and no semantic checks (leading questions, a substituted question, legal conclusions, "no need to involve anyone"). Details are in the report. |
| Prompt injection via victim text | DT | The dialogue policy ignores the utterance. Routing comes only from the pre-check and the detectors. | 8/8 victim-input red-team cases pass: injection neither suppresses nor forces escalation, and leaks no scores. |
| SVI integration (PC-08) | DT | D4 is structurally unavailable on text (÷ 0.88). The voice channel abstains. Hard overrides are independent of the weighted score. | `test_svi_normalization`, and the D4 checks in the evaluation (0 problems). See the sensitivity findings in the report. |
| Language identification | HT | A script-and-marker heuristic: `hi`, `en`, `hinglish` or `unknown`. | Unit-tested. Not measured against labelled language data. |
| Scenario fixtures and replay | DT | `backend/scenarios` walk-through, and incremental replay in `checks.scenario_replay`. | Backend scenario 35/35, then replay 1/1 with no new rows. ML replay consistent across 10 multi-turn samples. |
| D4 acoustic distress | UA (text) / OP | Never estimated, never zero. | EXT-004/005 (ASR, VAD) and an acoustic model are proposed, not approved. |
| ASR, VAD, TTS, acoustics, ML classifiers | OP | Interfaces only (`asr/`, `tts/`, `acoustics/`, `nlp/classifiers.py`). | Each needs an approved external decision. |

## Changes made in this phase (ML-owned files only)

1. **Crisis pre-check negation is clause-scoped** (`ml/guardrails/crisis_precheck.py`; lexicon version `crisis-v1.1-unreviewed`).
   - Motivated by dev fixtures only.
   - Fixed dev misses: DEV-EN-010, DEV-HI-013, DEV-HG-009.
   - It also caught candidate CAND-EN-011, which was not used for tuning.
   - This is a guardrail change. It needs the repository's `type:dialogue` review: two reviewers, one of them running `dialogue-safety-reviewer`.
   - `docs/dialogue/STATES.md` does not describe negation rules, so no state text changed.
   - It changes no victim-facing wording.
2. **D2 keeps attribution context** (`ml/nlp/detectors.py::score_crisis`).
   - It adds `matched_terms`, `attributed_turn_ids`, and basis `crisis_precheck_attributed`.
   - Score and routing are unchanged; the backend displays `basis` as text only.
   - This is additive to the dimension record and does not change `svi.compute` or any contract.

Measured before and after:

| | Before (dev) | After (dev) | Before (candidate) | After (candidate) |
|---|---|---|---|---|
| Critical misses | 4 of 17 | 1 of 17 | 5 of 14 | 4 of 14 |
| False escalations | 2 | 2 | 2 | 2 |
| Crisis pre-check recall | 0.571 | 1.000 | 0.444 | 0.556 |
