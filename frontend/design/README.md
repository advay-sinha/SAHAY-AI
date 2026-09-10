# frontend/design/ — visual reference only

Stitch-generated design explorations for the helpline executive console.

## Status

**These are visual references, not specifications.** They were produced by a
design tool and have not been reviewed against the frozen contracts.

Where a design and a contract disagree, the contract wins. In order of
authority:

1. Root `CLAUDE.md` — safety invariants
2. `docs/contracts/CONTRACTS.md` — frozen interfaces
3. `docs/dialogue/STATES.md` — what the system may say
4. `frontend/CLAUDE.md` — team rules for this directory
5. these design files

Nothing here is imported, built, or served. `code.html` is a static mockup, not
a component; `screen.png` is a render of it.

## Contents

| Directory | Screen |
|---|---|
| `stitch_sahay_ai_executive_console/live_case_queue/` | Queue |
| `stitch_sahay_ai_executive_console/case_review_workspace/` | Case packet |
| `stitch_sahay_ai_executive_console/supervisor_operations/` | Supervisor view |
| `stitch_sahay_ai_executive_console/audit_trail_decision_ledger/` | Audit viewer |
| `stitch_sahay_ai_executive_console/sahay_ai_mark/` | Identity mark |
| `stitch_sahay_ai_executive_console/civic_operations/DESIGN.md` | Design language and colour tokens |

## Before building a screen from one of these

Check the mockup against `frontend/CLAUDE.md`:

- [ ] The SVI is never a bare number — the dimension breakdown is adjacent and
      confidence has equal prominence.
- [ ] Every assessment field links to the utterance that produced it.
- [ ] Recommendations render as **awaiting decision**, never as action taken.
- [ ] Assistant turns and victim turns are visually distinct.
- [ ] Alerts sort to the top and require acknowledgement.
- [ ] "Needs Human Assessment" is present as a designed state.
- [ ] Weights are labelled provisional, pending expert calibration.
- [ ] The assessment disclaimer is on screen. Judges photograph screens.

Any colour, icon set, font or CDN asset a mockup uses is a new dependency and
needs its own approval under the external-dependency protocol. Do not add one
because a mockup used it.
