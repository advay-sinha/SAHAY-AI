import {
  ALERT_SEVERITIES, ALERT_TYPES, BANDS, CONSENT_STATUSES, DECISIONS,
  SESSION_CHANNELS, SESSION_STATES, TIMELINE_STAGES, TURN_SPEAKERS,
  type AlertAckResponse, type Band, type OfficerMessageResponse, type VictimTimeline,
} from "../types/contracts";
import type { AuditEntry, CasePacket, QueueItem } from "../types/packet";

type RecordValue = Record<string, unknown>;
export class ResponseValidationError extends Error {
  constructor() { super("invalid response"); this.name = "ResponseValidationError"; }
}
function record(value: unknown): value is RecordValue {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}
function exact(value: unknown, keys: readonly string[]): value is RecordValue {
  return record(value) && Object.keys(value).length === keys.length
    && Object.keys(value).every((key) => keys.includes(key));
}
function allowed(value: unknown, required: readonly string[], optional: readonly string[] = []): value is RecordValue {
  return record(value) && required.every((key) => key in value)
    && Object.keys(value).every((key) => required.includes(key) || optional.includes(key));
}
const string = (value: unknown): value is string => typeof value === "string";
const nonempty = (value: unknown): value is string => string(value) && value.length > 0;
const number = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const boolean = (value: unknown): value is boolean => typeof value === "boolean";
const nullable = <T>(predicate: (value: unknown) => value is T) => (value: unknown): value is T | null => value === null || predicate(value);
const oneOf = <T extends string>(values: readonly T[]) => (value: unknown): value is T => string(value) && values.includes(value as T);
const arrayOf = <T = unknown>(predicate: (value: unknown) => boolean) => (value: unknown): value is T[] => Array.isArray(value) && value.every(predicate);
const strings = arrayOf(string);
const band = nullable(oneOf(BANDS));
function accept<T>(value: unknown, predicate: (candidate: unknown) => candidate is T): T {
  if (!predicate(value)) throw new ResponseValidationError();
  return value;
}
function timelineEntry(value: unknown): boolean {
  return exact(value, ["stage", "label", "ts"])
    && oneOf(TIMELINE_STAGES)(value.stage) && string(value.label) && string(value.ts);
}

export function validateHealth(value: unknown) {
  return accept(value, (candidate): candidate is {
    status: "ok"; app_env: string; llm_provider: string; assessment_runner: string;
    database: string; fixed_scripts_ready: boolean; detail: Record<string, unknown>;
  } => exact(candidate, ["status", "app_env", "llm_provider", "assessment_runner", "database", "fixed_scripts_ready", "detail"])
    && candidate.status === "ok" && string(candidate.app_env) && string(candidate.llm_provider)
    && string(candidate.assessment_runner) && string(candidate.database)
    && boolean(candidate.fixed_scripts_ready) && record(candidate.detail));
}
function queueAlert(value: unknown): boolean {
  return exact(value, ["alert_type", "severity", "acknowledged"])
    && oneOf(ALERT_TYPES)(value.alert_type) && oneOf(ALERT_SEVERITIES)(value.severity) && boolean(value.acknowledged);
}
function queueItem(value: unknown): value is QueueItem {
  if (!exact(value, ["case_id", "reference", "language", "channel", "wait_seconds", "session_state",
    "session_ended", "band", "needs_human_assessment", "consent", "status", "assigned_to",
    "assigned_officer_id", "takeover_requested", "alerts", "unacknowledged_critical"])) return false;
  return nonempty(value.case_id) && nonempty(value.reference) && nullable(string)(value.language)
    && (value.channel === null || oneOf(SESSION_CHANNELS)(value.channel)) && number(value.wait_seconds)
    && nullable(oneOf(SESSION_STATES))(value.session_state) && boolean(value.session_ended) && band(value.band)
    && boolean(value.needs_human_assessment) && oneOf(CONSENT_STATUSES)(value.consent)
    && ["open", "claimed", "taken_over", "closed"].includes(String(value.status))
    && nullable(string)(value.assigned_to) && nullable(string)(value.assigned_officer_id)
    && boolean(value.takeover_requested) && arrayOf(queueAlert)(value.alerts) && boolean(value.unacknowledged_critical);
}
export const validateQueue = (value: unknown): QueueItem[] => accept(value, arrayOf(queueItem));

