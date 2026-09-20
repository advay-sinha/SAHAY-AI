# Prompt pack — Figure 1, SAHAY-AI system architecture

Self-contained. Every prompt below describes the figure completely, so nothing else needs to be
opened, imported or attached. Paste one block into Lucid AI, Claude, ChatGPT, Whimsical AI, Miro AI,
Napkin, Eraser or any Mermaid renderer.

> If you would rather edit the exact original, this folder also holds
> `figure1-system-architecture.drawio` and an identical `.xml` copy — some importers only list
> `.xml`. Neither file is needed for the prompts below.

---

## What this figure shows, in plain English

SAHAY-AI takes a distressed person's first contact with the helpline and turns it into a
decision-ready case for a human officer, without ever letting a model speak freely or decide
anything.

The diagram makes four claims at once:

1. **Contact arrives on several channels.** A victim mobile app and a portal chat are live. A
   telephony / IVRS adapter exists as a documented stub only — it is not connected, because live
   14566 integration needs departmental approval, a licensed operator and DLT registration.
2. **The reply path is guarded and synchronous.** Everything the caller says passes a crisis
   pre-check *before* any dialogue policy runs. Only then does a deterministic 12-state machine pick
   one approved intent, a language model phrases that single intent, a validator checks the sentence,
   and speech synthesis speaks it. The reply returns to the victim app within a sub-3-second budget.
3. **The assessment path runs in parallel and never blocks a reply.** The same turn is queued to
   detectors that score nine dimensions with evidence links, then to the index engine that applies
   hard overrides and abstains when uncertain, then into recommendations and an escalation packet
   which persist to the database and surface in the executive console.
4. **Nothing assessment-shaped can reach the caller.** Role filtering happens server-side: no score,
   band, dimension or alert is ever sent to a victim client. Separately, a trained shadow model reads
   turns for research only and changes nothing.

Colour and line style carry meaning: red is the safety guard, green is a human-facing surface, purple
is storage, and **dashed means not wired into the product** — the telephony stub and the shadow
model. Drawing either of those as live would overstate what the system does.

---

## 1. Universal prompt — complete build specification

