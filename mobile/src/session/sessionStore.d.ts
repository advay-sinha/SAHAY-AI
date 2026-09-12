import type { FetchLike, RequestConsent, RequestLang, ValidatedSession } from "../net/restClient";
import type { VictimTimeline } from "../net/victimPayload";
import type { MyRequestsLoadState } from "../screens/myRequestsState";

/** What screens may read. The session token is deliberately absent. */
export interface PublicSession {
  readonly session_id: string;
  readonly case_id: string;
  readonly reference_no: string;
  readonly ws_url: string;
  readonly lang: RequestLang;
  readonly consent: RequestConsent;
}

export interface SessionCreationState {
  readonly status: "idle" | "creating" | "failed" | "succeeded";
  readonly consent: RequestConsent | null;
  readonly lang: RequestLang | null;
  readonly attempt: number;
}

export interface TimelineState {
  readonly status: "idle" | "loading" | "ready" | "failed" | "unavailable";
  readonly payload: VictimTimeline | null;
}

export interface SessionSnapshot {
  readonly configured: boolean;
  readonly session: PublicSession | null;
  readonly creation: SessionCreationState;
  readonly timeline: TimelineState;
}

export type StartSessionResult =
  | { ok: true; session: PublicSession }
  | {
      ok: false;
      reason:
        | "invalid"
        | "active"
        | "in_flight"
        | "decided"
        | "not_failed"
        | "stale"
        | "config"
        | "network"
        | "timeout"
        | "aborted"
        | "http"
        | "malformed";
    };

export interface SessionStore {
  subscribe(listener: () => void): () => void;
  getSnapshot(): SessionSnapshot;
  startSession(consent: RequestConsent, lang: RequestLang): Promise<StartSessionResult>;
  retrySessionCreation(): Promise<StartSessionResult>;
  clearSession(): void;
  loadTimeline(): Promise<void>;
  cancelTimeline(): void;
}

export function createSessionStore(options: {
  apiUrl: unknown;
  fetchImpl: FetchLike;
  timeoutMs?: number;
  /** Private construction boundary for transports; never included in a snapshot. */
  onCredentialChange?: (session: ValidatedSession | null) => void;
}): SessionStore;

export function timelineLoadState(timeline: TimelineState): MyRequestsLoadState;
