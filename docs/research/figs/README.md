# Figure sources for the whole-deck report

Editable diagram sources for two figures in `docs/research/whole-deck-report.pdf`. The PDF itself
draws them in TikZ; these files exist so the same diagrams can be edited in Lucidchart or
diagrams.net for slides.

| File | Report figure | Section |
|---|---|---|
| `prompt-figure1-system-architecture.md` | Figure 1 — prompts, self-contained | §4.1 |
| `prompt-figure4-case-lifecycle.md` | Figure 4 — prompts, self-contained | §5.6 |
| `figure1-system-architecture.drawio` / `.xml` | Figure 1 — exact editable original | §4.1 |
| `figure4-case-lifecycle.drawio` / `.xml` | Figure 4 — exact editable original | §5.6 |

## Two ways to use this folder

- **Generate a new diagram (no file needed):** open the matching `prompt-*.md` and paste one block
  into Lucid AI, Claude, ChatGPT, Whimsical, Miro AI, Napkin, Eraser or a Mermaid renderer. Each pack
  starts with a plain-English explanation of what the figure argues, then gives a complete build
  specification — every box, its text, its colour, the grid position, every connector with its label
  and routing, the legend and the captions. Nothing has to be imported or attached.
- **Edit the exact original:** import the `.drawio` file, or the identical `.xml` copy if your
  importer only lists `.xml` (Lucid's draw.io importer often does). Both files hold the same diagram.

Each prompt pack ends with accuracy rules and a verification checklist. They exist because this is
the point where a prettier diagram could quietly overstate what the MVP does — drawing the telephony
stub as connected, or the shadow model as live, or letting a band override appear to reach the
complainant.

## Importing into Lucidchart

1. In Lucidchart: **File → Import Diagram → draw.io**, then choose the `.drawio` file.
2. Everything arrives positioned, coloured and connected. Lucid maps draw.io rounded rectangles,
   fills, dashed strokes and orthogonal connectors directly.
3. Two things usually need a look after import: connector label placement, and the over-the-top
   return connector in Figure 1 (`LLM phrasing → Expo victim app`), whose waypoints Lucid may
   re-route. Its waypoints are y = 50 across the top of the canvas.

They also open unchanged in [diagrams.net](https://app.diagrams.net) (**File → Open From → Device**)
and in the VS Code Draw.io extension.

## What the colours mean

The palette is the report's, and it carries meaning — keep it if you re-style.

| Colour | Border / fill | Meaning |
|---|---|---|
| Blue | `#1F4E79` / `#EAF1F8` | Normal system component, or a case state |
| Red | `#B3261E` / `#FBEBEA` | Safety-critical: the synchronous crisis pre-check |
| Green | `#2E7D32` / `#EAF3EB` | Human-facing surface, or an action a human officer takes |
| Purple | `#6A3D9A` / `#F1ECF7` | Storage, and the victim-safe timeline |
| Gray, dashed | `#5F6368` / `#F1F2F3` | Not connected in the MVP, or research-only |

**Dashed means not wired up.** In Figure 1 that is the telephony/IVRS adapter stub (needs
departmental approval, a licensed operator and DLT registration) and the MuRIL shadow model
(`rejected_for_product_integration`, research CLI only). Drawing them solid would overstate what the
MVP does.

## Figure 1 — what it argues

Two paths and one guard:

- the **reply path** is synchronous and fronted by the crisis pre-check, which runs before dialogue
  policy on every utterance;
- the **assessment path** runs in parallel, so no model can delay a reply;
- **role-filtered fan-out** happens server-side, so no score, band, dimension or alert can reach a
  victim client.

Layout: five columns at x = 40 / 300 / 560 / 820 / 1080, four rows at y = 110 / 230 / 360 / 500,
boxes 190 × 80.

## Figure 4 — what it argues

The case moves `open → claimed → taken_over → closed`, and every transition after the first is a
human action. The green boxes are what the claiming officer can do in each state; all of them are
executive-only, and a supervisor token gets 403. Only the purple path reaches the complainant, and
only a confirm or modify produces the `action_taken` step — an AI recommendation alone never does.

Layout: four columns at x = 40 / 320 / 600 / 880, states at y = 80 (200 × 70), actions at y = 250
(220 × 60), timeline box at (320, 400), 560 × 80.

## Keeping these in step with the report

If a figure changes in `whole-deck-report.tex`, change it here too, or delete the stale file. A
diagram that disagrees with the report is worse than no diagram.
