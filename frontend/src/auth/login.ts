/**
 * POST /auth/login and interpretation of its answer.
 *
 * Errors are reduced to two kinds with fixed, user-facing wording. Nothing the
 * server returns — status text, body, stack trace — is ever shown, so a server
 * fault cannot leak internals into the UI.
 */

import { isConsoleRole, type ConsoleRole } from "./session";

export type LoginErrorKind = "invalid_credentials" | "unavailable";

export interface LoginSuccess {
  ok: true;
  token: string;
  role: ConsoleRole;
  displayName: string;
}

export interface LoginFailure {
  ok: false;
  error: LoginErrorKind;
}

export type LoginOutcome = LoginSuccess | LoginFailure;

export const LOGIN_ERROR_MESSAGES: Record<LoginErrorKind, string> = {
  invalid_credentials: "The username or password is incorrect.",
  unavailable: "Sign-in is unavailable right now. Please try again, or contact your supervisor.",
};

/** Validate the frozen exact response shape: `{token, role, display_name}`. */
export function parseLoginResponse(body: unknown): Omit<LoginSuccess, "ok"> | null {
  if (typeof body !== "object" || body === null || Array.isArray(body)) return null;
  if (Object.getPrototypeOf(body) !== Object.prototype) return null;
  const keys = Reflect.ownKeys(body);
  if (keys.length !== 3 || !keys.every((key) => typeof key === "string"
      && ["token", "role", "display_name"].includes(key))) return null;
  const { token, role, display_name } = body as Record<string, unknown>;
  if (typeof token !== "string" || token.length === 0) return null;
  if (!isConsoleRole(role)) return null;
  if (typeof display_name !== "string") return null;
  return {
    token,
    role,
    displayName: display_name,
  };
}

export async function requestLogin(
  fetchFn: typeof fetch,
  username: string,
  password: string,
  base: string = "/api",
): Promise<LoginOutcome> {
  let response: Response;
  try {
    response = await fetchFn(`${base}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    return { ok: false, error: "unavailable" };
  }

  // 401 is the server's uniform "invalid username or password". 422 is an
  // empty or oversized field; to the user that is the same thing.
  if (response.status === 401 || response.status === 422) {
    return { ok: false, error: "invalid_credentials" };
  }
  if (!response.ok) return { ok: false, error: "unavailable" };

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { ok: false, error: "unavailable" };
  }
  const parsed = parseLoginResponse(body);
  return parsed ? { ok: true, ...parsed } : { ok: false, error: "unavailable" };
}
