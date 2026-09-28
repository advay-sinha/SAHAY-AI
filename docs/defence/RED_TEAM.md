# Red-team result

Generated from the evaluation run of 2026-09-28T00:00:00+00:00 (commit `0f05ec466e47`).

**Evidence class: exposed regression.** The red-team corpus was published on 2026-09-11 and its failures were fixed afterwards, so a pass shows the regression is fixed, not that the validator generalises (`ml/eval/CONTAMINATION.md`).

**39 of 39 cases blocked before synthesis.** Failures by severity: critical 0, high 0, low 0, medium 0.

## By language

| Language | Cases | Blocked |
|---|---|---|
| English | 23 | 23/23 |
| Hindi | 7 | 7/7 |
| Hinglish | 9 | 9/9 |

## By category

| Category | Cases | Blocked | Languages |
|---|---|---|---|
| advice outside scope | 4 | 4/4 | English, Hinglish |
| diagnosis | 4 | 4/4 | English, Hindi, Hinglish |
| embedded instruction | 2 | 2/2 | English |
| leading question | 2 | 2/2 | English, Hindi |
| legal conclusion | 2 | 2/2 | English, Hinglish |
| minimising | 3 | 3/3 | English, Hindi, Hinglish |
| promise | 3 | 3/3 | English, Hindi |
| prompt injection | 2 | 2/2 | English, Hindi |
| quoted threat | 2 | 2/2 | English, Hinglish |
| reveal scores | 5 | 5/5 | English, Hindi, Hinglish |
| roleplay | 3 | 3/3 | English |
| suppress escalation | 4 | 4/4 | English, Hinglish |
| victim blaming | 3 | 3/3 | English, Hindi |

Hindi has the fewest red-team cases. More Hindi and Hinglish cases, written by people who did not build the validator, are needed before any claim about those languages.
