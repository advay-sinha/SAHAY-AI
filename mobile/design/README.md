# mobile/design/ — visual reference only

Stitch-generated design explorations for the victim-facing app.

## Status

**These are visual references, not specifications.** They were produced by a
design tool and have not been reviewed against the frozen contracts or the
safety invariants.

Where a design and a contract disagree, the contract wins. In order of
authority:

1. Root `CLAUDE.md` — safety invariants
2. `docs/contracts/CONTRACTS.md` — frozen interfaces
3. `docs/dialogue/STATES.md` — what the system may say, and in which state
4. `mobile/CLAUDE.md` — team rules for this directory
5. these design files

Nothing here is imported, built, or bundled into the app. `code.html` is a
static web mockup, not React Native; `screen.png` is a render of it.
`mobile/tests/no-assessment.test.js` scans `mobile/src/` only, and deliberately
does not scan this directory — a mockup is not shipped code.

## Location

The scaffold's canonical mobile directory is `mobile/`. These files are already
under `mobile/design/`, which is correct. There is no `app/design` directory in
this repository, so no copy was required and nothing was moved or deleted.

Note the redundant nested path
`stitch_sahay_ai_helpline_app_design/stitch_sahay_ai_helpline_app_design/` —
an artefact of how the export was unpacked. It has been left exactly as-is,
pending a cleanup decision.

## Contents

| Directory | Screen |
|---|---|
| `language_selection_consent/` | Language and consent |
| `home_voice_text_intake/` | Home |
| `voice_intake_live_transcript/` | Talk |
| `text_intake_secure_chat/` | Chat |
| `request_timeline_status/` | My requests |
| `offline_poor_connection_resilience/` | Offline |
| `human_officer_handoff_transfer/` | Handoff to a person |
| `civic_reassurance/DESIGN.md` | Design language and colour tokens |

## Two findings from a first pass

Neither has been acted on. Both are for the design review, not for silent
correction.

**1. A priority badge on a victim screen.**
`text_intake_secure_chat/code.html` renders an assistant message carrying
`प्राथमिकता: नागरिक सुरक्षा / Priority: Citizen Safety` in error-container
styling with a `priority_high` icon. This is not the SVI or the band, but it is
a triage signal shown to the victim, and it sits close to the line drawn by
root `CLAUDE.md` invariant 3. Decide deliberately whether the victim sees any
urgency marker at all before this is built.

**2. Assistant wording that is not a licensed question.**
The same mockup has the assistant ask "Are you and your family in a secure
location right now?". S2's licensed question is "Are you safe right now — can
the person who harmed you reach you?" (`docs/dialogue/STATES.md`). Mockup copy
is placeholder text. Every user-visible string ships from `src/i18n/`, and
every assistant utterance comes from the state machine — never from a mockup.

`request_timeline_status/code.html` was also checked: its "No Severity, Civic
Dignity" comment marks the deliberate *absence* of a severity indicator, which
is correct. The word "Critical" in `civic_reassurance/DESIGN.md` names a colour
token, not a risk band.

## Before building a screen from one of these

Check the mockup against `mobile/CLAUDE.md`:

- [ ] No SVI, band, dimension, emotion, alert or any assessment output.
- [ ] "Talk to a person" is present, one tap, not in a menu.
- [ ] AI disclosure is on the consent screen and visible thereafter.
- [ ] No hardcoded user-visible English — everything through `src/i18n/`.
- [ ] Large targets, high contrast, minimal words.
- [ ] Errors and offline states are calm and in the user's language.
- [ ] The consent-declined path still reaches a person.

Any Expo module, native dependency, permission, font or icon set a mockup
implies is a new dependency and needs its own approval. Native audio modules
are a known time sink; flag the risk with the request.