function packetDimension(value: unknown): boolean {
  return exact(value, ["dimension", "label", "weight", "available", "effective_weight", "score", "confidence", "evidence_turn_ids", "basis"])
    && /^D[1-9]$/.test(String(value.dimension)) && string(value.label) && number(value.weight)
    && boolean(value.available) && number(value.effective_weight) && nullable(number)(value.score)
    && nullable(number)(value.confidence) && strings(value.evidence_turn_ids) && nullable(string)(value.basis);
}
function assessment(value: unknown): boolean {
  if (!allowed(value, ["suppressed", "svi", "band", "needs_human", "dimensions"], [
    "reason", "aggregate_confidence", "overrides_applied", "abstention_reasons", "cause",
    "weights_are_provisional", "scoring_version", "normalization", "cycle",
  ])) return false;
  return boolean(value.suppressed) && nullable(number)(value.svi) && band(value.band)
    && boolean(value.needs_human) && arrayOf(packetDimension)(value.dimensions)
    && (value.reason === undefined || string(value.reason))
    && (value.aggregate_confidence === undefined || nullable(number)(value.aggregate_confidence))
    && (value.overrides_applied === undefined || strings(value.overrides_applied))
    && (value.abstention_reasons === undefined || strings(value.abstention_reasons))
    && (value.cause === undefined || string(value.cause))
    && (value.weights_are_provisional === undefined || boolean(value.weights_are_provisional))
    && (value.scoring_version === undefined || nullable(string)(value.scoring_version))
    && (value.normalization === undefined || record(value.normalization))
    && (value.cycle === undefined || number(value.cycle));
}
function header(value: unknown): boolean {
  return exact(value, ["case_id", "reference", "language", "channel", "duration_seconds", "consent", "band",
    "band_source", "needs_human_assessment", "status", "session_state", "session_ended", "human_joined",
    "human_joined_at", "assigned_to", "assigned_officer_id", "takeover_requested", "session_id"])
    && nonempty(value.case_id) && nonempty(value.reference) && nullable(string)(value.language)
    && nullable(string)(value.channel) && nullable(number)(value.duration_seconds) && oneOf(CONSENT_STATUSES)(value.consent)
    && band(value.band) && nullable(string)(value.band_source) && boolean(value.needs_human_assessment)
    && string(value.status) && nullable(oneOf(SESSION_STATES))(value.session_state) && boolean(value.session_ended)
    && boolean(value.human_joined) && nullable(string)(value.human_joined_at) && nullable(string)(value.assigned_to)
    && nullable(string)(value.assigned_officer_id) && boolean(value.takeover_requested) && nonempty(value.session_id);
}
function packetAlert(value: unknown): boolean {
  return exact(value, ["id", "alert_type", "severity", "evidence_turn_ids", "requires_ack", "acknowledged_by", "acknowledged_at"])
    && nonempty(value.id) && oneOf(ALERT_TYPES)(value.alert_type) && oneOf(ALERT_SEVERITIES)(value.severity)
    && strings(value.evidence_turn_ids) && boolean(value.requires_ack) && nullable(string)(value.acknowledged_by)
    && nullable(string)(value.acknowledged_at);
}
function sourced(value: unknown): boolean { return exact(value, ["value", "source_turn_ids"]) && string(value.value) && strings(value.source_turn_ids); }
function structured(value: unknown): boolean {
  if (!allowed(value, [], ["incident", "timeline", "persons", "threats", "safety_now", "medical_need", "legal_status", "isolation", "requested_support"])) return false;
  return Object.entries(value).every(([key, item]) => ["timeline", "persons", "threats"].includes(key)
    ? arrayOf(sourced)(item) : item === null || sourced(item));
}
function turn(value: unknown): boolean {
  return exact(value, ["id", "seq", "speaker", "text", "lang", "state", "intent", "review_status", "ts"])
    && nonempty(value.id) && number(value.seq) && oneOf(TURN_SPEAKERS)(value.speaker) && string(value.text)
    && string(value.lang) && string(value.state) && nullable(string)(value.intent)
    && nullable(string)(value.review_status) && nullable(string)(value.ts);
}
function trajectory(value: unknown): boolean {
  return exact(value, ["cycle", "svi", "band", "needs_human", "cause", "trigger_turn_id", "ts"])
    && number(value.cycle) && nullable(number)(value.svi) && band(value.band) && boolean(value.needs_human)
    && string(value.cause) && nullable(string)(value.trigger_turn_id) && nullable(string)(value.ts);
}
function recommendation(value: unknown): boolean {
  return exact(value, ["action_id", "action_type", "label", "rationale", "policy_citations", "confidence", "evidence_turn_ids", "status"])
    && nonempty(value.action_id) && string(value.action_type) && string(value.label) && string(value.rationale)
    && strings(value.policy_citations) && number(value.confidence) && strings(value.evidence_turn_ids)
    && (value.status === "awaiting_decision" || value.status === "decided");
}
function decision(value: unknown): boolean {
  return exact(value, ["id", "action_id", "decision", "rationale", "officer", "decided_at"])
    && nonempty(value.id) && nonempty(value.action_id) && oneOf(DECISIONS)(value.decision) && string(value.rationale)
    && string(value.officer) && nullable(string)(value.decided_at);
}
function override(value: unknown): boolean {
  return exact(value, ["id", "from_band", "to_band", "reason", "officer", "at"])
    && nonempty(value.id) && band(value.from_band) && oneOf(BANDS)(value.to_band) && string(value.reason)
    && string(value.officer) && nullable(string)(value.at);
}
function casePacket(value: unknown): value is CasePacket {
  if (!exact(value, ["header", "assessment", "alerts", "structured", "transcript", "evidence", "trajectory",
    "recommendations", "decisions", "overrides", "uncertainty", "disclaimer"])) return false;
  return header(value.header) && assessment(value.assessment) && arrayOf(packetAlert)(value.alerts)
    && structured(value.structured) && arrayOf(turn)(value.transcript) && record(value.evidence)
    && Object.values(value.evidence).every(strings) && arrayOf(trajectory)(value.trajectory)
    && arrayOf(recommendation)(value.recommendations) && arrayOf(decision)(value.decisions)
    && arrayOf(override)(value.overrides) && record(value.uncertainty) && string(value.disclaimer);
}
export const validateCasePacket = (value: unknown): CasePacket => accept(value, casePacket);
function auditEntry(value: unknown): value is AuditEntry {
  return exact(value, ["at", "actor_kind", "actor", "action", "detail"])
    && nullable(string)(value.at) && string(value.actor_kind) && string(value.actor) && string(value.action) && record(value.detail);
}
export const validateAudit = (value: unknown): AuditEntry[] => accept(value, arrayOf(auditEntry));
export const validateTimeline = (value: unknown): VictimTimeline => accept(value, (candidate): candidate is VictimTimeline =>
  exact(candidate, ["reference", "timeline"]) && nonempty(candidate.reference) && arrayOf(timelineEntry)(candidate.timeline));
