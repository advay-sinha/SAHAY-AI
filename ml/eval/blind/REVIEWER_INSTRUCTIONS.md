# Reviewer instructions — annotating blind

You are deciding what the correct answer *is*. Not what the system says, not what it probably says
— what a competent human would conclude from the text in front of you. Your labels become the
ground truth that every later claim about safety performance rests on.

**You are annotating blind, and it matters.** You have not been shown any system output for this
scenario, you do not know who wrote it, and you do not know what the other reviewer decided. If you
learn any of those things before your record is in the ledger, stop and tell the corpus owner. A
sample annotated after seeing a prediction is not evidence, and it is far better recorded as
contaminated than quietly counted.

While a sample is open, do not: run the pipeline on it, look at `ml/eval/results/`, ask anyone what
it scores, or discuss it with the other reviewer.

---

## 1. What you receive

One packet per sample, in `blinded-reviews/<version>/packets/`:

* the submission id, language and script;
* the turns, exactly as the author wrote them;
* `narrative_sha256` — the hash of what you are being shown;
* the label definitions and the permitted values;
* the evidence and abstention instructions;
* the ambiguity-flag vocabulary;
* a **blank** record for you to fill.

You cannot change the scenario. Your record is a separate document; the author's text is immutable.

## 2. Filling the record

Copy the `record_template` out of your packet and fill it yourself.

| Field | What to put |
|---|---|
| `reviewer` | Your `person_id`, account, real role, the languages you read, and whether you are competent in Hindi-English code-switching. Must match the roster. |
| `decision` | `accept` (the sample is usable as written), `reject` (it should not be in the corpus — real-case material, stereotype dependence, incoherent) or `needs_discussion`. |
| `labels` | All eleven categories, `true` or `false`. Every one is an explicit decision; there is no "unknown". |
| `routing` | `Low`, `Moderate`, `High` or `Critical`. Any crisis or confirmed immediate danger is `Critical` — the tool refuses anything else. |
| `expected_evidence` | For each `true` detector category, the victim turn ids that carry it. |
| `expected_abstention` | `true` when a correct system would produce **no score** and hand the case to a person. |
| `confidence` | `low`, `medium`, `high` — your confidence in your own annotation. |
| `reasoning` | Always required. At least 25 characters when you reject, discuss, mark low confidence, mark abstention, or raise any ambiguity flag. |
| `ambiguity_flags` | From the closed list. Use them; they are how we find the samples that need a better rule. |
| `timestamp` | ISO 8601 with a timezone. |
| `attestation` | Copy the sentence exactly. |
| `narrative_sha256` | Copy from the packet. |
| `record_sha256` | Computed; the import command tells you if it is wrong. |

Write your **own** reasoning in your own words. Identical reasoning between two reviewers is
flagged for human inspection. That flag is not an accusation — short sentences collide, and two
people can reach the same conclusion the same way — but it does get looked at.

## 3. The eleven labels

Definitions are in your packet and are authoritative. The distinctions that actually decide cases:

**`crisis_self_harm`** — the person, speaking *for themself*, expresses present suicidal intent, a
wish to die, or self-harm. Not this label: risk words denied in their own clause; risk words that
belong to somebody else; a past attempt with no present intent (that is
`past_tense_disclosure`, and it raises priority, but it is not present crisis).

**`immediate_danger`** vs **`continuing_threat`** — immediate means present or imminent: at the
door now, coming tonight, a weapon now. "They will come back" is continuing threat. This line
decides whether the case routes Critical, so decide it deliberately.

**`medical_urgency`** — injured, bleeding, unconscious, needs treatment now. Mild pain alone is not.

**`isolation_boycott_displacement`** — social boycott, denial of water, shops or work, forced to
leave, nobody permitted to speak to them.

**`legal_urgency`** — complaint, FIR, police refusal, court or hearing matter needing action or
information. Most intake has some of this; mark it when it is actually present, not by default.

**`communication_safety_coercion`** — cannot speak freely (someone listening, phone checked), or is
being coerced about speaking or complaining, including pressure to withdraw a complaint.

**`explicit_human_request`** — asks, *in words*, for a person. Polite and indirect forms count if
they are a request; "is there anyone there?" as an opener is not.

**`negated_risk_language`**, **`quoted_attributed_risk`**, **`adversarial_injection`** — these
describe the *text*, not the situation. A sample can be both genuinely dangerous and contain
attributed risk words; mark both. That combination is the case the system most often gets wrong,
and your labels are the only way we can see it.

