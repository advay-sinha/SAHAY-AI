# Review packet — D5 lexicon v1.1: anxiety and low-mood indicators

| Field | Value |
|---|---|
| Change | `ml/nlp/lexicons.py` D5 entries added; `LEXICON_VERSION = "detectors-v1.1-draft"` |
| Why | The Problem Statement asks for stress, anxiety and depression indicators. D5 covered only sleep loss, flashbacks and shaking. The new terms add anxiety and low-mood phrasing as **linguistic indicators under the existing D5 label**, never as a diagnosis. There is no contract change. |
| Status | **DRAFT: written and tested, not yet reviewed by a human.** Two reviewers are required, one of them a native Hindi reader. Record the decision below and change the version suffix to `-reviewed`. |

## 1. What was added

| Language | Tier 2 (explicit) | Tier 1 (weaker) |
|---|---|---|
| English | panic attack(s), heart keeps racing, can't / cannot stop worrying, constantly worried, lost interest in everything, stopped eating, can't eat, cry every day, crying every day, cry all the time, feel numb, feel empty | anxious, on edge, can't / cannot concentrate, feel low, feeling low, no energy |
| Hinglish | ghabrahat, dil ghabrata, dil baith, bechaini, man / mann nahi lagta, kuch accha / acha nahi lagta, rota rehta, roti rehti, roz rota, roz roti, bhookh / bhook nahi, khana nahi kha pa, himmat toot | tension mein, tension ho rahi, chinta hoti, chinta lagi, chinta mein, dimaag kaam nahi |
| Hindi | घबराहट, दिल घबराता, दिल बैठ, बेचैनी, मन नहीं लगता, कुछ अच्छा नहीं लगता, रोता रहता, रोती रहती, रोज़ / रोज रोती, भूख नहीं, खाना नहीं खा पा, हिम्मत टूट | टेंशन में, टेंशन हो रही, चिंता होती, चिंता लगी, चिंता में, दिमाग काम नहीं |

The maximum tier is 2. Tier 3 stays reserved for other dimensions. D5 carries weight 0.08, so a single tier-2 hit contributes at most about 5 SVI points.

## 2. Deliberately NOT added (reviewer, please confirm)

- **Hopelessness wording** ("hopeless", "no point", "koi fayda nahi", "कोई फायदा नहीं"). It is crisis-adjacent, and the crisis lexicon alone owns D2. Whether these belong in the crisis lexicon is a **counsellor's decision**; they were not added anywhere.
- **Bare "tension", "chinta", "pareshan".** They are too generic: "chinta mat karo" (said to the victim), "tension mat lo", and "police ne pareshan kiya" (meaning harassed). Only first-person forms such as "chinta hoti" and "tension mein" were added.
- **Diagnostic words** (depression, PTSD, disorder, trauma). SAHAY never diagnoses, and a test enforces this.

## 3. Evidence

- `ml/tests/test_d5_anxiety_low_mood.py` covers:
  - positives in all three languages;
  - negation cancelling a hit ("I don't have panic attacks", "मुझे घबराहट नहीं होती");
  - 7 near-misses that must not fire;
  - zero overlap with the crisis lexicon in either direction;
  - low-mood sentences never triggering the crisis pre-check, while a real crisis sentence still does;
  - no diagnostic words.
- **The exposed dev, candidate and red-team evaluation is unchanged (0 fields changed, before against after, 2026-09-27).** None of those fixtures contain anxiety or low-mood phrasing. So these terms are **untested on corpus evidence**. The next blind-corpus coverage plan (v2, which needs lead approval) should require anxiety and low-mood scenarios, including negated and attributed forms.

## 4. Risks

- **False positives:**
  - Attributed speech ("she said she cries every day") will fire, because D5 has no attribution handling. The effect is limited (tier 2, weight 0.08), but the reviewer should judge it.
  - "no energy" and "on edge" may appear in non-emotional contexts.
- **False negatives:** regional and spelling variants ("ghabrahat" / "ghabrahut", "bechaini" / "bechainee") and indirect phrasing are not covered.
- **Negation scope** follows the existing D5 rule: the same clause, within 18 characters. Long negated sentences may still fire.

## 5. Reviewer checklist

- [ ] I read every term in §1. Each is first-person anxiety or low-mood phrasing, not a diagnosis, not crisis language.
- [ ] A native Hindi reader checked the Hindi and Hinglish terms for meaning and register.
- [ ] I agree with the exclusions in §2, or I recorded which should change and why.
- [ ] I ran `python -m pytest ml/tests/test_d5_anxiety_low_mood.py` myself.
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
