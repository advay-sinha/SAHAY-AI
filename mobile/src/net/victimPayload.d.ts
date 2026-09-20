import type { VictimEvent } from "../types/events";

export type TimelineStage =
  | "request_received"
  | "under_review"
  | "officer_assigned"
  | "action_taken"
  | "follow_up_scheduled"
  | "closed";

export interface VictimTimelineEntry {
  stage: TimelineStage;
  label: string;
  ts: string;
}

export interface VictimTimeline {
  reference: string;
  timeline: VictimTimelineEntry[];
}

export const EVENT_TYPES: readonly [
  "assistant.turn",
  "transcript.line",
  "session.status",
  "timeline.update",
  "officer.message",
];

export const SESSION_STATES: readonly [
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
];

export const CONSENT_STATUSES: readonly ["granted", "declined", "pending"];

export const TIMELINE_STAGES: readonly [
  "request_received",
  "under_review",
  "officer_assigned",
  "action_taken",
  "follow_up_scheduled",
  "closed",
];

export function validateVictimEvent(value: unknown): VictimEvent | null;
export function parseVictimEvent(raw: unknown): VictimEvent | null;
export function dispatchVictimEvent(
  raw: unknown,
  onEvent: (event: VictimEvent) => void,
): boolean;
export function validateVictimTimeline(value: unknown): VictimTimeline | null;
