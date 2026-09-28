# Component card — output validator (guardrails)

| Field | Value |
|---|---|
| Component | `ml/guardrails/validator.py` (`guardrails-v1.1`) with output rules `lexicons/output_rules.py` (`output-rules-1.1-unreviewed`) |
| Role | Checks every generated sentence before it can be spoken or shown to a victim. On failure the pre-written fallback is used, never a repaired version of the model's sentence. |
| Type | Deterministic phrase rules: 87 rules in English, Hindi and Hinglish, plus the licensed-question checks. Standard library only. |
| Default path | `LLM_PROVIDER=mock`. No generated text exists and victims only receive pre-written text, which is validated too. |

## What it refuses

Every refusal category is covered in English, Hindi and Hinglish:
- assessment leaks (score, band, priority);
- diagnosis;
- promises;
- legal conclusions;
- advice outside scope;
- leading questions;
- minimising;
- victim blame;
- discouraging escalation;
- role-play;
- instruction residue and prompt injection;
- quoted threats.

## Measured

- **Red-team:** 39 of 39 cases blocked before synthesis (English 23, Hindi 7, Hinglish 9). This is **exposed regression evidence**: the 19 original failures were fixed after they were published. See `docs/defence/RED_TEAM.md`.
- **Near-miss and paraphrase cases** written alongside the rules also pass. They are development evidence, not holdout evidence.

## Limits (tested and documented)

- **Bare numbers.** A bare number cannot be told apart from a case reference, so none is blocked. The planned fix is structural (P-BND-1): the phrasing adapter would never receive assessment data.
- **Licensed questions.** The validator checks that a question is present, not that it is the licensed question (P-GR-2).
- **Review status.** The rules are unreviewed until two human reviewers sign them off.
