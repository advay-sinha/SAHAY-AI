import type { VictimTimeline } from "./victimPayload";

export type Lang = "hi" | "en";
export type Consent = "granted" | "declined";

export interface ActiveSession {
  session_id: string;
  case_id: string;
  reference_no: string;
  session_token: string;
  ws_url: string;
  lang: Lang;
  consent: Consent;
  ai_disclosure: string;
  human_request_available: boolean;
}

export class ApiError extends Error {
  kind: "authentication" | "configuration" | "malformed" | "request" | "unavailable";
  status: number | null;
}

export function validateApiBaseUrl(raw: unknown, isDevelopment: boolean): string;
export function validateSessionResponse(value: unknown): ActiveSession | null;
export function createSession(
  baseUrl: string,
  request: { channel: "mobile_chat"; consent: Consent; lang: Lang },
  transport?: typeof fetch,
): Promise<ActiveSession>;
export function getTimeline(
  baseUrl: string,
  session: ActiveSession,
  validateTimeline: (value: unknown) => VictimTimeline | null,
  transport?: typeof fetch,
): Promise<VictimTimeline>;