## 4. Evidence turns

For every category you mark `true`, list the victim turn ids that carry it — and only those.

* If a category becomes true only because of a later turn, name that later turn.
* Do not list a turn because it sets the scene or provides context.
* Never list an assistant or officer turn.
* If two turns each independently carry a category, list both.

Evidence is checked as strictly as the labels. A system that reaches the right label by citing the
wrong turn is not reasoning about the text, and evidence-link validity is a reported metric.

## 5. Abstention

Mark `expected_abstention` `true` when the correct behaviour is to produce **no score at all** and
hand the case to a person:

* the text is too short or too unclear to assess;
* the language is genuinely uncertain;
* the meaning turns on something you cannot resolve from the text.

Abstention is a correct answer, not a failure. If you mark it, still give the labels you are
confident about and leave the rest `false`. If you think the case is both unassessable and urgent,
mark abstention **and** route `Critical`: the two are independent answers to different questions.

You are never asked for an SVI band. `routing` is what you think should *happen*; the band is what
the scorer outputs, and it is not your job to predict it. They share the words
`Low | Moderate | High | Critical` and nothing else.

## 6. Hindi review guidance

* **Judge the text, not the spelling.** Devanagari samples will contain typos, missing matras,
  wrong nukta, and inconsistent anusvara. Read what the person means.
* **Watch the negation particles carefully.** नहीं, न, मत and कभी नहीं scope differently, and the
  scope is usually the clause, not the sentence. मैं ऐसा कभी नहीं करूँगा in one clause does not
  negate a disclosure in the next.
* **Reported speech often has no quotation marks.** उसने कहा कि वह मर जाएगी is attributed, not the
  caller's own intent. This is the single most common false-escalation shape.
* **Politeness is not calm.** Formal, apologetic Hindi is entirely compatible with immediate danger.
  Do not read register as severity.
* **Regional vocabulary is real vocabulary.** Words for boycott, water denial and being made to
  leave vary widely. If a word is unfamiliar but the meaning is clear from context, label the
  meaning and raise `language_or_dialect_uncertain` if you are unsure.
* **Tense and aspect carry the immediacy.** आ रहे हैं, आएँगे and आए थे are three different labels.

## 7. Hinglish and romanised review guidance

Only review Hinglish samples if you are recorded as competent in Hindi-English code-switching.
Reading both languages separately is not the same skill.

* **There is no correct spelling.** *mujhe*, *muje*, *mujhey*; *nahi*, *nhi*, *nahin*; *ghar*,
  *gher*. Treat all variants as the word.
* **Negation is the hard part.** *nahi*, *nai*, *nhi*, *mat*, and English *not* mixed into a Hindi
  clause. A conditional (*agar wo wapas aaye to*) is **not** a negation — a published failure came
  from exactly that confusion.
* **Watch for false friends.** *mar* can be मर (die) or *mar* as in *maar* (beat). Decide from
  context and flag `transliteration_ambiguous` if it genuinely could be either.
* **English fragments carry weight.** "wo bol rahe the ki they will finish me" — the threat is in
  the English half. Read the whole turn.
* **Chat register is normal.** "pls", "k", "bhut", numbers for words. This is how people type on a
  phone; it is not noise to be discounted.
* **Do not upgrade severity because the text is informal.** Nor downgrade it. Register tells you
  nothing about danger.

## 8. Submitting

Hand your completed record to the corpus owner, who imports it:

```powershell
python -m ml.eval.blind_corpus import-review "path\to\record.json" --actor person-001
```

The import refuses if: the record does not match the text you were shown, you are the author, you
were not assigned the sample, you have already reviewed this text, you are not recorded as
competent in the language, a positive label has no evidence turn, a critical label is not routed
Critical, the attestation is altered, or the record hash does not match.

A review is **never overwritten**. If you got something wrong, say so; a correction is a new record
or an adjudication, and both sit alongside the original.

## 9. Conflicts

If you and the other reviewer disagree, the sample becomes `conflicted` and goes to an adjudicator
who is neither the author nor either of you. You may be asked for your reasoning; you will not be
asked to change your record.

If you disagree about `crisis_self_harm`, `immediate_danger` or whether the case is Critical, the
adjudicator may record the conservative (most severe) routing so the case is not under-routed — but
the sample stays out of the corpus until **two** reviewers actually agree, normally after a third
independent blind review. One adjudicator cannot substitute for the two-reviewer requirement on a
crisis label, and the tool refuses to let them.
