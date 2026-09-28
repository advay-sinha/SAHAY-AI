# Component card — crisis pre-check and rule-based detectors

| Field | Value |
|---|---|
| Components | Crisis pre-check `ml/guardrails/crisis_precheck.py` (`crisis-v1.2-unreviewed`); text detectors `ml/nlp/detectors.py` with lexicons `ml/nlp/lexicons.py` (`detectors-v1.2-draft`) |
| Type | Deterministic rules: phrase lexicons, clause-scoped negation, attribution cues, an explicit spelling map. Standard library only; the same input always gives the same output. |
| Languages | English, Devanagari Hindi, romanised Hinglish |
| Authority | **Authoritative.** They decide crisis routing (SX, Critical, takeover) and feed the SVI dimensions D1, D2, D3 and D5–D9. Every model in this project is compared against them and none replaces them. |

## What they do

- **Crisis pre-check.**
  - It runs synchronously on every victim turn, before the dialogue policy.
  - The lexicon has 21 English, 16 Hindi and 12 Hinglish crisis entries plus reviewed variants. Unicode, spacing and hyphen normalisation is applied first.
  - A match forces state SX, the fixed script, Critical priority and a human takeover. Intake never resumes on its own.
  - Negation and attribution are clause-scoped. Attributed matches still route to a person, but are recorded as attributed.
- **Detectors.**
  - Each dimension has a lexicon of tiered phrases (tier 3 explicit and severe, 2 explicit, 1 implied). The number of phrases per dimension:

    | D1 | D3 | D5 | D6 | D7 | D8 | D9 |
    |---|---|---|---|---|---|---|
    | 38 | 22 | 76 | 22 | 23 | 17 | 12 |
  - Tier 3 in D1 (imminent danger) can trigger the Critical override.
  - D4 has no text lexicon: it is voice-only.
  - Every score cites the turns that produced it.

## Measured (see `docs/defence/NUMBERS.md`, `ml/eval/results/eval-table-2026-09-29.md`)

**Evidence class: exposed regression.** Both fixture sets were published during development, so these numbers show regression behaviour, not generalisation.

| Measure | Development fixtures (57) | Candidate fixtures (48) |
|---|---|---|
| Critical events missed | 0 of 17 | 1 of 14 |
| Crisis pre-check recall | 9 of 9 | 8 of 9 |
| Crisis pre-check precision | 0.82 | 0.80 |
| Detector micro F1, 7 text categories | 0.93 | 0.88 |
| Red-team victim inputs matching the expected crisis outcome | 8 of 8 | — |

Rule recall on the borrowed-label test sets (weak-supervision evidence):
- Reddit crisis posts: 0.38;
- stressed Dreaddit posts: 0.10 (D5);
- hate-speech rows: 0.003 (threat).

The rules are precise and narrow. They catch explicit phrasing and miss indirect, figurative and regional wording.

## Known gaps (recorded, not hidden)

- **Indirect crisis statements** without a stock phrase ("take the pills tonight and not wake up") are not caught (P-DET-4). The shadow MuRIL detector catches some, but it also fires on harmless absence wording.
- **Quoted and attributed crisis speech** still interrupts to a person. That's the recall-first design, pending the leads' P-DET-2 decision.
- **Draft changes** await two human reviews each: `v1.1` anxiety and low-mood terms; `v1.2` conditional coercion and the misspelt return-tonight fix.
- **Coverage:** regional vocabulary, chat abbreviations and spelling variants outside the explicit map are not covered.

## Not claimed

Clinical validity, accuracy on real victims, or coverage of any language beyond the three above.
