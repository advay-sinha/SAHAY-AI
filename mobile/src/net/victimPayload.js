const EVENT_TYPES = Object.freeze([
  "assistant.turn",
  "transcript.line",
  "session.status",
  "timeline.update",
  "officer.message",
]);

const LANGUAGES = Object.freeze(["hi", "en"]);
const AUDIO_KINDS = Object.freeze(["streaming", "prerecorded"]);
const TRANSCRIPT_SPEAKERS = Object.freeze(["victim", "assistant"]);
const SESSION_STATES = Object.freeze([
  "S0",
  "S1",
  "S2",
  "S3",
  "S4",
  "S5",
  "S6",
  "S7",
  "S8",
  "S9",
  "SX",
  "SH",
]);
const CONSENT_STATUSES = Object.freeze(["granted", "declined", "pending"]);
const TIMELINE_STAGES = Object.freeze([
  "request_received",
  "under_review",
  "officer_assigned",
  "action_taken",
  "follow_up_scheduled",
  "closed",
]);

function isRecord(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  if (Object.getPrototypeOf(value) !== Object.prototype) return false;

  for (const key in value) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
  }
  return true;
}

function hasExactKeys(value, expected) {
  if (!isRecord(value)) return false;

  const actual = Reflect.ownKeys(value);
  return actual.length === expected.length
    && actual.every((key) => typeof key === "string" && expected.includes(key));
}

function isString(value) {
  return typeof value === "string";
}

function isOneOf(value, allowed) {
  return typeof value === "string" && allowed.includes(value);
}

function isAssistantTurn(value) {
  return hasExactKeys(value, ["type", "turn_id", "text", "lang", "intent", "audio"])
    && value.type === "assistant.turn"
    && isString(value.turn_id)
    && isString(value.text)
    && isOneOf(value.lang, LANGUAGES)
    && isString(value.intent)
    && isOneOf(value.audio, AUDIO_KINDS);
}

function isTranscriptLine(value) {
  return hasExactKeys(value, ["type", "turn_id", "speaker", "text", "lang", "ts"])
    && value.type === "transcript.line"
    && isString(value.turn_id)
    && isOneOf(value.speaker, TRANSCRIPT_SPEAKERS)
    && isString(value.text)
    && isOneOf(value.lang, LANGUAGES)
    && isString(value.ts);
}

function isSessionStatus(value) {
  return hasExactKeys(value, ["type", "state", "consent", "lang", "human_joined"])
    && value.type === "session.status"
    && isOneOf(value.state, SESSION_STATES)
    && isOneOf(value.consent, CONSENT_STATUSES)
    && isOneOf(value.lang, LANGUAGES)
    && typeof value.human_joined === "boolean";
}

function isTimelineEntry(value, includeType) {
  const keys = includeType ? ["type", "stage", "label", "ts"] : ["stage", "label", "ts"];
  return hasExactKeys(value, keys)
    && (!includeType || value.type === "timeline.update")
    && isOneOf(value.stage, TIMELINE_STAGES)
    && isString(value.label)
    && isString(value.ts);
}

function isOfficerMessage(value) {
  return hasExactKeys(value, ["type", "turn_id", "text", "lang", "ts", "origin"])
    && value.type === "officer.message"
    && isString(value.turn_id)
    && isString(value.text)
    && isOneOf(value.lang, LANGUAGES)
    && isString(value.ts)
    && value.origin === "human_officer";
}

function validateVictimEvent(value) {
  try {
    if (!isRecord(value) || !isOneOf(value.type, EVENT_TYPES)) return null;

    switch (value.type) {
      case "assistant.turn":
        return isAssistantTurn(value) ? value : null;
      case "transcript.line":
        return isTranscriptLine(value) ? value : null;
      case "session.status":
        return isSessionStatus(value) ? value : null;
      case "timeline.update":
        return isTimelineEntry(value, true) ? value : null;
      case "officer.message":
        return isOfficerMessage(value) ? value : null;
      default:
        return null;
    }
  } catch {
    return null;
  }
}

function parseVictimEvent(raw) {
  if (typeof raw !== "string") return null;

  try {
    return validateVictimEvent(JSON.parse(raw));
  } catch {
    return null;
  }
}

function dispatchVictimEvent(raw, onEvent) {
  const event = parseVictimEvent(raw);
  if (event === null) return false;

  onEvent(event);
  return true;
}

function validateVictimTimeline(value) {
  try {
    if (!hasExactKeys(value, ["reference", "timeline"])) return null;
    if (!isString(value.reference) || !Array.isArray(value.timeline)) return null;
    if (!value.timeline.every((entry) => isTimelineEntry(entry, false))) return null;
    return value;
  } catch {
    return null;
  }
}

module.exports = {
  CONSENT_STATUSES,
  EVENT_TYPES,
  SESSION_STATES,
  TIMELINE_STAGES,
  dispatchVictimEvent,
  parseVictimEvent,
  validateVictimEvent,
  validateVictimTimeline,
};
