# Prompt pack — Figure 4, case lifecycle and officer actions

Self-contained. Every prompt below describes the figure completely, so nothing else needs to be
opened, imported or attached.

> The exact original is also here as `figure4-case-lifecycle.drawio` with an identical `.xml` copy,
> since some importers only list `.xml`. Neither file is needed for the prompts below.

---

## What this figure shows, in plain English

Once the intake conversation produces a case, this is what happens to it — and who is allowed to do
what.

A case sits in one of four states. It starts `open` in a band-ranked queue. An officer **claims** it,
which makes them the one person accountable for it. They may then **take over** the live session,
which mutes the assistant so the officer speaks to the complainant directly. Finally the case is
**closed**. Every one of those transitions is a human action; the system performs none of them by
itself.

Hanging beneath the states are the four things an officer can actually do. While the case is
`claimed` they can acknowledge a safety alert (recorded against their name, idempotent, so a repeat
changes nothing), confirm, modify or reject each AI-proposed support pathway, and override the
priority band — for which a written reason is mandatory and enforced. Once they have taken over, they
can message the complainant directly; that text is theirs, never generated or rephrased by AI.

At the bottom sits the only thing the complainant ever sees: a victim-safe timeline of plain-language
process steps. Just two actions feed it — a confirm or modify, and an officer message. An
acknowledgement or a band override deliberately changes nothing on the complainant's screen, and the
timeline never names a pathway, a band or a score.

So the figure exists to prove three things: the machine decides nothing, authority is traceable to
one named officer, and the information reaching the complainant is narrow and deliberate.

---

## 1. Universal prompt — complete build specification

```text
Create a clean, presentation-grade process diagram titled "Case lifecycle and officer actions".
16:9 canvas, white background, generous whitespace, three tiers stacked vertically.

CONTEXT so the layout carries the meaning: this shows a helpline case moving through four states
where every transition is performed by a human officer, the actions each state permits, and the one
narrow channel of information that reaches the complainant.

TIER 1 - CASE STATES. Four rounded boxes in a left-to-right row, evenly spaced, roughly 200 wide by
70 tall, blue border #1F4E79 on fill #EAF1F8. Put the state name on the first line in MONOSPACE bold
and the subtitle beneath in the body font:
  1. "open"        / "in the queue"
  2. "claimed"     / "by one officer"
  3. "taken_over"  / "assistant muted"
  4. "closed"
Join them with three labelled arrows, left to right: "claim", then "takeover", then "close".
Above this tier, small bold label in #1F4E79:
  "CASE STATE - every transition after the first is a human action"

TIER 2 - OFFICER ACTIONS. Four rounded boxes in a row directly beneath the states, roughly 220 wide
by 60 tall, green border #2E7D32 on fill #EAF3EB, bold first line and lighter second line:
  5. "alert acknowledged"        / "idempotent, audited"
  6. "confirm / modify / reject" / "each recommendation"
  7. "band override"             / "reason mandatory"
  8. "officer message"           / "to the complainant"
Above this tier, small bold label in #2E7D32:
  "OFFICER ACTIONS - executive tokens only; a supervisor token is read-only and gets 403"

CONNECT STATES TO ACTIONS so ownership is unmistakable:
  - THREE arrows fan out from a single point on the BOTTOM EDGE of "claimed" to boxes 5, 6 and 7.
    Draw them from the same origin point so the fan reads as "these three powers belong to the
    officer who claimed this case". Do not draw them as four parallel vertical lines.
  - ONE arrow from the bottom of "taken_over" down to box 8.

TIER 3 - WHAT THE COMPLAINANT SEES. One wide box, centred beneath the action row, roughly 560 wide by
80 tall, purple border #6A3D9A on fill #F1ECF7, three lines:
  "victim-safe timeline"
  "request received -> under review -> officer assigned -> action taken -> follow-up scheduled -> closed"
  "plain language, no pathway, no score"
EXACTLY TWO arrows reach it, both drawn in purple #6A3D9A: one from box 6 (confirm / modify / reject)
and one from box 8 (officer message). Nothing else connects to it.

CAPTION directly beneath the timeline box, small grey italic:
  "only a human confirm or modify adds the \"action taken\" step"

LEGEND bottom-left, small grey text:
  "blue = case state  |  green = action a human officer takes  |  purple = the only path that reaches
  the complainant"

STYLE: rounded rectangles with 6-8 px radius, 1.5 px borders, pale fills, one sans-serif family
throughout with monospace reserved for the four state names, connectors #4D4D4D at 1.5 px with small
solid arrowheads, no crossing lines, no drop shadows, no 3D, no clip-art.

Exactly 4 state boxes, 4 action boxes, 1 timeline box, 9 connectors. Do not add states, do not
connect anything else to the timeline, and keep the state names lowercase with underscores.
```

