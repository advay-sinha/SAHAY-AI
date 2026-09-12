# Contract review — decisions before teams branch

Prepared by the Integration Lead on 2026-09-10. **The leads decided every item on 2026-09-11.** Section 1 records each outcome and section 4 lists the decisions.

The Integration Lead applied the decisions in one change to:
- `CONTRACTS.md` (v2)
- HANDOVER §11–§13
- the typed mirrors and the contract tests

Final decision records: `PROPOSED_CHANGES.md`. The analysis below is kept as it was written, for the record. **PC-11 (2026-09-12) supersedes every transitional PC-05 statement below: query authentication is removed and rejected; exact first-frame authentication is now canonical.**

## 0. Repository state this review is based on

| | |
|---|---|
| Local branch | `master` (on 2026-09-11: local `dev`, created from `master`) |
| HEAD (local and `origin/main`) | `eb5c50f feat: initialize SAHAY-AI local-first scaffold` |
| Remote branches | `main` only — no `dev` (on 2026-09-11: `dev` exists locally, not pushed) |
| Vertical slice | **Not committed and not pushed.** 62 files staged locally. |
| `.claude/`, CLAUDE.md, Stitch designs | Not in any commit. Currently untracked, because the local `.gitignore` no longer ignores them. (On 2026-09-11 they were scanned and staged for version control.) |

A team branching from `origin/main` today gets the **baseline**, not the slice.
The slice must be committed and pushed, and `dev` created from it, before any
team branch is cut (see section 5).

## 1. Summary decision table

| PC | Subject | Frozen contract | In code now | Recommendation | **Lead decision (2026-09-11)** |
|---|---|---|---|---|---|
| PC-01 | Alert acknowledgement route | No route | **Yes** (additive route) | **Approve** | **APPROVED**: frozen; executive-only, case access, idempotent |
| PC-02 | `alert.safety` kind field `type` → `alert_type` | `type` | **Yes** (`alert_type` + envelope-wins fix) | **Approve** rename; the envelope fix stays either way | **APPROVED**: `alert_type` everywhere |
| PC-03 | Overrides + timeline persistence | 13 tables (no `overrides`, no `timeline_events`); HANDOVER §11 lists 15 | **Yes** (typed `audit_log` events) | **Revise HANDOVER §11** to the frozen 13 now; reconsider at packaging | **REJECTED** (audit-only). Dedicated tables; now 15 |
| PC-04 | Assignment/takeover socket event | None | No (console polls) | **Defer** | **DEFERRED** |
| PC-05 | WebSocket auth out of the URL | `?token=<jwt>` | No (log redaction only) | **Approve in principle**; implement before mobile socket work | **APPROVED IN PRINCIPLE**, phased. Target frozen; query token transitional |
| PC-06 | Supervisor reassignment | None | No | **Defer** (P3, first on the cut list) | **DEFERRED**. Supervisor view read-only |
| PC-07 | Officer messaging after takeover | `transcript.line` speaker is `victim\|assistant` only | No | **Approve** — EC-09 (P0) is incomplete without it | **APPROVED WITH STRICT LIMITS**: `POST /cases/{id}/messages`, `officer.message` |
| PC-08 | Text-only SVI: renormalise weights without D4 | §7 formula has no renormalisation; HANDOVER §8.4 and §23 require it | **No** — not renormalised | **Approve**, scoped to *modality-unavailable* dimensions only | **APPROVED CONDITIONALLY**: structural unavailability only; denominator 0.88 |
| PC-09 | Additive response fields shipped without a PC | `POST /sessions → {session_id, ws_url}`; login `{token, role}` | **Yes** (extra fields) | **Approve** as additive; write shapes into §4 | **APPROVED AND FROZEN**: `session_token`; `ws_url` without a token; no `state` |
| PC-10 | Load-bearing shapes and enums not frozen | Unspecified | Defined only in code | **Revise**: freeze explicit enums and REST read-model shapes | **FROZEN** in HANDOVER vocabulary. CONTRACTS §9 |

## 2. Per-proposal detail

### PC-01 — Alert acknowledgement route

