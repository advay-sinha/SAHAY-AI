/**
 * Shared REST client. Shapes come from ../types, never from inference.
 *
 * Authentication: the session token is attached as `Authorization: Bearer`.
 * It never goes into a URL. A 401 from any call means the session is no longer
 * valid: `onUnauthorized` clears it and sends the user to /login.
 *
 * Errors carry the HTTP status and, for 400/409, the server's short fixed
 * message (e.g. "claim the case before acting on it"), which the backend
 * guarantees contains no stack trace, secret or case text. Other bodies are
 * never surfaced.
 */

import type {
  AlertAckResponse,
  Band,
  DecisionKind,
  Lang,
  OfficerMessageResponse,
  VictimTimeline,
} from "../types/contracts";
import type { AuditEntry, CasePacket, QueueItem } from "../types/packet";
import {
  ResponseValidationError,
  validateAlertAck,
  validateAudit,
  validateCasePacket,
  validateClaim,
  validateDecision,
  validateHealth,
  validateOfficerMessage,
  validateOverride,
  validateQueue,
  validateTakeover,
  validateTimeline,
} from "./validation";

export const API_BASE: string = import.meta.env.VITE_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string | null = null,
  ) {
    super(detail ?? (status === 0 ? "network error" : `request failed (${status})`));
    this.name = "ApiError";
  }
}

export interface ApiDeps {
  fetchFn: typeof fetch;
  /** Returns the current token, or null when signed out. */
  getToken: () => string | null;
  /** Called on any 401. Must clear the session. */
  onUnauthorized: () => void;
  base?: string;
}

const SAFE_DETAIL_STATUSES = new Set([400, 403, 404, 409]);

export function createApiClient({ fetchFn, getToken, onUnauthorized, base = API_BASE }: ApiDeps) {
  async function request<T>(path: string, validate: (value: unknown) => T, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    let response: Response;
    try {
      response = await fetchFn(`${base}${path}`, { ...init, headers });
    } catch {
      throw new ApiError(0);
    }

    if (response.status === 401) {
      onUnauthorized();
      throw new ApiError(401);
    }
    if (!response.ok) {
      let detail: string | null = null;
      if (SAFE_DETAIL_STATUSES.has(response.status)) {
        try {
          const body = (await response.json()) as { detail?: unknown };
          if (typeof body.detail === "string" && body.detail.length <= 200) detail = body.detail;
        } catch {
          /* no usable detail */
        }
      }
      throw new ApiError(response.status, detail);
    }
    let value: unknown;
    try {
      value = await response.json();
      return validate(value);
    } catch (error) {
      if (error instanceof ResponseValidationError) throw new ApiError(502);
      throw new ApiError(502);
    }
  }

  const post = <T>(path: string, validate: (value: unknown) => T, body?: unknown) =>
    request<T>(path, validate, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  const id = encodeURIComponent;

  return {
    health: () => request("/health", validateHealth),
    queue: () => request<QueueItem[]>("/queue", validateQueue),
    case: (caseId: string) => request<CasePacket>(`/cases/${id(caseId)}`, validateCasePacket),
    claim: (caseId: string) => post(`/cases/${id(caseId)}/claim`, validateClaim),
    acknowledge: (caseId: string, alertId: string) =>
      post<AlertAckResponse>(`/cases/${id(caseId)}/alerts/${id(alertId)}/ack`, validateAlertAck),
    decide: (caseId: string, actionId: string, decision: DecisionKind, rationale: string) =>
      post(`/cases/${id(caseId)}/decisions`, validateDecision, { action_id: actionId, decision, rationale }),
    /** reason is required by contract; the server refuses a blank one with 400. */
    override: (caseId: string, band: Band, reason: string) =>
      post(`/cases/${id(caseId)}/override`, validateOverride, { band, reason }),
    takeover: (caseId: string) => post(`/cases/${id(caseId)}/takeover`, validateTakeover),
    /** PC-07: only after takeover (409 before). The officer's own words. */
    message: (caseId: string, text: string, lang?: Lang) =>
      post<OfficerMessageResponse>(`/cases/${id(caseId)}/messages`, validateOfficerMessage, { text, lang }),
    timeline: (caseId: string) => request<VictimTimeline>(`/cases/${id(caseId)}/timeline`, validateTimeline),
    audit: (caseId: string) => request<AuditEntry[]>(`/cases/${id(caseId)}/audit`, validateAudit),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
