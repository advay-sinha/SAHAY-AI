/**
 * Shared REST client. Shapes come from ../types/contracts, never from inference.
 *
 * Authentication: the session token is attached as `Authorization: Bearer`.
 * It never goes into a URL. A 401 from any call means the session is no longer
 * valid: `onUnauthorized` clears it and sends the user to /login.
 *
 * Errors carry the HTTP status only. Server response bodies are never surfaced
 * to the UI, so a backend fault cannot leak internals onto the screen.
 */

import type { DecisionRequest, OverrideRequest, VictimTimeline } from "../types/contracts";

export const API_BASE: string = import.meta.env.VITE_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 0 ? "network error" : `request failed (${status})`);
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
    if (!response.ok) throw new ApiError(response.status);
    return (await response.json()) as T;
  }

  return {
    request,
    health: () => request<{ status: string; llm_provider: string; assessment_runner: string; fixed_scripts_ready: boolean }>("/health"),
    queue: () => request<unknown[]>("/queue"),
    case: (caseId: string) => request<unknown>(`/cases/${encodeURIComponent(caseId)}`),
    claim: (caseId: string) =>
      request<unknown>(`/cases/${encodeURIComponent(caseId)}/claim`, { method: "POST" }),
    decide: (caseId: string, body: DecisionRequest) =>
      request<unknown>(`/cases/${encodeURIComponent(caseId)}/decisions`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    /** reason is required by contract; the server refuses a blank one. */
    override: (caseId: string, body: OverrideRequest) =>
      request<unknown>(`/cases/${encodeURIComponent(caseId)}/override`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    takeover: (caseId: string) =>
      request<unknown>(`/cases/${encodeURIComponent(caseId)}/takeover`, { method: "POST" }),
    timeline: (caseId: string) =>
      request<VictimTimeline>(`/cases/${encodeURIComponent(caseId)}/timeline`),
    audit: (caseId: string) => request<unknown[]>(`/cases/${encodeURIComponent(caseId)}/audit`),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
