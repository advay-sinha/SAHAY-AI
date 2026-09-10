---
name: svi-engine
description: Use when implementing or changing the Stress Vulnerability Index — dimensions, weights, bands, hard overrides, abstention or trajectory.
---

# SVI engine

A pure function. Standard library only. No I/O, no network, no model loading. Backend imports it without any ML dependency and manual verification tests it in seconds.

```python
svi.compute(dimension_scores, confidences, quality)
    -> {svi, band, needs_human, breakdown, overrides_applied}
```

## Dimensions and provisional weights

| Dim | Meaning | Weight |
|---|---|---|
| D1 | Immediate safety threat | 0.22 |
| D2 | Crisis / self-harm language | 0.18 |
| D3 | Fear, intimidation, threats | 0.13 |
| D4 | Acute distress (acoustic + emotional) | 0.12 |
| D5 | Trauma-associated indicators | 0.08 |
| D6 | Social isolation, boycott, displacement | 0.08 |
| D7 | Medical urgency | 0.08 |
| D8 | Legal urgency | 0.06 |
| D9 | Communication safety (cannot speak freely) | 0.05 |

`SVI = Σ(weight_i × score_i)`, each score 0–100.

**Bands:** 0–29 Low · 30–54 Moderate · 55–74 High · 75–100 Critical.

## Hard overrides — rules beat weights

- Confirmed D1 or D2 above threshold ⇒ band = **Critical**, regardless of the weighted sum. A weighted average must never dilute an explicit statement of danger.
- Aggregate confidence < 0.45, or audio quality poor, or language confidence low ⇒ return `needs_human: true` and **no score**. Abstention is a first-class output, not an error.
- Consent declined ⇒ scoring suppressed entirely.

Every override applied is returned in `overrides_applied` so the console can display why the band is what it is.

## Presentation contract

The composite number is never displayed alone — the breakdown and the confidence travel with it, and every dimension carries the evidence turn ids that produced it. The weights are labelled in the interface as **provisional, pending expert calibration**. Do not remove that label.

## Trajectory

Recompute per assessment cycle. Every band change stores the utterance that caused it, so the trajectory chart is clickable. This is one of the most convincing thirty seconds of the demo — do not let it degrade into a plain line chart.

## Testing

Cover: weight arithmetic, each band boundary, each override firing, abstention paths, missing-modality behaviour (text-only chat sessions where D4 is not applicable — the remaining weights renormalise, and this must be tested explicitly).
