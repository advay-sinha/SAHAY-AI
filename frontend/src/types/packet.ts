/**
 * REST read models returned by the backend (queue, escalation packet, audit).
 * These mirror backend/app/services/packet.py, not the frozen event contract.
 */

import type { AlertSeverity, AlertType, Band, DecisionKind, DimensionId } from "./contracts";

export interface QueueAlert {
  alert_type: AlertType;
  severity: AlertSeverity;
  acknowledged: boolean;
}

export interface QueueItem {
  case_id: string;
  reference: string;
  language: string | null;
  channel: string | null;
  wait_seconds: number;
  session_state: string | null;
  session_ended: boolean;
  band: Band | null;
  needs_human_assessment: boolean;
  consent: "granted" | "declined" | "pending" | string;
  status: "open" | "claimed" | "taken_over" | "closed" | string;
  assigned_to: string | null;
  assigned_officer_id: string | null;
  takeover_requested: boolean;
  alerts: QueueAlert[];
  unacknowledged_critical: boolean;
}

export interface PacketDimension {
  dimension: DimensionId;
  label: string;
  weight: number;
  /** null when unscored, and ALWAYS null under Needs Human Assessment. */
  score: number | null;
  confidence: number | null;
  evidence_turn_ids: string[];
  basis: string | null;
  /** PC-08: false when structurally unavailable for the channel (D4 on typed text). */
  available?: boolean;
  /** PC-08: weight / weight_denominator; 0 when unavailable. */
  effective_weight?: number;
}

/** PC-08 normalisation record stored with every assessment. */
export interface Normalization {
  scoring_version?: string;
  channel?: string;
  available_dimensions?: DimensionId[];
  structurally_unavailable?: DimensionId[];
  weight_denominator?: number;
  normalization_factor?: number;
}

export interface PacketAssessment {
  suppressed: boolean;
  reason?: string;
  svi: number | null;
  band: Band | null;
  needs_human: boolean;
  aggregate_confidence?: number | null;
  overrides_applied?: string[];
  abstention_reasons?: string[];
  cause?: string;
  dimensions: PacketDimension[];
  weights_are_provisional?: boolean;
  scoring_version?: string | null;
  normalization?: Normalization;
  cycle?: number;
}

export interface PacketAlert {
  id: string;
  alert_type: AlertType;
  severity: AlertSeverity;
  evidence_turn_ids: string[];
  requires_ack: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface SourcedField {
  value: string;
  source_turn_ids: string[];
}

export interface StructuredRecord {
  incident?: SourcedField | null;
  timeline?: SourcedField[];
  persons?: SourcedField[];
  threats?: SourcedField[];
  safety_now?: SourcedField | null;
  medical_need?: SourcedField | null;
  legal_status?: SourcedField | null;
  isolation?: SourcedField | null;
  requested_support?: SourcedField | null;
}

export interface PacketTurn {
  id: string;
  seq: number;
  speaker: "victim" | "assistant" | "officer";
  text: string;
  lang: string;
  state: string;
  intent: string | null;
  review_status: string | null;
  ts: string | null;
}

export interface TrajectoryPoint {
  cycle: number;
  svi: number | null;
  band: Band | null;
  needs_human: boolean;
  cause: string;
  trigger_turn_id: string | null;
  ts: string | null;
}

export interface PacketRecommendation {
  action_id: string;
  action_type: string;
  label: string;
  rationale: string;
  policy_citations: string[];
  confidence: number;
  evidence_turn_ids: string[];
  status: "awaiting_decision" | "decided";
}

export interface HumanDecision {
  id: string;
  action_id: string;
  decision: DecisionKind;
  rationale: string;
  officer: string;
  decided_at: string | null;
}

export interface OverrideRecord {
  id: string;
  from_band: Band | null;
  to_band: Band;
  reason: string;
  officer: string;
  at: string | null;
}

export interface CasePacket {
  header: {
    case_id: string;
    reference: string;
    language: string | null;
    channel: string | null;
    duration_seconds: number | null;
    consent: string;
    band: Band | null;
    band_source: string | null;
    needs_human_assessment: boolean;
    status: string;
    session_state: string | null;
    session_ended: boolean;
    human_joined: boolean;
    human_joined_at: string | null;
    assigned_to: string | null;
    assigned_officer_id: string | null;
    takeover_requested: boolean;
    session_id: string;
  };
  assessment: PacketAssessment;
  alerts: PacketAlert[];
  structured: StructuredRecord;
  transcript: PacketTurn[];
  evidence: Record<string, string[]>;
  trajectory: TrajectoryPoint[];
  recommendations: PacketRecommendation[];
  decisions: HumanDecision[];
  overrides: OverrideRecord[];
  uncertainty: Record<string, unknown>;
  disclaimer: string;
}

export interface AuditEntry {
  at: string | null;
  actor_kind: "system" | "human" | string;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
}