- **Frozen contract:** no route. EC-06 (P0) requires acknowledgement; §3 events carry `requires_ack: true`.
- **Implementation:** `POST /cases/{case_id}/alerts/{alert_id}/ack` (console roles). Idempotent: the first acknowledgement stands, and a repeat writes no audit event. An alert whose severity escalates is reset and needs a fresh acknowledgement.
- **Why different:** the contract has no way to acknowledge; the owner approved the additive route on 2026-09-10.
- **Backward compatibility:** additive; nothing existing changes.
- **Backend:** `api/cases.py::acknowledge_alert`, `services/casework.py::acknowledge`.
- **Web:** `api/client.ts::acknowledge`, `AlertsPanel` acknowledge button.
- **Mobile:** none (executive only).
- **ML:** none.
- **Database:** uses existing `alerts.acknowledged_by/at`; `audit_log.dedupe_key` (migration `4abeb4233bf7`).
- **Security/privacy:** console roles only; the victim token gets 403; the audit entry records the officer.
- **Recommendation:** approve and add to CONTRACTS §4.
- **If rejected, revert:** the route and service; `client.acknowledge` and the button; `test_vertical_slice::test_duplicate_acknowledgement_is_safe`; scenario step 11. EC-06 would then need another mechanism.

### PC-02 — `alert.safety` field collides with the event envelope

- **Frozen contract:** `alert.safety {type:"crisis"|"threat"|..., severity, ...}`. Every frame is `{type:<event>, ...payload}`, so the two `type`s collide.
- **Implementation:** the fan-out now forces the event name (`{**payload, "type": event}`); publishers send the kind as `alert_type`. A regression test proves a payload can never rename an event.
- **Why different:** a P0 defect. Officers received frames typed `"threat"` instead of `"alert.safety"`, and the TypeScript intersection type was `never`.
- **Backward compatibility:** breaking for any client reading the alert kind from `type` on the socket. No such client exists: the console refetches the REST packet, and mobile never receives alerts.
- **Backend:** `ws/fanout.py` (keep regardless), `workers/assessment.py::_alert_event`, the crisis alert in `services/intake.py`.
- **Web:** `types/contracts.ts::SafetyAlert.alert_type`.
- **Mobile:** none (alerts are executive-only).
- **ML:** none (`ml/assessment.py` still returns `type`; the backend maps it).
- **Database:** none. `alerts.type` is unchanged.
- **Security/privacy:** positive. A payload can no longer spoof the event type a client sees.
- **Recommendation:** approve the rename. The alternative (nest every payload under `data`) is a much larger change for every event.
- **If rejected, revert:** do **not** revert the envelope fix; that would reintroduce the defect. The leads would have to choose another non-colliding scheme.

### PC-03 — Overrides and timeline persistence

- **Frozen contract:** CONTRACTS §6 lists 13 tables. HANDOVER §11 (authoritative spec) lists 15, including `overrides(reason NOT NULL)` and `timeline_events`.
- **Implementation:** the frozen 13 tables. `band.override` and `timeline` are typed, append-only `audit_log` events, with `dedupe_key` making each timeline stage happen once.
- **Why different:** the two authoritative documents disagree. The code followed the frozen list.
- **Backward compatibility:** a later move to dedicated tables is an additive migration plus a data copy.
- **Backend:** `services/audit.py::timeline`, `casework.override_band`, `packet.timeline_for` / `overrides`.
- **Web:** none (reads the packet).
- **Mobile:** none (reads `GET /timeline`).
- **ML:** none.
- **Database:** if tables are chosen, a new migration adds `overrides` and `timeline_events` and copies the audit events.
- **Security/privacy:** the timeline is projected through an allowlist either way. A dedicated `overrides` table would also enforce `reason NOT NULL` in the schema.
- **Recommendation:** amend HANDOVER §11 to the frozen 13 now (it is implemented and tested). Revisit at packaging.
- **If rejected (tables chosen), change:** a migration, those three service functions, CONTRACTS §6 (13 → 15), and the table check in the contract tests.

### PC-04 — Assignment and takeover socket events

