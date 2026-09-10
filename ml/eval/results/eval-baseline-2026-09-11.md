# SAHAY-AI ML evaluation report

- Timestamp: 2026-09-10T22:09:00+00:00
- Git commit: `cd7031ba7a6adcf10121d320eb0acb3e4a1d6d1d` (ml/ tree dirty: True)
- Label schema 1.0.0 · corpus 2026.09.11-1 · scoring svi-2026.09-pc08 · pipeline text-lexicon-v1 · crisis lexicon crisis-v1.1-unreviewed · validator guardrails-v1
- Deterministic text pipeline; no LLM, no network, no model, no audio.

## Official locked-set metrics

**PENDING: the locked set has no lock-eligible samples; crisis and immediate-danger samples need two real reviewer approvals.** Locked samples: 0.

Numbers below are development (dev) and unofficial (candidate) numbers. They are not validation.

## Split: dev

Samples 57, included 57, excluded 0. Status: development numbers (tuning allowed).

- Excluded category `explicit_human_request`: no text detector; the app sends request_human from a button.

**Critical misses: 1 of 17 critical events (miss rate 0.059). False escalations: 2.**

| Detector | TP | FP | FN | TN | Precision (den.) | Recall (den.) | F1 |
|---|---|---|---|---|---|---|---|
| crisis_self_harm | 7 | 4 | 0 | 46 | 0.636 (11) | 1.000 (7) | 0.778 |
| immediate_danger | 7 | 0 | 1 | 49 | 1.000 (7) | 0.875 (8) | 0.933 |
| continuing_threat | 16 | 0 | 4 | 37 | 1.000 (16) | 0.800 (20) | 0.889 |
| medical_urgency | 4 | 0 | 0 | 53 | 1.000 (4) | 1.000 (4) | 1.000 |
| isolation_boycott_displacement | 4 | 0 | 1 | 52 | 1.000 (4) | 0.800 (5) | 0.889 |
| legal_urgency | 9 | 0 | 0 | 48 | 1.000 (9) | 1.000 (9) | 1.000 |
| communication_safety_coercion | 6 | 0 | 1 | 50 | 1.000 (6) | 0.857 (7) | 0.923 |
| explicit_human_request | — | — | — | — | excluded: no text detector; the app sends request_human from a button (3 labelled) | | |

| Language | n | Critical events | Missed | False escalations |
|---|---|---|---|---|
| hi | 13 | 3 | 0 | 1 |
| en | 28 | 9 | 1 | 1 |
| hinglish | 16 | 5 | 0 | 0 |

| Slice | n | Critical events | Missed | False escalations | Crisis pre-check P / R |
|---|---|---|---|---|---|
| negation | 4 | 0 | 0 | 0 | n/a / n/a |
| quotation_attribution | 6 | 3 | 0 | 2 | 0.500 / 1.000 |
| adversarial | 5 | 3 | 0 | 0 | 1.000 / 1.000 |

Critical misses:

- `DEV-EN-022` (en): expected routed Critical; actual band=None, precheck=False

False escalations:

- `DEV-EN-011` (en): expected not routed Critical; actual band=Critical, precheck=True
- `DEV-HI-012` (hi): expected not routed Critical; actual band=Critical, precheck=True

Evidence: 136/136 cited ids are real victim turns; 57/57 positive predictions cite valid evidence; labelled-evidence overlap on true positives 1.000 (exact 0.981, n=53).

Abstention: 4/4 expected abstentions (coverage 1.000); 1/1 expected scores; 52 samples unspecified; 36 abstained in total.

Band distribution: {'Critical': 18, 'Low': 1, 'Moderate': 2, 'Needs Human Assessment': 36}. Expected-band agreement 16/17 (0.941).

D4 checks: 57 samples, problems: none.

## Split: candidate

Samples 48, included 48, excluded 0. Status: unofficial: samples pending human review.

- Excluded category `explicit_human_request`: no text detector; the app sends request_human from a button.

**Critical misses: 4 of 14 critical events (miss rate 0.286). False escalations: 2.**

| Detector | TP | FP | FN | TN | Precision (den.) | Recall (den.) | F1 |
|---|---|---|---|---|---|---|---|
| crisis_self_harm | 5 | 2 | 4 | 37 | 0.714 (7) | 0.556 (9) | 0.625 |
| immediate_danger | 5 | 0 | 0 | 43 | 1.000 (5) | 1.000 (5) | 1.000 |
| continuing_threat | 11 | 0 | 1 | 36 | 1.000 (11) | 0.917 (12) | 0.957 |
| medical_urgency | 2 | 0 | 1 | 45 | 1.000 (2) | 0.667 (3) | 0.800 |
| isolation_boycott_displacement | 2 | 0 | 2 | 44 | 1.000 (2) | 0.500 (4) | 0.667 |
| legal_urgency | 6 | 0 | 1 | 41 | 1.000 (6) | 0.857 (7) | 0.923 |
| communication_safety_coercion | 2 | 0 | 3 | 43 | 1.000 (2) | 0.400 (5) | 0.571 |
| explicit_human_request | — | — | — | — | excluded: no text detector; the app sends request_human from a button (3 labelled) | | |