---

## 2. Mermaid prompt — complete, paste-and-render

```text
Produce a Mermaid flowchart TD diagram of the process below and colour it with classDef. It shows a
helpline case lifecycle where every transition is a human action.

subgraph Case state - every transition after the first is a human action
  s1["open<br/>in the queue"]
  s2["claimed<br/>by one officer"]
  s3["taken_over<br/>assistant muted"]
  s4["closed"]
end
subgraph Officer actions - executive tokens only, a supervisor gets 403
  a1["alert acknowledged<br/>idempotent, audited"]
  a2["confirm / modify / reject<br/>each recommendation"]
  a3["band override<br/>reason mandatory"]
  a4["officer message<br/>to the complainant"]
end
subgraph What the complainant sees
  tl["victim-safe timeline<br/>request received, under review, officer assigned, action taken,
  follow-up scheduled, closed<br/>plain language, no pathway, no score"]
end

s1 -- "claim" --> s2
s2 -- "takeover" --> s3
s3 -- "close" --> s4
s2 --> a1
s2 --> a2
s2 --> a3
s3 --> a4
a2 --> tl
a4 --> tl

Styling: s1 to s4 stroke #1F4E79 fill #EAF1F8; a1 to a4 stroke #2E7D32 fill #EAF3EB; tl stroke
#6A3D9A fill #F1ECF7, and colour the two edges entering tl purple. Add a note reading: only a human
confirm or modify adds the "action taken" step. Do not connect a1 or a3 to tl.
```

---

## 3. State-machine flavour (PlantUML, Lucid state diagram, Structurizr)

```text
Draw a UML-style state machine for a helpline case, plus the actions each state permits.

States: open, claimed, taken_over, closed.
Transitions: open -> claimed [claim]; claimed -> taken_over [takeover]; taken_over -> closed [close].
Annotate on the diagram that every transition is triggered by a human officer, never by the system.

Internal actions attached to "claimed": acknowledge alert (idempotent, audited); confirm, modify or
reject each recommendation; band override (written reason mandatory).
Internal action attached to "taken_over": message the complainant (the officer's own words, never AI
generated). Mark all four "executive tokens only - a supervisor token is read-only and gets 403".

Add one external artefact, "victim-safe timeline", showing the stages request received, under review,
officer assigned, action taken, follow-up scheduled, closed. It receives updates from exactly two
actions - confirm/modify and officer message - and carries no score, band or pathway name.
```

---

## 4. Image-model prompt — cover art only

```text
A minimal flat-vector process illustration on an off-white background: a horizontal row of four
rounded boxes joined by thin arrows, a second row of four smaller boxes beneath with three connector
lines fanning out from a single point on one box above, and one wide soft-purple box below receiving
two lines. Muted navy, sage green and lavender palette, generous whitespace, no text, no logos, no
3D, no gradients. Clean editorial style for a government technology report.
```

---

## Accuracy rules — apply to every block above

1. **The fan matters.** Three arrows leaving one point on `claimed` says those powers belong to the
   claiming officer. Four parallel lines lose that meaning.
2. **Only two arrows may touch the timeline.** If a generator links `band override` or `alert
   acknowledged` to it, delete those edges. Both deliberately change nothing the complainant sees.
3. **Never label the timeline with a pathway, band or score.** Its labels are process facts in plain
   language: "an officer has taken action on your request", never "counselling pathway initiated".
4. **Keep "reason mandatory" on the band override.** The written reason is enforced at the endpoint
   and in the database, and it is one of the project's accountability claims.
5. **Keep state names lowercase with underscores, in monospace** — `open`, `claimed`, `taken_over`,
   `closed`. They are enumerated values in a frozen contract, not prose.
6. **Add no states.** No "escalated", "pending", "reopened" or "resolved". Four states.
7. **No arrow may show the system making a transition.** Every tier-1 arrow is a human action.

## Check the result before you use it

- 4 states, 4 actions, 1 timeline box, 1 caption, 1 legend.
- 9 connectors: 3 state transitions, 4 state-to-action, 2 action-to-timeline.
- `taken_over` is the only state connected to "officer message" — messaging before takeover is
  rejected by the API, and the diagram must not suggest otherwise.
- Nothing except confirm/modify and officer message touches the timeline.
