/**
 * Pure console logic. No React, no fetch, no DOM: tested directly in vitest.
 *
 * The rules that matter most live here so they are tested, not just rendered:
 *   - a score is never shown without its breakdown and confidence;
 *   - Needs Human Assessment shows NO number at all;
 *   - modify / reject need a rationale, an override needs a reason;
 *   - evidence links only ever point at turns that exist.
 */

import type { Band, DecisionKind } from "../types/contracts";
import type {
  CasePacket,
  PacketAssessment,
  PacketTurn,
  QueueItem,
  TrajectoryPoint,
} from "../types/packet";

// ---------------------------------------------------------------------------
// Assessment display
// ---------------------------------------------------------------------------

export type AssessmentView =
  | { mode: "suppressed"; reason: string }
  | { mode: "needs_human"; reasons: string[]; evidenceDimensions: string[] }
  | {
      mode: "scored";
      svi: number;
      band: Band;
      confidence: number | null;
      overrides: string[];
      /** PC-08 explanation, or null when nothing was renormalised. */
      normalizationNote: string | null;
      rows: { dimension: string; label: string; weight: number; score: number | null;
              confidence: number | null; evidence: string[]; basis: string | null;
              available: boolean }[];
    };

/**
 * PC-08: say plainly which dimension was not measured and how the weights were
 * rescaled. Never implies the dimension was measured, never shows it as zero.
 */
export function normalizationNote(a: PacketAssessment): string | null {
  const missing = a.normalization?.structurally_unavailable ?? [];
  const denominator = a.normalization?.weight_denominator;
  if (missing.length === 0 || denominator === undefined) return null;
  const names = missing.join(", ");
  return (
    `${names} was not measured: it is structurally unavailable on this typed channel. ` +
    `It is excluded, not scored as zero, and the remaining weights are rescaled ` +
    `(divided by ${denominator.toFixed(2)}).`
  );
}

export function assessmentView(a: PacketAssessment): AssessmentView {
  if (a.suppressed) {
    return { mode: "suppressed", reason: a.reason ?? "Consent declined — no AI assessment." };
  }
  if (a.svi === null || a.band === null) {
    return {
      mode: "needs_human",
      reasons: a.abstention_reasons ?? [],
      evidenceDimensions: a.dimensions.filter((d) => d.evidence_turn_ids.length > 0).map((d) => d.dimension),
    };
  }
  return {
    mode: "scored",
    svi: a.svi,
    band: a.band,
    confidence: a.aggregate_confidence ?? null,
    overrides: a.overrides_applied ?? [],
    normalizationNote: normalizationNote(a),
    rows: a.dimensions.map((d) => ({
      dimension: d.dimension, label: d.label, weight: d.weight, score: d.score,
      confidence: d.confidence, evidence: d.evidence_turn_ids, basis: d.basis,
      available: d.available !== false,
    })),
  };
}

export const ABSTENTION_TEXT: Record<string, string> = {
  aggregate_confidence_below_floor: "Not enough of the conversation has been heard to assess reliably.",
  low_language_confidence: "The language of the messages could not be identified reliably.",
  poor_input_quality: "The messages are too short or unclear to assess.",
  conflicting_evidence: "The messages contain conflicting statements about safety.",
  poor_audio_quality: "Audio quality is too poor to assess.",
  acoustic_not_measured: "Acoustic distress could not be measured on this audio channel; the score is withheld, not rescaled.",
  consent_declined: "Consent was declined; no AI assessment is made.",
};

export function explainAbstention(reason: string): string {
  return ABSTENTION_TEXT[reason] ?? reason.replace(/_/g, " ");
}

// ---------------------------------------------------------------------------
// Validation of officer input (mirrors the server; the server still decides)
// ---------------------------------------------------------------------------

export function validateDecision(decision: DecisionKind, rationale: string): string | null {
  if ((decision === "modify" || decision === "reject") && rationale.trim() === "") {
    return "A rationale is required to modify or reject a recommendation.";
  }
  return null;
}

export function validateOverride(band: Band | "", reason: string): string | null {
  if (band === "") return "Choose a band.";
  if (reason.trim() === "") return "A written reason is required to override the band.";
  return null;
}

// ---------------------------------------------------------------------------
// Queue
// ---------------------------------------------------------------------------

export interface QueueFilters {
  band: "" | Band | "needs_human";
  alertsOnly: boolean;
  unassignedOnly: boolean;
  language: string;
}

