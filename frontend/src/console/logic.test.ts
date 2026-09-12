/**
 * Console display rules. These encode safety requirements, so they are tested
 * rather than trusted to the components:
 *   - Needs Human Assessment exposes no number;
 *   - a score always travels with breakdown and confidence;
 *   - modify / reject need a rationale; override needs a reason;
 *   - evidence links resolve only to real turns;
 *   - the trajectory never invents a value for an unscored cycle.
 */

import { describe, expect, it } from "vitest";

import type { CasePacket, PacketAssessment, PacketTurn, QueueItem, TrajectoryPoint } from "../types/packet";
import {
  assessmentView,
  canAct,
  canMessage,
  EMPTY_FILTERS,
  explainAbstention,
  filterQueue,
  formatWait,
  resolveEvidence,
  trajectoryGeometry,
  trajectoryPath,
  turnNumber,
  validateDecision,
  validateMessage,
  validateOverride, formatAcknowledgedBy, filterAuditDetail,
} from "./logic";

const DIMS = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"] as const;

function assessment(over: Partial<PacketAssessment> = {}): PacketAssessment {
  return {
    suppressed: false,
    svi: 55.1,
    band: "High",
    needs_human: false,
    aggregate_confidence: 0.63,
    overrides_applied: [],
    abstention_reasons: [],
    dimensions: DIMS.map((d) => ({
      dimension: d, label: d, weight: 0.1, score: d === "D4" ? null : 60,
      confidence: d === "D4" ? null : 0.7, evidence_turn_ids: d === "D3" ? ["t2"] : [], basis: "lexicon",
    })),
    weights_are_provisional: true,
    ...over,
  };
}

const TURNS: PacketTurn[] = [
  { id: "t1", seq: 1, speaker: "victim", text: "a", lang: "hi", state: "S1", intent: null, review_status: null, ts: null },
  { id: "t2", seq: 2, speaker: "assistant", text: "b", lang: "hi", state: "S2", intent: "x", review_status: "draft", ts: null },
];

describe("assessment display", () => {
  it("shows a score only with its breakdown and confidence", () => {
    const v = assessmentView(assessment());
    expect(v.mode).toBe("scored");
    if (v.mode !== "scored") return;
    expect(v.rows).toHaveLength(9);
    expect(v.confidence).toBe(0.63);
  });

  it("Needs Human Assessment exposes no number anywhere", () => {
    const v = assessmentView(assessment({ svi: null, band: null, needs_human: true,
      abstention_reasons: ["aggregate_confidence_below_floor"] }));
    expect(v.mode).toBe("needs_human");
    const text = JSON.stringify(v);
    expect(text).not.toMatch(/"svi"|"score"|"confidence"|\d+\.\d/);
    if (v.mode === "needs_human") expect(v.evidenceDimensions).toEqual(["D3"]);
  });

  it("a band without an svi, or an svi without a band, is treated as no score", () => {
    expect(assessmentView(assessment({ svi: null })).mode).toBe("needs_human");
    expect(assessmentView(assessment({ band: null })).mode).toBe("needs_human");
  });

  it("consent declined is its own state", () => {
    expect(assessmentView(assessment({ suppressed: true, svi: null, band: null })).mode).toBe("suppressed");
  });

  it("PC-08: says D4 was not measured and how weights were rescaled, never as zero", () => {
    const v = assessmentView(assessment({
      dimensions: DIMS.map((d) => ({
        dimension: d, label: d, weight: 0.1, score: d === "D4" ? null : 60,
        confidence: d === "D4" ? null : 0.7, evidence_turn_ids: [], basis: "lexicon",
        available: d !== "D4", effective_weight: d === "D4" ? 0 : 0.1136,
      })),
      normalization: { structurally_unavailable: ["D4"], weight_denominator: 0.88, scoring_version: "svi-2026.09-pc08" },
    }));
    expect(v.mode).toBe("scored");
    if (v.mode !== "scored") return;
    expect(v.normalizationNote).toMatch(/D4 was not measured/);
    expect(v.normalizationNote).toMatch(/not scored as zero/);
    expect(v.normalizationNote).toMatch(/0\.88/);
    const d4 = v.rows.find((r) => r.dimension === "D4");
    expect(d4?.available).toBe(false);
    expect(d4?.score).toBeNull();
  });

  it("PC-08: no note when nothing was renormalised", () => {
    const v = assessmentView(assessment({ normalization: { structurally_unavailable: [], weight_denominator: 1 } }));
    if (v.mode === "scored") expect(v.normalizationNote).toBeNull();
  });

  it("abstention reasons are explained in plain language", () => {
    expect(explainAbstention("conflicting_evidence")).toMatch(/conflicting/);
    expect(explainAbstention("something_new")).toBe("something new");
  });
});
describe("officer input validation", () => {
  it("modify and reject need a rationale; confirm does not", () => {
    expect(validateDecision("confirm", "")).toBeNull();
    expect(validateDecision("modify", "   ")).not.toBeNull();
    expect(validateDecision("reject", "")).not.toBeNull();
    expect(validateDecision("reject", "caller declined")).toBeNull();
  });

  it("an override needs a band and a written reason", () => {
    expect(validateOverride("", "why")).not.toBeNull();
    expect(validateOverride("High", "  ")).not.toBeNull();
    expect(validateOverride("High", "officer judgement")).toBeNull();
  });
});
describe("evidence", () => {
  it("only resolves ids that are real turns", () => {
    expect(resolveEvidence(["t1", "ghost", "t2"], TURNS)).toEqual(["t1", "t2"]);
    expect(turnNumber("t2", TURNS)).toBe(2);
    expect(turnNumber("ghost", TURNS)).toBeNull();
  });
});

