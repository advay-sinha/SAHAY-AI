# Staffing required for an independent evaluation corpus

This is the blocker. The tooling is finished; the corpus cannot exist without people. The numbers
below are the minimum that satisfies the independence rules without weakening any of them.

---

## 1. The rules that set the numbers

Taken from the repository as they stand. This task did not change any of them.

1. A sample author cannot approve their own sample.
2. Authors must not see pipeline predictions.
3. Reviewers must not see pipeline predictions before the labels are frozen.
4. Crisis and immediate-danger labels require **two independent human reviewers**.
5. Other labels follow the current label schema.
6. Hindi samples need at least one Hindi-capable reviewer.
7. Hinglish samples need at least one reviewer competent in Hindi-English code-switching.
8. Conflicting critical labels need an adjudicator who did not author the sample.
9. Reviewer identity must be a real recorded human identity. TODO values, AI identities, bots and
   duplicated copied reasoning are invalid.
10. Review records use the existing hash-chained ledger.

Two consequences the tooling draws from these, both visible in the code:

* **Every sample gets two blind reviews, not just the critical ones.** Whether a sample is critical
  is only known *after* annotation — that is what blinding means. Assigning one reviewer and adding
  a second when a crisis label appears would mean the second reviewer knows the first found a
  crisis, which is no longer independent. So `REVIEWS_PER_SAMPLE = 2` throughout, and rule 4 binds
  as a check on agreement rather than as a trigger for more work.
* **An adjudicator may not be one of the reviewers in conflict.** Rule 8 states only "did not author
  the sample". Letting one side of a disagreement decide it defeats the purpose, so
  `adjudication.py` also refuses a conflicting reviewer. This is **stricter than the stated policy**
  and needs lead sign-off; it is flagged here rather than buried in code.

## 2. Minimum staffing

For the 180-sample v1 plan (60 en / 60 hi / 60 hinglish):

| Role | Minimum | Competencies required |
|---|---:|---|
| Authors | **3** | Between them: 1 writing English, 1 writing Hindi in Devanagari, 1 writing Hinglish / romanised Hindi. None may have read `ml/eval/corpus/*.json` or any report in `ml/eval/results/`. |
| Reviewers | **4** | At least 2 read Hindi. At least 2 competent in Hindi-English code-switching. At least 2 read English. None may review their own writing. |
| Adjudicator | **1** | Authored nothing in v1. Reads Hindi and English, code-switch competent. Marked `can_adjudicate`. |
| Corpus owner | **1** | Runs the commands, holds the private root, keeps the backups and the ledger heads. May be one of the reviewers, but not an author of a sample they review, and not the adjudicator. |

**Distinct humans required: 5.** One person may hold more than one role across the corpus, but never
more than one role on the *same* sample. The arithmetic that makes 5 the floor for a single sample:
1 author + 2 reviewers + 1 adjudicator = 4 distinct people, and an adjudicator who authored nothing
in the corpus cannot be one of the three authors, so a corpus where every author also reviews needs
a fifth person to adjudicate.

**Comfortable staffing is 7–8**: 3 authors, 4 reviewers, 1 dedicated adjudicator, with the corpus
owner separate. At 5 people the load per person is high enough that the two-reviewer rule starts
forcing awkward allocations, and the assignment tool will report shortfalls rather than compromise.

### Why one human with two accounts does not help

`identity.py` carries both a `person_id` (the human) and an `identity` (the account). Two roster
entries sharing a `person_id` are one human, and the allocator gives them one slot per sample.
Adding an account to satisfy the two-reviewer rule does not work, and is refused rather than
silently accepted.

## 3. Volume of human work

| Work | Quantity |
|---|---|
| Scenarios authored | **180** (60 per language) |
| Blind annotations recorded | **360** (two per sample) |
| Additional third reviews | one per critical disagreement — budget 10–20% of the critical samples |
| Adjudications | one per conflicting sample — budget 10–15% of 180, so roughly 18–27 |
| Privacy clearances | one human read per PII-screen hit |
| Contamination adjudications | one per similarity warning |

Rough effort, to be measured rather than trusted: 15–30 minutes to write a good multi-turn scenario
with a deliberate challenge slice, 5–10 minutes to annotate one blind with evidence turns and
written reasoning. That is on the order of **60–90 person-hours of authoring** and **30–60
person-hours of annotation**, plus adjudication and the owner's time. It is not an afternoon's work,
and pretending otherwise is how corpora end up generated.

## 4. Coverage constraints that affect allocation

* Language totals are hard. 60 Hindi samples need Hindi authors; 60 Hinglish samples need authors
  who write code-switched text naturally, which is a different skill from writing formal Hindi.
* Every Hindi sample needs a Hindi-reading reviewer, and it needs **two** of them. One Hindi
  reviewer is a single point of failure that the assignment tool will report as a shortfall.
* Every Hinglish sample needs two code-switch-competent reviewers. This is the binding constraint
  in practice, and the reason the minimum says "at least 2 competent in code-switching".
* `crisis_self_harm` and `immediate_danger` need 18 samples each, 6 per language. That is 36
  critical samples, each needing two agreeing reviewers, and a disagreement on any of them needs a
  third blind review before the sample can be used.

## 5. The staffing blocker, stated plainly

As of 2026-09-11 no roster exists for corpus version v1. Therefore:

* no sample can be assigned, because assignment needs a roster of real humans;
* no review can be imported, because a reviewer must be on the roster;
* no sample can become eligible, and the freeze gate refuses on coverage;
* **locked count remains 0 and official metrics remain unavailable.**

This is reported as a staffing blocker, not worked around. The policy is not weakened, the review
counts are not reduced, and no record is fabricated to make the pipeline run. If the available
humans cannot satisfy independence — for instance if only one person reads Hindi — the correct
outcome is a smaller corpus in the languages that *can* be staffed, with the shortfall stated, not
a 180-sample corpus with one reviewer signing twice.

## 6. What to do first

1. Decide the humans and their real roles. Write the roster into
   `<SAHAY_EVAL_ROOT>/assignments/v1/roster.json` using `intake/roster-template.json`; set
   `can_author`, `can_review`, `can_adjudicate` honestly, and record languages and code-switch
   competence per person.
2. `python -m ml.eval.blind_corpus roster-status` — it prints reviewers per language and will show
   immediately whether Hindi and Hinglish can be staffed with two reviewers each.
3. Give every author `AUTHOR_INSTRUCTIONS.md` and confirm, individually, that they have not read
   `ml/eval/corpus/*.json` or `ml/eval/results/*`. Anyone who has is a reviewer or an adjudicator,
   not an author.
4. Give every reviewer `REVIEWER_INSTRUCTIONS.md`, including the Hindi and Hinglish sections.
5. Allocate submission id ranges per author so ids do not collide.
6. Start with 15–20 samples end to end, freeze nothing, and read
   `python -m ml.eval.blind_corpus status` to find where the process breaks before 180 samples are
   written against it.
