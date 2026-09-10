/**
 * Console session storage.
 *
 * Decision (local MVP): the project had no session mechanism, so the token is
 * kept in `sessionStorage` under one key. It survives a page reload, dies with
 * the tab, and is not shared across tabs. The frozen contract is Bearer-token
 * auth (HANDOVER.md 12.4); this does not introduce cookies.
 *
 * Known trade-off: sessionStorage is readable by any script on the page, so an
 * XSS bug could read the token. The mitigations are the ones the console
 * already has: no third-party scripts, no CDN assets, no `dangerouslySetInnerHTML`.
 * Production hardening (SSO/MFA, httpOnly cookies) is out of MVP scope per
 * HANDOVER.md section 8 and would be a contract change.
 *
 * Everything here fails closed: a malformed, expired, tampered or role-less
 * entry is deleted and treated as "not logged in".
 *
 * Nothing in this module reads the page URL. A token can enter storage only
 * through `writeSession`, which only the login flow calls.
 */

import { readClaims } from "./jwt";

export const SESSION_KEY = "sahay.console.session";

export type ConsoleRole = "executive" | "supervisor";
export const CONSOLE_ROLES: readonly ConsoleRole[] = ["executive", "supervisor"];

export function isConsoleRole(value: unknown): value is ConsoleRole {
  return typeof value === "string" && (CONSOLE_ROLES as readonly string[]).includes(value);
}

export interface Session {
  token: string;
  role: ConsoleRole;
  displayName: string;
  /** Milliseconds since epoch, taken from the token's `exp`. */
  expiresAt: number;
}

/** The subset of the Web Storage API this module needs. */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** In-memory store for tests, and a fallback when storage is blocked. */
export function memoryStore(): KeyValueStore & { dump(): Record<string, string> } {
  const data = new Map<string, string>();
  return {
    getItem: (k) => (data.has(k) ? (data.get(k) as string) : null),
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
    dump: () => Object.fromEntries(data),
  };
}

/** sessionStorage when available; memory otherwise (private mode, blocked storage). */
export function browserStore(): KeyValueStore {
  try {
    const probe = "__sahay_probe__";
    window.sessionStorage.setItem(probe, "1");
    window.sessionStorage.removeItem(probe);
    return window.sessionStorage;
  } catch {
    return memoryStore();
  }
}

/** Validate a token + role pair into a Session, or null. Pure. */
export function toSession(
  token: unknown,
  role: unknown,
  displayName: unknown,
  now: number,
): Session | null {
  if (!isConsoleRole(role)) return null;
  const claims = readClaims(token);
  if (!claims) return null;
  // The role the server sent must be the role inside the token.
  if (claims.role !== role) return null;
  const expiresAt = claims.exp * 1000;
  if (expiresAt <= now) return null;
  return {
    token: token as string,
    role,
    displayName: typeof displayName === "string" ? displayName : "",
    expiresAt,
  };
}

export function clearSession(store: KeyValueStore): void {
  store.removeItem(SESSION_KEY);
}

/** Read and re-validate the stored session. Deletes anything invalid. */
export function readSession(store: KeyValueStore, now: number = Date.now()): Session | null {
  const raw = store.getItem(SESSION_KEY);
  if (raw === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    clearSession(store);
    return null;
  }
  const record = (parsed ?? {}) as Record<string, unknown>;
  const session = toSession(record.token, record.role, record.displayName, now);
  if (!session) clearSession(store);
  return session;
}

/** Store a session. Returns null (and stores nothing) if it does not validate. */
export function writeSession(
  store: KeyValueStore,
  token: unknown,
  role: unknown,
  displayName: unknown,
  now: number = Date.now(),
): Session | null {
  const session = toSession(token, role, displayName, now);
  if (!session) {
    clearSession(store);
    return null;
  }
  store.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}