export const validateAlertAck = (value: unknown): AlertAckResponse => accept(value, (candidate): candidate is AlertAckResponse =>
  exact(candidate, ["alert_id", "case_id", "acknowledged_by", "acknowledged_at"])
  && nonempty(candidate.alert_id) && nonempty(candidate.case_id) && nonempty(candidate.acknowledged_by) && nonempty(candidate.acknowledged_at));
export const validateOfficerMessage = (value: unknown): OfficerMessageResponse => accept(value, (candidate): candidate is OfficerMessageResponse =>
  exact(candidate, ["turn_id", "case_id", "origin", "ts"]) && nonempty(candidate.turn_id)
  && nonempty(candidate.case_id) && candidate.origin === "human_officer" && nonempty(candidate.ts));
export const validateClaim = (value: unknown) => accept(value, (candidate): candidate is { case_id: string; status: string; assigned_officer_id: string } =>
  exact(candidate, ["case_id", "status", "assigned_officer_id"]) && nonempty(candidate.case_id) && string(candidate.status) && nonempty(candidate.assigned_officer_id));
export const validateDecision = (value: unknown) => accept(value, (candidate): candidate is { decision_id: string; action_id: string; decision: string; rationale: string; officer_id: string } =>
  exact(candidate, ["decision_id", "action_id", "decision", "rationale", "officer_id"]) && nonempty(candidate.decision_id)
  && nonempty(candidate.action_id) && oneOf(DECISIONS)(candidate.decision) && string(candidate.rationale) && nonempty(candidate.officer_id));
export const validateOverride = (value: unknown) => accept(value, (candidate): candidate is { override_id: string; case_id: string; from_band: Band | null; to_band: Band; reason: string } =>
  exact(candidate, ["override_id", "case_id", "from_band", "to_band", "reason"]) && nonempty(candidate.override_id)
  && nonempty(candidate.case_id) && band(candidate.from_band) && oneOf(BANDS)(candidate.to_band) && string(candidate.reason));
export const validateTakeover = (value: unknown) => accept(value, (candidate): candidate is { case_id: string; status: string } =>
  exact(candidate, ["case_id", "status"]) && nonempty(candidate.case_id) && candidate.status === "taken_over");