```text
Create a clean, presentation-grade system architecture diagram titled "SAHAY-AI system architecture".
16:9 canvas, white or near-white background, strictly left-to-right flow, generous whitespace.

CONTEXT, so the layout reflects the meaning: this system handles first contact from victims calling a
government helpline. It has a guarded synchronous "reply path" that talks to the caller, and a
parallel "assessment path" that scores vulnerability for a human officer. Two components are drawn
dashed because they are deliberately NOT connected in the current build.

Lay the diagram out on a five-column, four-row grid. Boxes are rounded rectangles, about 190 wide by
80 tall, 8 px corner radius, 1.5 px border, pale fill, bold first line and a lighter subtitle line.

COLUMN 1 (far left) - clients, three boxes stacked:
  ROW 1: "Expo victim app" / "consent, talk, chat, timeline"        green border #2E7D32, fill #EAF3EB
  ROW 2: "Portal chat" / "text channel"                             green border #2E7D32, fill #EAF3EB
  ROW 3: "Telephony / IVRS adapter stub" / "not connected"          grey #5F6368, fill #F1F2F3, DASHED

COLUMN 2, ROW 2 - the gateway, slightly taller:
  "Session gateway - FastAPI" / "auth, consent, turn orchestration"  blue #1F4E79, fill #EAF1F8

COLUMN 3:
  ROW 1: "Crisis pre-check" / "synchronous, before dialogue policy"  RED #B3261E, fill #FBEBEA
  ROW 3: "Detectors" / "D1-D9 + extraction"                          blue
  ROW 4: "MuRIL shadow model" / "research CLI only"                  grey, DASHED

COLUMN 4:
  ROW 1: "Dialogue FSM" / "12 states"                                blue
  ROW 3: "SVI engine" / "overrides, abstention"                      blue
  ROW 4: "Supabase PostgreSQL" / "15 tables, TLS only"               purple #6A3D9A, fill #F1ECF7

COLUMN 5 (far right):
  ROW 1: "LLM phrasing + validator + TTS"                            blue
  ROW 3: "Recommendations + escalation packet"                       blue
  ROW 4: "Executive console" / "queue, packet, decisions, audit"     green

BAND LABELS - small bold uppercase text, left-aligned, above the row it names, colour #1F4E79,
optionally over a very pale tinted band background:
  above ROW 1, at the far left:          "CLIENTS"
  above ROW 1, from column 3 rightwards: "REPLY PATH (synchronous, sub-3 s budget)"
  above ROW 3, from column 3 rightwards: "ASSESSMENT PATH (parallel, never blocks a reply)"
  above ROW 4, from column 3 rightwards: "RESEARCH ONLY, OUTSIDE THE PRODUCT"  (grey #5F6368)

CONNECTORS - orthogonal, 1.5 px, colour #4D4D4D, small solid arrowheads, no crossings:
  1.  Expo victim app            -> Session gateway
  2.  Portal chat                -> Session gateway
  3.  Telephony / IVRS stub      -> Session gateway   DASHED grey, label "not connected in the MVP"
  4.  Session gateway            -> Crisis pre-check
  5.  Crisis pre-check           -> Dialogue FSM
  6.  Dialogue FSM               -> LLM phrasing + validator + TTS
  7.  LLM phrasing + validator + TTS -> Expo victim app, routed UP and OVER the top of the whole
      diagram and back down into the app, label "assistant turn to the victim"
  8.  Session gateway            -> Detectors, routed down then right, label "queued, parallel"
  9.  Detectors                  -> SVI engine
  10. SVI engine                 -> Recommendations + escalation packet
  11. Recommendations + escalation packet -> Executive console  (straight down)
  12. Recommendations + escalation packet -> Supabase PostgreSQL (down then left)
  13. Supabase PostgreSQL        -> Executive console
  14. Detectors                  -> MuRIL shadow model  DASHED grey, label "shadow only, changes nothing"

CAPTION between row 3 and row 4, under columns 4 and 5, italic, red #B3261E:
  "role-filtered fan-out: no score, band, dimension or alert ever reaches a victim client"

LEGEND bottom-left, small grey text, two lines:
  "solid = live path in the MVP  |  dashed = not connected (telephony) or research-only (shadow model)"
  "red = safety-critical  |  green = human-facing surface  |  purple = storage"

STYLE: one sans-serif family throughout, flat vector, no drop shadows, no 3D, no gradients, no
clip-art, no cloud-vendor logos. Exactly 13 boxes and 14 connectors. Do not add components that are
not listed, do not rename anything, and keep the two dashed boxes dashed.
```

---

## 2. Mermaid prompt — complete, paste-and-render

```text
Produce a Mermaid flowchart LR diagram of the architecture described below, then colour it with
classDef. It shows a government helpline intake system: a guarded synchronous reply path, a parallel
assessment path, and two components that are deliberately not connected.

subgraph Clients
  app["Expo victim app<br/>consent, talk, chat, timeline"]
  portal["Portal chat<br/>text channel"]
  ivrs["Telephony / IVRS adapter stub<br/>not connected"]
end
subgraph Reply path - synchronous, sub-3 s budget
  gw["Session gateway - FastAPI<br/>auth, consent, turn orchestration"]
  pre["Crisis pre-check<br/>synchronous, before dialogue policy"]
  fsm["Dialogue FSM<br/>12 states"]
  val["LLM phrasing + validator + TTS"]
end
subgraph Assessment path - parallel, never blocks a reply
  det["Detectors<br/>D1-D9 + extraction"]
  svi["SVI engine<br/>overrides, abstention"]
  pkt["Recommendations + escalation packet"]
end
subgraph Storage and research
  db[("Supabase PostgreSQL<br/>15 tables, TLS only")]
  con["Executive console<br/>queue, packet, decisions, audit"]
  shadow["MuRIL shadow model<br/>research CLI only"]
end

app --> gw
portal --> gw
ivrs -. "not connected in the MVP" .-> gw
gw --> pre --> fsm --> val
val -- "assistant turn to the victim" --> app
gw -- "queued, parallel" --> det
det --> svi --> pkt
pkt --> con
pkt --> db
db --> con
det -. "shadow only, changes nothing" .-> shadow

Styling: pre gets stroke #B3261E fill #FBEBEA; app, portal and con get stroke #2E7D32 fill #EAF3EB;
db gets stroke #6A3D9A fill #F1ECF7; ivrs and shadow get stroke #5F6368 fill #F1F2F3 with
stroke-dasharray 6 4; every other node gets stroke #1F4E79 fill #EAF1F8. Keep the two dotted edges
dotted. Add a note reading "role-filtered fan-out: no score, band, dimension or alert ever reaches a
victim client".
```