describe("action gate", () => {
  const packet = (owner: string | null) =>
    ({ header: { assigned_officer_id: owner, assigned_to: owner ? "Executive Two" : null } }) as unknown as CasePacket;
  it("requires the case to be claimed by the viewer", () => {
    expect(canAct(packet(null), "u1")).toEqual({ ok: false, reason: "Claim the case before acting on it." });
    expect(canAct(packet("u2"), "u1").ok).toBe(false);
    expect(canAct(packet("u1"), "u1")).toEqual({ ok: true });
  });

  it("PC-06: a supervisor view is read-only even on its own claim", () => {
    expect(canAct(packet("u1"), "u1", "supervisor").ok).toBe(false);
    expect(canAct(packet("u1"), "u1", "executive").ok).toBe(true);
  });
});

describe("officer message (PC-07)", () => {
  const packet = (over: Record<string, unknown>) =>
    ({ header: { assigned_officer_id: "u1", assigned_to: "Executive One", status: "taken_over",
      human_joined: true, human_joined_at: "2026-09-11T10:00:00+00:00", session_ended: false, ...over } }) as unknown as CasePacket;

  it("is allowed only after a verified takeover by the claiming officer", () => {
    const ok = packet({});
    expect(canMessage(ok, canAct(ok, "u1")).ok).toBe(true);
    for (const over of [{ status: "claimed" }, { human_joined: false }, { human_joined_at: null }, { session_ended: true }]) {
      const p = packet(over);
      expect(canMessage(p, canAct(p, "u1")).ok).toBe(false);
    }
    expect(canMessage(ok, canAct(ok, "u2")).ok).toBe(false);
    expect(canMessage(ok, canAct(ok, "u1", "supervisor")).ok).toBe(false);
  });

  it("refuses blank and over-long text", () => {
    expect(validateMessage("  ")).not.toBeNull();
    expect(validateMessage("x".repeat(2001))).not.toBeNull();
    expect(validateMessage("An officer is here with you.")).toBeNull();
  });
});

