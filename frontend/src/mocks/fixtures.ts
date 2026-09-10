/**
 * Fixtures so the console works before the API does.
 * Team C must never be blocked waiting on Team B.
 *
 * Every person, place and incident here is fictional.
 */

import type {
  ActionRecommended,
  CaseStructured,
  DimensionUpdate,
  SafetyAlert,
  TranscriptLine,
} from "../types/contracts";

export const mockTranscript: TranscriptLine[] = [
  {
    turn_id: "t1",
    speaker: "assistant",
    text: "(S0 opening script — not yet written)",
    lang: "hi",
    ts: "2026-09-10T10:00:00Z",
  },
  {
    turn_id: "t2",
    speaker: "victim",
    text: "They stopped us from using the village water tap again.",
    lang: "en",
    ts: "2026-09-10T10:00:20Z",
  },
];

export const mockDimensions: DimensionUpdate = {
  dims: {
    D1: { score: 40, conf: 0.71, evidence_turn_ids: ["t2"] },
    D2: { score: 0, conf: 0.88, evidence_turn_ids: [] },
    D3: { score: 55, conf: 0.64, evidence_turn_ids: ["t2"] },
    D4: { score: 48, conf: 0.52, evidence_turn_ids: ["t2"] },
    D5: { score: 20, conf: 0.49, evidence_turn_ids: [] },
    D6: { score: 72, conf: 0.77, evidence_turn_ids: ["t2"] },
    D7: { score: 10, conf: 0.8, evidence_turn_ids: [] },
    D8: { score: 35, conf: 0.6, evidence_turn_ids: [] },
    D9: { score: 25, conf: 0.55, evidence_turn_ids: [] },
  },
  svi: 38.6,
  band: "Moderate",
  needs_human: false,
  overrides_applied: [],
};

/** The abstention state is a designed state, not an error state. */
export const mockNeedsHuman: DimensionUpdate = {
  dims: mockDimensions.dims,
  svi: null,
  band: null,
  needs_human: true,
  overrides_applied: [],
};

export const mockAlerts: SafetyAlert[] = [
  { type: "threat", severity: "high", evidence_turn_ids: ["t2"], requires_ack: true },
];

export const mockRecommendation: ActionRecommended = {
  action_id: "a1",
  action_type: "assign_field_officer",
  rationale: "Reported exclusion from a shared water source with ongoing intimidation.",
  policy_citations: [],
  confidence: 0.61,
  status: "awaiting_decision",
};

export const mockStructured: CaseStructured = {
  incident: "Denial of access to a shared water source",
  timeline: [
    { stage: "request_received", label: "Request received", ts: "2026-09-10T10:00:00Z" },
    { stage: "under_review", label: "Under review", ts: "2026-09-10T10:04:00Z" },
  ],
  persons: [],
  threats: ["Told not to complain"],
  safety_now: "Not in immediate danger",
  medical_need: null,
  legal_status: "No FIR filed",
  isolation: "Excluded from a shared facility",
  requested_support: "Wants the tap access restored",
};
