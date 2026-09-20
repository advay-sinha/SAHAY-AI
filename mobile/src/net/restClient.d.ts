import type { VictimTimeline } from "./victimPayload";

export type RequestConsent = "granted" | "declined";
export type RequestLang = "hi" | "en";

export interface CreateSessionRequest {
  channel: "mobile_chat";
  consent: RequestConsent;
  lang: RequestLang;
}

/** The PC-09 fields the app keeps. ai_disclosure is validated, not kept. */
export interface ValidatedSession {
  session_id: string;
  case_id: string;
  reference_no: string;
  session_token: string;
  ws_url: string;
  lang: RequestLang;
  consent: RequestConsent;
}

export interface FetchResponseLike {
  status: number;
  text(): Promise<string>;
}

export interface FetchInit {
  method: string;
  headers: Record<string, string>;
  body?: string;
  signal: AbortSignal;
}

export type FetchLike = (url: string, init: FetchInit) => Promise<FetchResponseLike>;

export type CreateSessionFailure =
  | "invalid"
  | "network"
  | "timeout"
  | "aborted"
  | "http"
  | "malformed";

export type CreateSessionResult =
  | { ok: true; session: ValidatedSession }
  | { ok: false; reason: CreateSessionFailure };

export type TimelineResult =
  | { kind: "ready"; timeline: VictimTimeline }
  | { kind: "unauthenticated" }
  | { kind: "forbidden" }
  | { kind: "not_found" }
  | { kind: "aborted" }
  | { kind: "failed"; reason: "invalid" | "network" | "timeout" | "http" | "malformed" };

export const DEFAULT_TIMEOUT_MS: number;
export const SESSION_RESPONSE_KEYS: readonly string[];

export function buildCreateSessionRequest(
  consent: unknown,
  lang: unknown,
): CreateSessionRequest | null;

export function validateCreateSessionResponse(
  value: unknown,
  requested: { consent: RequestConsent; lang: RequestLang },
): ValidatedSession | null;

export function validateTimelineResponse(value: unknown): VictimTimeline | null;

export function createSession(options: {
  fetchImpl: FetchLike;
  baseUrl: string;
  consent: RequestConsent;
  lang: RequestLang;
  timeoutMs?: number;
}): Promise<CreateSessionResult>;

export function fetchTimeline(options: {
  fetchImpl: FetchLike;
  baseUrl: string;
  caseId: string;
  sessionToken: string;
  signal?: AbortSignal;
  timeoutMs?: number;
}): Promise<TimelineResult>;