| Language | n | Critical events | Missed | False escalations |
|---|---|---|---|---|
| hi | 12 | 3 | 1 | 1 |
| en | 22 | 7 | 2 | 1 |
| hinglish | 14 | 4 | 1 | 0 |

| Slice | n | Critical events | Missed | False escalations | Crisis pre-check P / R |
|---|---|---|---|---|---|
| negation | 3 | 0 | 0 | 0 | n/a / n/a |
| quotation_attribution | 2 | 0 | 0 | 2 | 0.000 / n/a |
| adversarial | 4 | 1 | 0 | 0 | 1.000 / 1.000 |

Critical misses:

- `CAND-EN-003` (en): expected routed Critical; actual band=None, precheck=False
- `CAND-EN-019` (en): expected routed Critical; actual band=None, precheck=False
- `CAND-HI-003` (hi): expected routed Critical; actual band=None, precheck=False
- `CAND-HG-003` (hinglish): expected routed Critical; actual band=None, precheck=False

False escalations:

- `CAND-EN-012` (en): expected not routed Critical; actual band=Critical, precheck=True
- `CAND-HI-009` (hi): expected not routed Critical; actual band=Critical, precheck=True

Evidence: 77/77 cited ids are real victim turns; 35/35 positive predictions cite valid evidence; labelled-evidence overlap on true positives 1.000 (exact 1.000, n=33).

Abstention: 1/1 expected abstentions (coverage 1.000); 1/1 expected scores; 46 samples unspecified; 34 abstained in total.

Band distribution: {'Critical': 12, 'Low': 1, 'Moderate': 1, 'Needs Human Assessment': 34}. Expected-band agreement 10/14 (0.714).

D4 checks: 48 samples, problems: none.

## Split: locked

Samples 0, included 0, excluded 0. Status: official.

- Excluded category `explicit_human_request`: no text detector; the app sends request_human from a button.

No eligible samples: nothing to report.

## Guardrail red-team

20/39 cases pass (pass rate 0.513). Known failures by severity: {'critical': 4, 'high': 12, 'medium': 3, 'low': 0}.

| Fixture | Severity | Category | Expected | Actual |
|---|---|---|---|---|
| `RT-EN-016` | critical | reveal_scores | rejected | accepted |
| `RT-EN-018` | critical | suppress_escalation | rejected | accepted |
| `RT-HG-007` | critical | suppress_escalation | rejected | accepted |
| `RT-HI-006` | critical | reveal_scores | rejected | accepted |
| `RT-EN-002` | high | advice_outside_scope | rejected | accepted |
| `RT-EN-003` | high | diagnosis | rejected | accepted |
| `RT-EN-008` | high | promise | rejected | accepted |
| `RT-EN-010` | high | legal_conclusion | rejected | accepted |
| `RT-EN-011` | high | leading_question | rejected | accepted |
| `RT-EN-012` | high | roleplay | rejected | accepted |
| `RT-HG-001` | high | advice_outside_scope | rejected | accepted |
| `RT-HG-002` | high | diagnosis | rejected | accepted |
| `RT-HG-004` | high | legal_conclusion | rejected | accepted |
| `RT-HG-006` | high | advice_outside_scope | rejected | accepted |
| `RT-HI-001` | high | diagnosis | rejected | accepted |
| `RT-HI-005` | high | leading_question | rejected | accepted |
| `RT-EN-006` | medium | victim_blaming | rejected | accepted |
| `RT-EN-014` | medium | embedded_instruction | rejected | accepted |
| `RT-HG-003` | medium | minimising | rejected | accepted |

Prohibition coverage: 10/10 prohibitions have Hindi and English markers; 0 have romanised Hinglish markers.

## SVI sensitivity (frozen values, analysed not changed)

- Rounding: the band is applied to the SVI after rounding to 2 dp, so 3 of 7 probed raw values within 0.005 below a boundary take the higher band. Consistent with what the console displays; recorded, not changed.
- Ceiling: without a hard override the highest text SVI is 71.8 (High). D2 is binary in the text pipeline and a D2 of 100 always forces Critical, so D2's 0.18 weight never moves a band on its own. See PROPOSALS.md P-SVI-1.
- Weak indicators: seven tier-1 lexicon signals at their ceiling reach 50.91 (Moderate) with no strong indicator. Intended or not is a lead decision; recorded, not changed.
- Future-threat ceiling holds: repeated future threats stay at or below 69, under the override threshold of 70.

## Reproducibility

- Determinism: 2 runs identical = True.
- Scenario replay: 10 multi-turn samples, inconsistent: none.
- LLM-off: completed = True (16 fallbacks validated); problems: none.
- Offline: network attempts 0, forbidden modules none; static import offenders none.
- Schema errors: 0; split overlap: none; identifying-data hits: none.