- **Frozen contract:** no event. Takeover is visible via `session.status.human_joined`.
- **Implementation:** the console polls `GET /queue` (5 s) and refetches the packet after any socket event.
- **Why different:** no contract event exists.
- **Backward compatibility:** additive when introduced.
- **Backend:** a new executive-only event plus its allowlist entry.
- **Web:** optional; polling works.
- **Mobile:** none.
- **ML:** none.
- **Database:** none.
- **Security/privacy:** must be executive-only (officer identity).
- **Recommendation:** defer. Polling meets the MVP.
- **If rejected:** nothing to revert.

### PC-05 — WebSocket authentication out of the URL

- **Frozen contract:** `WSS /ws/session/{id}?token=<jwt>`.
- **Implementation:** unchanged contract. `core/log_redaction.py` rewrites `token=` values and anything JWT-shaped in every uvicorn log line; verified live.
- **Why different:** tokens in request lines leak to server and proxy logs.
- **Backward compatibility:** breaking for every socket client (console and mobile). Needs a coordinated switch.
- **Backend:** `ws/session.py` reads a first `{"type":"auth"}` frame (or `Sec-WebSocket-Protocol`) and rejects the query parameter.
- **Web:** `api/socket.ts`.
- **Mobile:** `net/socket.ts`. This is the reason to decide before mobile builds its socket.
- **ML:** none.
- **Database:** none.
- **Security/privacy:** removes a credential from URLs. Keep the redaction as defence in depth.
- **Recommendation:** approve first-message auth in principle; implement on `feat/backend-hardening`; web and mobile switch in the same merge window.
- **If rejected:** nothing to revert.

### PC-06 — Supervisor reassignment

- **Frozen contract:** none (BE-021, P3).
- **Implementation:** read-only supervisor view by owner decision.
- **Backward compatibility:** additive.
- **Backend:** a supervisor-only route using `require_supervisor`.
- **Web:** a reassign control.
- **Mobile:** none.
- **ML:** none.
- **Database:** an audit event.
- **Security/privacy:** supervisor role only; reason required.
- **Recommendation:** defer. The supervisor view is first on the HANDOVER cut list.
- **If rejected:** nothing to revert.

### PC-07 — Officer messaging after takeover *(new)*

- **Frozen contract:** `transcript.line.speaker` is `"victim"|"assistant"`. There is no executive UP event. EC-09 (P0) requires the takeover to "hand over the channel"; AS-08 requires the victim to be told "in their language".
- **Implementation:** takeover mutes the assistant and sets `human_joined`, but the officer cannot type to the victim.
- **Why different:** the contract cannot represent an officer turn.
- **Backward compatibility:** extends an enum (`speaker` gains `"officer"`) and adds an UP event for console roles only.
- **Backend:** WS handler accepts `{"type":"officer.message","text","lang"}` from the assigned officer only; persists `speaker="human"`; fans out a victim-safe `transcript.line`.
- **Web:** a composer in the case workspace.
- **Mobile:** render officer turns. The takeover notification wording is an i18n decision.
- **ML:** none. Officer turns must be excluded from assessment (the pipeline already reads victim turns only).
- **Database:** none (`turns.speaker` already allows `human`).
- **Security/privacy:** the officer text is free text reaching the victim, bypassing the guardrail validator by design (a human, not the AI). This must be explicit in STATES.md.
- **Recommendation:** approve. Without it the P2 gate step "takeover" is cosmetic.
- **If rejected:** nothing to revert.

### PC-08 — Text-only SVI renormalisation *(new)*

