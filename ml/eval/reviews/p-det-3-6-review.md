# Review packet — detectors v1.2: misspelt imminent return (P-DET-6) and conditional coercion (P-DET-3)

| Field | Value |
|---|---|
| Change | `ml/nlp/lexicons.py`: six tier-3 D1 phrases, `SPELLING_VARIANTS` (23 whole-word entries), `CONDITIONAL_NEGATION_EXEMPT = {"D3"}` with condition and consequence markers. `ml/nlp/detectors.py`: `normalise_spelling` before matching; the D3 conditional check. `LEXICON_VERSION = "detectors-v1.2-draft"`. |
| Why | Plan M14 exposed failures: the missed dev critical event DEV-EN-022, and coercion recall on candidates (CAND-HG-004, a conditional threat read as a denial). |
| Status | **DRAFT: written and tested, not yet reviewed by a human.** Two reviewers are required: the AI/ML and Safety lead and the Backend lead (P-DET-6 changes D1 meaning and can force a Critical override), one of them a native Hindi reader. Record the decisions below and change the version suffix to `-reviewed`. |
| Contract | No change. Scores, bands, overrides, weights and enums are untouched. The crisis pre-check is untouched. |

## 1. What changed

**D1, tier 3 (imminent).** The new phrases are "come back tonight", "coming back tonight", "aaj raat wapas aayenge", "aaj raat phir aayenge", "आज रात वापस आएंगे" and "आज रात फिर आएंगे".
- Rationale: a return *tonight* is as imminent as the existing tier-3 phrases "coming tonight", "aaj raat aayenge" and "आज रात आएंगे".
- Tier 3 reaches the D1 hard override, so a match with enough confidence forces Critical.

**Spelling map (detectors only).** The map is explicit and matches whole ASCII words only. There is no stemming or fuzzy matching.
- English: wil, tonite, tonit, 2nite, 2night, tonyt, comin, threatend, thretened, threatned, threatning, thretening.
- Hinglish: wapis, vapas, vaapas, ayenge, aaenge, aayege, ayege, dhamkee, dhamaki, shikayt, shikaayat.
- Each maps to the spelling already used in the lexicon.
- Matched terms and evidence stay the canonical lexicon terms.
- The crisis pre-check keeps its own reviewed normalisation and does not use this map.

**Conditional clauses (D3 only).** A negation no longer cancels a D3 hit when either of these holds in the same clause:
- a condition marker precedes the match ("if", "unless", "agar", "agr", "अगर");
- the negation is followed by a consequence marker ("to", "toh", "warna", "varna", "तो", "वरना").

So "agar complaint wapas nahi li to …" and "if you don't withdraw the complaint, …" count as coercion, not as denials of it. Devanagari markers must be whole words ("तो", never inside "तोड़"). **D1 keeps ordinary negation:** "if they don't come back tonight" is not a claim of danger.

## 2. Evidence

- **Unit tests:** `ml/tests/test_detectors_m14.py` (12 tests) covers:
  - returns tonight in English, Hinglish and Hindi, including misspellings;
  - negated and conditional returns;
  - conditional coercion in all three languages;
  - plain negation still cancelling;
  - the whole-word "तो" rule;
  - the spelling map never introducing a negation word;
  - the crisis pre-check unchanged;
  - DEV-EN-022 routing Critical, and the coercion alert on a conditional threat.

  These sentences were written by the same author alongside the rules, so they are development evidence, not holdout evidence.
- **Exposed corpora, before against after (2026-09-28):**

  | | Before | After |
  |---|---|---|
  | Dev critical misses | 1 of 17 | **0 of 17** (DEV-EN-022, regression only) |
  | Dev continuing_threat | tp 16, fn 4 | tp 18, fn 2 (DEV-EN-022, DEV-HG-010) |
  | Dev immediate_danger | tp 7, fn 1 | tp 8, fn 0 |
  | Candidate coercion | tp 2, fn 3 | tp 3, fn 2 (CAND-HG-004, regression only) |
  | False escalations, dev / candidate | 2 / 2 | 2 / 2 |
  | New false positives, any detector | — | **0** |
  | Red-team | 39 / 39 | 39 / 39 |

  Every changed fixture is exposed (`REGRESSION_TARGETS_M14`, CONTAMINATION.md). None of this is generalisation evidence.

## 3. Deliberately NOT changed

- **Quoted and attributed crisis speech** (DEV-EN-011, DEV-HI-012, CAND-EN-012, CAND-HI-009) still routes to a person. Suppressing it would weaken the crisis interrupt (invariant 2). Changing it needs the leads' policy decision (P-DET-2).
- **Chat abbreviations in coercion** (CAND-HG-014) and **regional threat vocabulary** are not covered. No reviewed pattern set exists yet.
- **The conditional rule does not apply to D1, D5, D7 or D9.**

## 4. Risks

- **False positives, D1:**
  - A benign return tonight ("my son will come back tonight from the city") fires tier 3 and forces Critical. The lexicon cannot tell who is returning. The cost is an officer reviewing a non-urgent case; a test pins this.
  - Hinglish "phir aayenge" has the same issue.
- **False positives, D3:** "dhamki nahi di to …" ("they didn't threaten, so …") now counts as a threat. This is rare, and it routes to a person (coercion alert), not to Critical.
- **Spelling map:** each variant is a whole word. "vapas" is also a standard spelling, and mapping it is intended. A variant that turns out to be a real word in another language would be a false positive; the reviewer should check the list.
- **False negatives:** other spellings ("tonait", "wapass"), indirect imminence ("they are on their way") and long conditionals that span a clause break ("if you don't withdraw it, then …") are not covered.

## 5. Reviewer checklist

- [ ] I agree that a return *tonight* belongs in tier 3 (imminent), with the Critical override that implies.
- [ ] I read every spelling variant. Each is an unambiguous misspelling or variant of the lexicon word.
- [ ] A native Hindi reader checked the Hindi and Hinglish phrases and the "to", "toh" and "तो" consequence markers.
- [ ] I agree the conditional exemption is D3 only.
- [ ] I ran `python -m pytest ml/tests/test_detectors_m14.py` myself.
- [ ] I did not author this change.

## 6. Review records (to be completed by each reviewer personally; left empty)

```text
Reviewer:
Role:
Reads Hindi (yes/no):
Decision (approve / request changes):
Reasoning (own words):
Date:
```

```text
Reviewer:
Role:
Reads Hindi (yes/no):
Decision (approve / request changes):
Reasoning (own words):
Date:
```
