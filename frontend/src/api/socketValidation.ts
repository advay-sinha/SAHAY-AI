import {
  ALERT_SEVERITIES, ALERT_TYPES, ASSISTANT_AUDIO, BANDS, CONSENT_STATUSES, SESSION_STATES, TIMELINE_STAGES,
  type Role, type SocketEvent,
} from "../types/contracts";

type Row = Record<string, unknown>;
const record = (value: unknown): value is Row => typeof value === "object" && value !== null
  && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;
const exact = (value: unknown, keys: readonly string[]): value is Row => record(value)
  && Object.keys(value).length === keys.length && Object.keys(value).every((key) => keys.includes(key));
const string = (value: unknown): value is string => typeof value === "string";
const number = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const boolean = (value: unknown): value is boolean => typeof value === "boolean";
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(string);
const oneOf = (values: readonly string[], value: unknown) => string(value) && values.includes(value);
const nullableString = (value: unknown) => value === null || string(value);
const nullableNumber = (value: unknown) => value === null || number(value);
const dimensionIds = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"] as const;
const dimensionValue = (value: unknown) => exact(value, ["score", "conf", "evidence_turn_ids"])
  && nullableNumber(value.score) && nullableNumber(value.conf) && strings(value.evidence_turn_ids);
const safetyAlert = (value: unknown) => exact(value, ["alert_type", "severity", "evidence_turn_ids", "requires_ack"])
  && oneOf(ALERT_TYPES, value.alert_type) && oneOf(ALERT_SEVERITIES, value.severity)
  && strings(value.evidence_turn_ids) && value.requires_ack === true;
const structuredTimeline = (value: unknown) => exact(value, ["stage", "label", "ts"])
  && string(value.stage) && string(value.label) && string(value.ts);

export function validateAuthOk(value: unknown, sessionId: string): { type: "auth.ok"; session_id: string; role: Role } | null {
  if (!exact(value, ["type", "session_id", "role"]) || value.type !== "auth.ok"
      || value.session_id !== sessionId || !oneOf(["victim", "executive", "supervisor"], value.role)) return null;
  return value as { type: "auth.ok"; session_id: string; role: Role };
}

export function validateSocketEvent(value: unknown): SocketEvent | null {
  if (!record(value) || !string(value.type)) return null;
  let valid = false;
  switch (value.type) {
    case "assistant.turn":
      valid = exact(value, ["type", "turn_id", "text", "lang", "intent", "audio"])
        && string(value.turn_id) && string(value.text) && oneOf(["hi", "en"], value.lang)
        && string(value.intent) && oneOf(ASSISTANT_AUDIO, value.audio);
      break;
    case "transcript.line":
      valid = exact(value, ["type", "turn_id", "speaker", "text", "lang", "ts"])
        && string(value.turn_id) && oneOf(["victim", "assistant"], value.speaker) && string(value.text)
        && oneOf(["hi", "en"], value.lang) && string(value.ts);
      break;
    case "session.status":
      valid = exact(value, ["type", "state", "consent", "lang", "human_joined"])
        && oneOf(SESSION_STATES, value.state) && oneOf(CONSENT_STATUSES, value.consent)
        && oneOf(["hi", "en"], value.lang) && boolean(value.human_joined);
      break;
    case "timeline.update":
      valid = exact(value, ["type", "stage", "label", "ts"])
        && oneOf(TIMELINE_STAGES, value.stage) && string(value.label) && string(value.ts);
      break;
    case "officer.message":
      valid = exact(value, ["type", "turn_id", "text", "lang", "ts", "origin"])
        && string(value.turn_id) && string(value.text) && oneOf(["hi", "en"], value.lang)
        && string(value.ts) && value.origin === "human_officer";
      break;
    case "dimension.update":
      valid = exact(value, ["type", "dims", "svi", "band", "needs_human", "overrides_applied"])
        && exact(value.dims, dimensionIds) && Object.values(value.dims).every(dimensionValue)
        && nullableNumber(value.svi)
        && (value.band === null || oneOf(BANDS, value.band)) && boolean(value.needs_human)
        && strings(value.overrides_applied);
      break;
    case "alert.safety":
      valid = exact(value, ["type", "alert_type", "severity", "evidence_turn_ids", "requires_ack"])
        && oneOf(ALERT_TYPES, value.alert_type) && oneOf(ALERT_SEVERITIES, value.severity)
        && strings(value.evidence_turn_ids) && value.requires_ack === true;
      break;
    case "case.structured":
      valid = exact(value, ["type", "incident", "timeline", "persons", "threats", "safety_now",
        "medical_need", "legal_status", "isolation", "requested_support"])
        && nullableString(value.incident) && Array.isArray(value.timeline) && value.timeline.every(structuredTimeline)
        && strings(value.persons) && strings(value.threats) && nullableString(value.safety_now)
        && nullableString(value.medical_need) && nullableString(value.legal_status)
        && nullableString(value.isolation) && nullableString(value.requested_support);
      break;
    case "action.recommended":
      valid = exact(value, ["type", "action_id", "action_type", "rationale", "policy_citations", "confidence"])
        && string(value.action_id) && string(value.action_type) && string(value.rationale)
        && strings(value.policy_citations) && number(value.confidence);
      break;
    case "safesignal.flag":
      valid = exact(value, ["type", "direction", "delta", "suggested_question"])
        && oneOf(["up", "down"], value.direction) && number(value.delta) && string(value.suggested_question);
      break;
    case "escalation.packet":
      valid = exact(value, ["type", "case_id", "band", "alerts", "summary", "ready"])
        && string(value.case_id) && (value.band === null || oneOf(BANDS, value.band))
        && Array.isArray(value.alerts) && value.alerts.every(safetyAlert)
        && string(value.summary) && value.ready === true;
      break;
  }
  return valid ? value as unknown as SocketEvent : null;
}