- **Frozen contract:** CONTRACTS §7 `SVI = Σ(weight_i × score_i)`. HANDOVER §8.4: "Text-only sessions: D4 not applicable, remaining weights renormalise — explicitly tested"; §23 lists renormalisation among the required unit tests.
- **Implementation:** not renormalised. D4 (0.12) is unscored on text and simply drops out, so a text-only SVI is capped at 88. This is why the scenario reaches High only with strong evidence on nearly every other dimension.
- **Why different:** the frozen formula and HANDOVER disagree; the code followed the frozen formula.
- **Backward compatibility:** changes scores (upward) for every text session. Bands, the scenario expectations and the replay checks all shift.
- **Backend:** none directly; the scenario-runner assertions need re-baselining.
- **Web:** none (the display reads the returned values).
- **Mobile:** none.
- **ML:** `ml/svi/engine.py` and `overrides.py` (aggregate confidence likewise), plus the unit tests HANDOVER requires.
- **Database:** none.
- **Security/privacy:** more text cases reach High/Critical, which is the safety-conservative direction. Abstention is unchanged.
- **Recommendation:** approve, **scoped to modality-unavailable dimensions** (D4 on text). Do not renormalise over dimensions that are merely "not yet heard": that would let one strong early signal inflate the score.
- **If rejected:** amend HANDOVER §8.4 and §23 instead.

### PC-09 — Additive fields shipped without a PC entry *(new; drift introduced by the slice)*