describe("queue", () => {
  const item = (over: Partial<QueueItem>): QueueItem => ({
    case_id: "c", reference: "SAH-1", language: "hi", channel: "mobile_chat", wait_seconds: 10, session_state: "S1",
    session_ended: false, band: "Moderate", needs_human_assessment: false, consent: "granted", status: "open",
    assigned_to: null, assigned_officer_id: null, takeover_requested: false, alerts: [],
    unacknowledged_critical: false, ...over,
  });
  const items = [
    item({ case_id: "a", band: "High", alerts: [{ alert_type: "threat", severity: "high", acknowledged: false }] }),
    item({ case_id: "b", band: null, needs_human_assessment: true, language: "en" }),
    item({ case_id: "c", assigned_officer_id: "u1", assigned_to: "x" }),
  ];

  it("filters by band, needs-human, alerts, assignment and language", () => {
    expect(filterQueue(items, { ...EMPTY_FILTERS, band: "High" }).map((i) => i.case_id)).toEqual(["a"]);
    expect(filterQueue(items, { ...EMPTY_FILTERS, band: "needs_human" }).map((i) => i.case_id)).toEqual(["b"]);
    expect(filterQueue(items, { ...EMPTY_FILTERS, alertsOnly: true }).map((i) => i.case_id)).toEqual(["a"]);
    expect(filterQueue(items, { ...EMPTY_FILTERS, unassignedOnly: true }).map((i) => i.case_id)).toEqual(["a", "b"]);
    expect(filterQueue(items, { ...EMPTY_FILTERS, language: "en" }).map((i) => i.case_id)).toEqual(["b"]);
  });

  it("keeps the server's order", () => {
    expect(filterQueue(items, EMPTY_FILTERS).map((i) => i.case_id)).toEqual(["a", "b", "c"]);
  });

  it("formats waiting time", () => {
    expect(formatWait(42)).toBe("42s");
    expect(formatWait(125)).toBe("2m");
    expect(formatWait(3 * 3600 + 5 * 60)).toBe("3h 5m");
  });
});

describe("trajectory", () => {
  const p = (cycle: number, svi: number | null): TrajectoryPoint => ({
    cycle, svi, band: svi === null ? null : "Moderate", needs_human: svi === null, cause: "x",
    trigger_turn_id: `t${cycle}`, ts: null,
  });

  it("never invents a value for an unscored cycle", () => {
    const geo = trajectoryGeometry([p(1, null), p(2, 40), p(3, 55)], 100, 50);
    expect(geo[0]!.y).toBeNull();
    expect(geo[1]!.y).not.toBeNull();
    const path = trajectoryPath(geo);
    expect(path.startsWith("M")).toBe(true);
    expect(path.match(/[ML]/g)).toHaveLength(2);
  });

  it("breaks the line across a gap", () => {
    const path = trajectoryPath(trajectoryGeometry([p(1, 40), p(2, null), p(3, 60)], 100, 50));
    expect(path.match(/M/g)).toHaveLength(2);
    expect(path).not.toMatch(/L/);
  });

  it("higher SVI plots higher on screen", () => {
    const [low, high] = trajectoryGeometry([p(1, 20), p(2, 80)], 100, 50);
    expect(high!.y!).toBeLessThan(low!.y!);
  });
});

describe("audit and alerts formatting", () => {
  it("formats alert acknowledgement with timestamp", () => {
    expect(formatAcknowledgedBy("Executive One", null)).toBe("Acknowledged by Executive One");
    const at = "2026-09-11T12:00:00Z";
    expect(formatAcknowledgedBy("Executive One", at)).toBe(`Acknowledged by Executive One at ${new Date(at).toLocaleString()}`);
    expect(formatAcknowledgedBy(null, null)).toBeNull();
  });

  it("filters sensitive audit details", () => {
    const raw = {
      action_id: "act-1",
      band: "High",
      narrative: "Victim reported severe distress",
      transcript_text: "Help me",
      unknown_field: 42
    };
    const safe = filterAuditDetail(raw);
    expect(safe).toEqual({
      action_id: "act-1",
      band: "High"
    });
  });
});

