# Component card — Stress Vulnerability Index (SVI) engine

| Field | Value |
|---|---|
| Component | `ml/svi/engine.py`, `dimensions.py`, `overrides.py`; scoring version `svi-2026.09-pc08` |
| Type | Deterministic weighted sum with hard overrides and abstention. Standard library only, no I/O. |
| Output | A score from 0 to 100, a band (Low 0–29, Moderate 30–54, High 55–74, Critical 75–100), a per-dimension breakdown with confidence and evidence, any overrides applied, or `needs_human` with no score |
| Consumer | The executive console only. **Never sent to the victim** (server-enforced and tested). |

## Weights — PROVISIONAL

The weights are **design choices, not fitted values**. They await expert calibration, and the console labels them provisional (`WEIGHTS_ARE_PROVISIONAL = True`).

| Dimension | Meaning | Weight |
|---|---|---|
| D1 | Immediate safety threat | 0.22 |
| D2 | Crisis or self-harm language | 0.18 |
| D3 | Fear, intimidation, threats | 0.13 |
| D4 | Acute distress, from voice | 0.12 |
| D5 | Trauma-associated indicators | 0.08 |
| D6 | Isolation, boycott, displacement | 0.08 |
| D7 | Medical urgency | 0.08 |
| D8 | Legal urgency | 0.06 |
| D9 | Communication safety | 0.05 |

## Rules that override the weights

- **Crisis or confirmed immediate danger forces Critical**, whatever the weighted score (invariant 5). The override needs D1 or D2 ≥ 70 at confidence ≥ 0.60.
- **Abstention** (invariant 6) returns `needs_human` and **no score** for any of:
  - aggregate confidence below 0.45;
  - poor audio or low speech-to-text confidence;
  - low language confidence;
  - poor input quality or conflicting evidence;
  - declined consent;
  - an unmeasured acoustic dimension on a voice channel.
- **Renormalisation (PC-08)** happens only for a dimension that is structurally unavailable, meaning D4 on a typed channel. The denominator is then 0.88.

## Evidence

- Unit and contract tests cover the formula, bands, overrides, abstention and renormalisation.
- On the exposed fixtures, labelled bands agree with the engine's bands on 17 of 17 dev fixtures and 13 of 14 candidates (evaluation of 2026-09-28; exposed regression evidence).
- Abstention happens whenever it is expected: 4 of 4 on dev and 1 of 1 on candidates.
- **Known structural property (P-SVI-1, awaiting the leads):** on text, Critical is reachable only through an override. The highest weighted text score without one is 71.8, which is High (measured 2026-09-11; the weights have not changed since).

## Not claimed

The SVI is not a clinical scale, a diagnosis or a validated risk instrument. It is a triage aid whose weights are provisional. A human decides every action.
