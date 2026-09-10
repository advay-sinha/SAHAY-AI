/**
 * The ONLY events this app knows about.
 *
 * mobile/CLAUDE.md: this app never displays the SVI, the risk band, the nine
 * dimensions, detected emotions, alerts, or any part of the assessment.
 *
 * There is deliberately no import from the console's contract mirror here. The
 * victim app defines the four events it is allowed to receive and nothing else,
 * so an assessment type cannot arrive by autocomplete.
 *
 * Mirrors backend/app/ws/events.py VICTIM_ALLOWED and CONTRACTS.md section 2
 * (backend/tests/test_contract_mirror.py checks all three agree).
 */

export type Lang = "hi" | "en";

export interface AssistantTurn {
  turn_id: string;
  text: string;
  lang: Lang;
  intent: string;
  audio: "streaming" | "prerecorded";
}

export interface TranscriptLine {
  turn_id: string;
  speaker: "victim" | "assistant";
  text: string;
  lang: Lang;
  ts: string;
}

export interface SessionStatus {
  state: string;
  consent: string;
  lang: Lang;
  human_joined: boolean;
}

export interface TimelineUpdate {
  stage: string;
  label: string;
  ts: string;
}

/**
 * PC-07: a message typed by the human officer who took over the conversation.
 * Show it as coming from a person ("Officer"), never as the assistant. It
 * carries no assessment field.
 */
export interface OfficerMessage {
  turn_id: string;
  text: string;
  lang: Lang;
  ts: string;
  origin: "human_officer";
}

export type VictimEvent =
  | ({ type: "assistant.turn" } & AssistantTurn)
  | ({ type: "transcript.line" } & TranscriptLine)
  | ({ type: "session.status" } & SessionStatus)
  | ({ type: "timeline.update" } & TimelineUpdate)
  | ({ type: "officer.message" } & OfficerMessage);

export const ALLOWED_EVENT_TYPES = [
  "assistant.turn",
  "transcript.line",
  "session.status",
  "timeline.update",
  "officer.message",
] as const;