- **Frozen contract:** `POST /sessions → {session_id, ws_url}`; `POST /auth/login → {token, role}`; action routes unspecified.
- **Implementation:**
  - `POST /sessions` also returns `token` (the victim's REST credential), `case_id`, `reference_no`, `state`, `consent`, `lang`, `ai_disclosure` and `human_request_available`.
  - Login also returns `display_name`.
  - The claim, takeover, decision, override and acknowledgement routes return small JSON bodies.
  - Status codes: 400 for a missing reason or rationale; 403 when the body `officer_id` isn't the caller, and for cross-session victim access; 409 for invalid transitions or clashes.
- **Why different:** needed to make the flow work; it was not written into the contract.
- **Backward compatibility:** additive.
- **Backend:** `schemas/contracts.py` (already done).
- **Web:** consumes the action bodies and 409 messages.
- **Mobile:** **depends on** `token`, `case_id` and `reference_no`.
- **ML:** none.
- **Database:** none.
- **Security/privacy:** `token` in the response body is the victim's own credential. `ws_url` also embeds it (see PC-05).
- **Recommendation:** approve and write the shapes into CONTRACTS §4.
- **If rejected, revert:** the extra `CreateSessionResponse` fields, which leaves the victim without a REST credential and blocks mobile.

### PC-10 — Load-bearing shapes and enums that are not frozen *(new)*

Values every team now depends on, defined only in code:

| Item | HANDOVER says | Code has |
|---|---|---|
| Timeline stages (VF-08) | received → under review → officer assigned → action taken → follow-up scheduled → closed | `request_received, under_review, officer_assigned, support_arranged, officer_speaking, recorded, closed` |
| Timeline label policy | Plain language, e.g. "a counsellor will call you" | A generic label that never names the pathway (safer if the phone is seen by someone else) |
| Session `channel` | `mobile_voice\|mobile_chat\|portal_chat\|upload` | `voice\|chat` |
| Recommendation `action_type` | `counselling\|legal_aid\|medical\|police\|witness_protection\|welfare\|follow_up` | `counselling, legal_aid, medical, police, witness_protection, emergency` |
| Case `status` | Unspecified | `open\|claimed\|taken_over\|closed` |
| `GET /queue` item, `GET /cases/{id}` packet | Sections only (§14) | `backend/app/services/packet.py`, mirrored in `frontend/src/types/packet.ts` |

- **Recommendation:** revise.
  1. Freeze each enum in CONTRACTS, choosing between the HANDOVER vocabulary and the implemented one.
  2. Decide the timeline label policy explicitly: specific vs. generic, weighed against the risk of the phone being overheard or seen.
  3. Freeze the queue item and packet as named REST shapes that mobile and web import from one source.
- **If the HANDOVER vocabulary is chosen, change:** `services/audit.py` / `timeline.py` stages, the `schemas/contracts.py` channel, `ml/nlp/recommend.py` pathway ids, and scenario data and tests.

## 3. PC numbering discrepancy

`PROPOSED_CHANGES.md` contains exactly six entries, PC-01 to PC-06. The previous
report asked the leads to sign off "PC-01 to PC-05" and mentioned PC-06
separately as not implemented. That grouping was inaccurate. It was meant to
separate items with code at stake from future proposals, but PC-04 and PC-05
have no code at stake either. The correct split:

- **Code at stake:** PC-01 and PC-02 (live in code); PC-03 (live, spec conflict).
- **Mitigation only:** PC-05 (redaction stays regardless of the decision).
- **No code:** PC-04 and PC-06.

All six need a decision. This review adds PC-07 to PC-10.

## 4. Decisions needed from the leads

| # | Decision | Options |
|---|---|---|
| D-1 | PC-01 ack route | approve / reject |
| D-2 | PC-02 alert kind field | `alert_type` / nest payloads / other |
| D-3 | PC-03 persistence | amend HANDOVER to 13 tables / add 2 tables |
| D-4 | PC-04 assignment event | defer / approve now |
| D-5 | PC-05 socket auth | first-message / subprotocol header / keep query + redaction |
| D-6 | PC-06 reassignment | defer / approve |
| D-7 | PC-07 officer messaging | approve / defer (EC-09 incomplete) |
| D-8 | PC-08 renormalisation | renormalise for modality-unavailable dims / amend HANDOVER |
| D-9 | PC-09 additive fields | approve into §4 / trim |
| D-10 | PC-10 enums | HANDOVER vocabulary / implemented vocabulary, per row; timeline label policy |
| D-11 | Contract approvers | HANDOVER names three leads (AI, Backend, Frontend+Mobile). With Web and Mobile as separate teams: does the Mobile lead join contract approvals? CODEOWNERS has no mobile owner. |
| D-12 | Branch base | approve committing the staged slice as the base of `dev` |

**Outcomes (2026-09-11).**

- **D-1 to D-10:** as in the table in section 1.
- **D-11:** four approvers: AI/ML and Safety, Backend, Executive Web, Mobile/Victim Experience. `.github/CODEOWNERS` has explicit `@TODO-...` placeholders because no username-to-role mapping is recorded.
- **D-12:** the slice becomes the base of `dev` only after all of these are done:
  - the decisions are applied;
  - PC-03 is corrected;
  - the mirrors agree;
  - the safety tests pass;
  - the scenario runs;
  - the staging audit passes.

  All six conditions are met in the staged change. The user makes the signed commit.

## 5. Branch and worktree coordination

| Branch | Owner | Base | Worktree | Owns |
|---|---|---|---|---|
| `feat/backend-hardening` | Backend | `dev` | `..\sahay-ai-backend` | `backend/**` incl. migrations, seed, scenarios, backend tests |
| `feat/web-console` | Web | `dev` | `..\sahay-ai-web` | `frontend/**` (except the contract mirror) |
| `feat/mobile-app` | Mobile | `dev` | `..\sahay-ai-mobile` | `mobile/**` (except the contract mirror and the safety test) |
| `feat/ml-evaluation` | ML | `dev` | `..\sahay-ai-ml` | `ml/**`, `data-scripts/**`, ML evaluation docs |
| `contract/<decision>` | Integration Lead | `dev` | main worktree | `docs/contracts/**`, the three mirrors, contract tests, shared root config |

`dev` does not exist yet. CONTRIBUTING and HANDOVER §26 both expect
`dev` → `main`, with `main` promoted only at a passed gate.

### Files each team may modify

| Team | May modify | Must not modify without coordination |
|---|---|---|
| Backend | `backend/**`, `backend/alembic/versions/**`, `backend/tests/**` | `backend/app/ws/events.py`, `fanout.py`, `services/timeline.py`, and the safety tests `test_role_fanout.py`, `test_timeline_leakage.py`, `test_contract_mirror.py`, `test_vertical_slice.py` — safety boundary; all-leads review, never weakened |
| Web | `frontend/**` | `frontend/src/types/contracts.ts` (contract mirror; Integration only) |
| Mobile | `mobile/**` | `mobile/src/types/events.ts` (contract mirror), `mobile/tests/no-assessment.test.js` (safety test; never removed or weakened) |
| ML | `ml/**`, `data-scripts/**`, `ml/eval/**` | `ml/svi/**` (co-owned with Backend per CODEOWNERS); `ml/dialogue/**` and `ml/guardrails/**` changes are `type:dialogue` (two reviewers, one running `dialogue-safety-reviewer`, STATES.md in the same commit) |
| Integration Lead only | `docs/contracts/**`, `docs/dialogue/STATES.md` (with all leads), `docs/EXTERNAL_DECISIONS.md`, `.gitignore`, `.github/**`, root `CLAUDE.md`, `.claude/**`, `scripts/**`, `README.md`, `CONTRIBUTING.md`, `.env.example` | — |

### Shared contracts to import, not duplicate

| Consumer | Import from | Current state |
|---|---|---|
| Backend | `backend/app/ws/events.py` (allowlists, `ASSESSMENT_FIELDS`); `ml.svi.dimensions` (weights, labels); `ml.dialogue.states`; `ml.guardrails.crisis_check` | **Consolidated (2026-09-11)** into `backend/app/core/enums.py`; a mirror test forbids a second list |
| Web | `frontend/src/types/contracts.ts` (events, weights, disclaimer); `frontend/src/types/packet.ts` (REST read models) | Good. Covered by `test_contract_mirror.py` |
| Mobile | `mobile/src/types/events.ts` — a deliberately separate victim-event mirror (it must never import console types) | **Gap closed (2026-09-11).** `test_contract_mirror.py::TestMobileAllowlistMirror` and `mobile/tests/contract-gap.test.js` check that the mobile list, the backend list and CONTRACTS §2 agree |
| ML | The three pure interfaces; never redefine weights, bands or thresholds outside `ml/svi/` | Good |

## 6. Recommended merge order

1. **Integration:** commit the staged slice (signed), push, create `dev` from it.
2. **Integration contract PR:** apply D-1 to D-10 to CONTRACTS.md, the three mirrors and the contract tests. Extend `test_contract_mirror.py` to cover `mobile/src/types/events.ts`. Consolidate the timeline stage source.
3. **`feat/ml-evaluation`** — first if PC-08 is approved: a pure-module change that shifts scores, which backend scenario expectations depend on.
4. **`feat/backend-hardening`** — the producer: PC-05 / PC-07 / PC-10 server side, rebased on ML.
5. **`feat/web-console`** — consumes the backend shapes.
6. **`feat/mobile-app`** — last. Depends on PC-05, PC-07, PC-09, PC-10 and on FE-001 (a device build, blocked on EXT-102).

Contract, then producers, then consumers. Each merge into `dev` runs
`scripts/verify-local.ps1` and the scenario runner (`--reset`, then a replay).

## 7. Frozen invariants — status

| Invariant | Enforced by | Status |
|---|---|---|
| Crisis interrupt is unconditional | `ml/dialogue/policy.py` (crisis first, SX terminal); synchronous pre-check in `services/intake.py` | Holds; tested (ML, backend, live) |
| Victim clients never receive assessment data | `ws/events.py` allowlist + `fanout.py` recursive field check + hub | Holds; tested live |
| Consent decline suppresses analysis | `ml/assessment.py`, `workers/assessment.py`, `routed_to_human` | Holds; tested |
| AI recommendations and human decisions separate | `recommendations` + `decisions_ai` vs `decisions_human` | Holds; tested |
| Humans make every final decision | Only confirm/modify creates an action; override and takeover need the claim | Holds; tested |
| Abstention → Needs Human Assessment, no score | Engine returns null; packet withholds per-dimension scores | Holds; tested at every layer |
| Evidence links resolve to real turns | Detectors cite turn ids; tests resolve them | Holds; tested |
| No clinical diagnosis claims | Dimension labels; ML test forbids diagnostic vocabulary | Holds |
| No real victim data | Fictional fixtures; identifier-pattern test | Holds |

| PC-07 officer text reaches the victim only after verified takeover | `casework.officer_message` guards; `VICTIM_ALLOWED`; single publisher | Holds; tested (backend, mobile, live) |
| PC-08 D4 never pretended or zeroed; no rescale on abstention paths | `ml/svi/engine.py` `structurally_unavailable`; `assess(channel=...)` | Holds; tested |

PC-07 (officer free text) and PC-08 (score shift) touch invariant-adjacent
behaviour and need all-leads review in addition to the normal contract process.