export const EMPTY_FILTERS: QueueFilters = { band: "", alertsOnly: false, unassignedOnly: false, language: "" };

export function filterQueue(items: QueueItem[], f: QueueFilters): QueueItem[] {
  return items.filter((i) => {
    if (f.band === "needs_human" && !i.needs_human_assessment) return false;
    if (f.band && f.band !== "needs_human" && i.band !== f.band) return false;
    if (f.alertsOnly && !i.alerts.some((a) => !a.acknowledged)) return false;
    if (f.unassignedOnly && i.assigned_officer_id) return false;
    if (f.language && i.language !== f.language) return false;
    return true;
  });
}

export function formatWait(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

// ---------------------------------------------------------------------------
// Evidence and actions
// ---------------------------------------------------------------------------

/** Keep only ids that refer to turns in the transcript. */
export function resolveEvidence(ids: string[], transcript: PacketTurn[]): string[] {
  const known = new Set(transcript.map((t) => t.id));
  return ids.filter((id) => known.has(id));
}

/** 1-based position of a turn in the transcript, for "see turn 3" links. */
export function turnNumber(id: string, transcript: PacketTurn[]): number | null {
  const i = transcript.findIndex((t) => t.id === id);
  return i < 0 ? null : i + 1;
}

export type ActionGate =
  | { ok: true }
  | { ok: false; reason: string };

/**
 * Decide / override / takeover / message require the case to be claimed by
 * the viewer. A supervisor's view is read-only (PC-06); the server refuses
 * supervisor writes with 403 regardless of what this returns.
 */
export function canAct(packet: CasePacket, officerId: string | undefined, role?: string): ActionGate {
  if (role === "supervisor") return { ok: false, reason: "Supervisor view is read-only." };
  const owner = packet.header.assigned_officer_id;
  if (!owner) return { ok: false, reason: "Claim the case before acting on it." };
  if (owner !== officerId) return { ok: false, reason: `Assigned to ${packet.header.assigned_to ?? "another officer"}.` };
  return { ok: true };
}

/** PC-07: an officer may message only after a verified takeover. */
export function canMessage(packet: CasePacket, gate: ActionGate): ActionGate {
  if (!gate.ok) return gate;
  const h = packet.header;
  if (h.status !== "taken_over" || !h.human_joined || !h.human_joined_at) {
    return { ok: false, reason: "Take over the conversation before messaging the complainant." };
  }
  if (h.session_ended) return { ok: false, reason: "The session has ended." };
  return { ok: true };
}

export const MAX_MESSAGE_CHARS = 2000;

export function validateMessage(text: string): string | null {
  if (text.trim() === "") return "Write a message first.";
  if (text.trim().length > MAX_MESSAGE_CHARS) return `Keep the message under ${MAX_MESSAGE_CHARS} characters.`;
  return null;
}

export function decisionFor(packet: CasePacket, actionId: string) {
  return packet.decisions.find((d) => d.action_id === actionId) ?? null;
}

// ---------------------------------------------------------------------------
// Trajectory (inline SVG geometry; no chart library)
// ---------------------------------------------------------------------------

export interface PlotPoint {
  x: number;
  y: number | null; // null = Needs Human Assessment at this cycle: no point drawn
  point: TrajectoryPoint;
}

export function trajectoryGeometry(points: TrajectoryPoint[], width: number, height: number, pad = 8): PlotPoint[] {
  const n = points.length;
  return points.map((p, i) => ({
    x: n <= 1 ? width / 2 : pad + (i * (width - 2 * pad)) / (n - 1),
    y: p.svi === null ? null : height - pad - (p.svi / 100) * (height - 2 * pad),
    point: p,
  }));
}

/** SVG path through consecutive scored points; breaks at Needs Human gaps. */
export function trajectoryPath(geo: PlotPoint[]): string {
  let d = "";
  let pen = false;
  for (const g of geo) {
    if (g.y === null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${g.x.toFixed(1)},${g.y.toFixed(1)} `;
    pen = true;
  }
  return d.trim();
}

export const BAND_BOUNDS: { band: Band; from: number; to: number }[] = [
  { band: "Low", from: 0, to: 29 },
  { band: "Moderate", from: 30, to: 54 },
  { band: "High", from: 55, to: 74 },
  { band: "Critical", from: 75, to: 100 },
];
