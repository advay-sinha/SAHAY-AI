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
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
    return (await response.json()) as T;
  }

  const post = <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  const id = encodeURIComponent;

  return {
    request,
    health: () =>
      request<{ status: string; llm_provider: string; assessment_runner: string; fixed_scripts_ready: boolean }>("/health"),
    queue: () => request<QueueItem[]>("/queue"),
    case: (caseId: string) => request<CasePacket>(`/cases/${id(caseId)}`),
    claim: (caseId: string) => post<{ case_id: string; status: string }>(`/cases/${id(caseId)}/claim`),
    acknowledge: (caseId: string, alertId: string) =>
      post<AlertAckResponse>(`/cases/${id(caseId)}/alerts/${id(alertId)}/ack`),
    decide: (caseId: string, actionId: string, decision: DecisionKind, rationale: string) =>
      post<{ decision_id: string }>(`/cases/${id(caseId)}/decisions`, { action_id: actionId, decision, rationale }),
    /** reason is required by contract; the server refuses a blank one with 400. */
    override: (caseId: string, band: Band, reason: string) =>
      post<{ to_band: Band }>(`/cases/${id(caseId)}/override`, { band, reason }),
    takeover: (caseId: string) => post<{ status: string }>(`/cases/${id(caseId)}/takeover`),
    /** PC-07: only after takeover (409 before). The officer's own words. */
    message: (caseId: string, text: string, lang?: Lang) =>
      post<OfficerMessageResponse>(`/cases/${id(caseId)}/messages`, { text, lang }),
    timeline: (caseId: string) => request<VictimTimeline>(`/cases/${id(caseId)}/timeline`),
    audit: (caseId: string) => request<AuditEntry[]>(`/cases/${id(caseId)}/audit`),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