---

## 3. Diagram-as-code prompt (Eraser.io, Structurizr, D2)

```text
Write a cloud-architecture diagram as code for an AI-assisted government helpline intake system, in
four labelled groups.

Group "Clients": Expo victim app (consent, talk, chat, timeline); Portal chat (text channel);
Telephony / IVRS adapter stub, styled dashed and greyed because it is not connected.
Group "Reply path (synchronous, sub-3 s budget)": Session gateway - FastAPI (auth, consent, turn
orchestration); Crisis pre-check (synchronous, before dialogue policy), styled red as the safety
control; Dialogue FSM (12 states); LLM phrasing + validator + TTS.
Group "Assessment path (parallel, never blocks a reply)": Detectors D1-D9 + extraction; SVI engine
(overrides, abstention); Recommendations + escalation packet.
Group "Storage, console and research": Supabase PostgreSQL (15 tables, TLS only); Executive console
(queue, packet, decisions, audit); MuRIL shadow model (research CLI only), styled dashed and greyed.

Connections: both live clients into the gateway; the telephony stub into the gateway as a dashed
"not connected" link; gateway to pre-check to FSM to phrasing; phrasing back to the victim app
labelled "assistant turn to the victim"; gateway to detectors labelled "queued, parallel"; detectors
to SVI engine to escalation packet; packet to console and to the database; database to console;
detectors to the shadow model as a dashed "shadow only, changes nothing" link.

Icons where they fit: mobile app, web chat, phone, server, shield, state machine, speech, analytics,
gauge, clipboard, database, dashboard, flask. Add the caption "role-filtered fan-out: no score, band,
dimension or alert ever reaches a victim client".
```

---

## 4. Image-model prompt — cover art only, never the real diagram

Image models garble small text; use this for a slide background, not for the architecture itself.

```text
A clean, minimal enterprise architecture illustration on an off-white background: three horizontal
lanes of rounded rectangles connected by thin orthogonal arrows flowing left to right, with two boxes
drawn in dashed outline. Muted palette of deep navy, sage green and soft purple with a single red
accent box. Flat vector style, generous whitespace, subtle lane tints, no text, no logos, no people,
no 3D, no gradients. Editorial quality, suitable as the background of a government technology report.
```

---

## Accuracy rules — apply to every block above

1. **Dashed stays dashed.** The telephony / IVRS adapter is a documented stub with no live
   connection; the MuRIL shadow model is rejected for product integration and runs in a research CLI.
   Drawing either as live misrepresents the system.
2. **The crisis pre-check sits before the dialogue FSM**, never beside or after it. That position is
   the safety argument: it runs on every utterance before any policy or model decision.
3. **The assessment path must branch off the gateway**, not sit in the reply chain. That separation
   is why a slow model cannot delay a reply to a distressed caller.
4. **Keep the fan-out caption.** "No score, band, dimension or alert ever reaches a victim client" is
   an enforced, tested property.
5. **Invent nothing.** No Redis, Kafka, load balancer, vector database, cloud logo or generic "AI
   engine" box. Thirteen boxes exactly.
6. **Rename nothing upwards.** "Detectors D1-D9" is not a "neural risk engine"; "SVI engine" is not
   "AI scoring".

## Check the result before you use it

- 13 boxes, 14 connectors.
- The telephony stub and the shadow model are still dashed and grey.
- A return arrow reaches the victim app; without it the conversation loop is not closed.
- The red pre-check box sits between the gateway and the FSM.
- The only things touching the victim app are the gateway link and the assistant-turn return.
