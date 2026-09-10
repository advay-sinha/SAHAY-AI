---
description: Day 12 freeze audit — what ships, what gets cut, what must not merge
allowed-tools: Read, Bash, Glob, Grep
---

# Freeze audit

It is Day 12. Feature freeze is at noon. After it, only `type:bug` merges.

1. **Demo path integrity.** Walk the 90-second script in `docs/plan/PHASES.md`. For each beat, does it work today on the demo machine? Any beat that does not is the only thing that matters now.
2. **Unmerged work.** Every open PR and branch, labelled or not. Split into: demo-critical (finish), non-critical (close now), unknown (ask the user, then close).
3. **The cut list.** Anything not labelled `priority:demo-critical` and not already merged gets closed. Name them. Do not negotiate with yourself about small ones — this rule exists so the argument does not happen at midnight.
4. **Artefacts.** Backup video recorded? APK tested on an outside phone? Evaluation table complete? Red-team table complete? Ethics one-pager written? Architecture poster done?
5. **Tag.** `v0.9-freeze` on the exact commit that passes the demo path.
6. **Report** the residual risk in three bullets, ranked. Be blunt about what is likely to break on stage.
