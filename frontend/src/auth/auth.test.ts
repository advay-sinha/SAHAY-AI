/**
 * Console login, session and route protection.
 *
 * Runs in vitest's node environment against the pure auth modules, with an
 * in-memory store standing in for sessionStorage and a fake fetch standing in
 * for the network. No jsdom and no browser automation: neither is an approved
 * dependency.
 *
 * Tokens here are unsigned fixtures. The console never verifies signatures;
 * the backend does (backend/tests/test_auth.py).
 */

import { describe, expect, it, vi } from "vitest";

import { createApiClient, ApiError } from "../api/client";
import { readClaims } from "./jwt";
import { LOGIN_ERROR_MESSAGES, parseLoginResponse, requestLogin } from "./login";
import { accessFor, decide, homeFor, navFor, PATHS, shouldScrubQuery } from "./routing";
import {
  clearSession,
  memoryStore,
  readSession,
  SESSION_KEY,
  writeSession,
  type Session,
} from "./session";

const NOW = Date.UTC(2026, 8, 10, 12, 0, 0);
const HOUR = 3600;

function b64url(value: object): string {
  return btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function makeToken(claims: Record<string, unknown>): string {
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(claims)}.sig`;
}

function tokenFor(role: string, expOffsetSeconds = HOUR): string {
  return makeToken({ sub: `u-${role}`, role, iat: NOW / 1000, exp: NOW / 1000 + expOffsetSeconds });
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** fetch double that records every call. */
function fakeFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({ url, init });
    return handler(url, init);
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

function authHeader(init: RequestInit): string | null {
  return new Headers(init.headers).get("Authorization");
}

function sessionFor(role: "executive" | "supervisor"): Session {
  const store = memoryStore();
  const s = writeSession(store, tokenFor(role), role, `${role} user`, NOW);
  if (!s) throw new Error("fixture failed");
  return s;
}

// ---------------------------------------------------------------------------
// URL-token regression guard
// ---------------------------------------------------------------------------

describe("a token in the page URL never authenticates", () => {
  const FAKE = "fake-token";
  const REAL_LOOKING = tokenFor("supervisor");

  it("opening /login?token=fake-token leaves the user signed out", () => {
    const store = memoryStore();
    // What the app does on load: read the session. The URL is not an input.
    const session = readSession(store, NOW);
    expect(session).toBeNull();
    expect(decide(PATHS.queue, session)).toEqual({ kind: "redirect", to: PATHS.login });
    expect(decide(PATHS.supervisor, session)).toEqual({ kind: "redirect", to: PATHS.login });
    expect(decide(PATHS.login, session)).toEqual({ kind: "allow" });
  });

  it("even a well-formed token in the URL is not copied into storage", () => {
    const store = memoryStore();
    readSession(store, NOW);
    expect(store.dump()).toEqual({});
    expect(JSON.stringify(store.dump())).not.toContain(REAL_LOOKING);
  });

  it("no request carries an Authorization header while signed out", async () => {
    const store = memoryStore();
    const { fn, calls } = fakeFetch(() => jsonResponse(401, { detail: "Not authenticated" }));
    const api = createApiClient({
      fetchFn: fn,
      getToken: () => readSession(store, NOW)?.token ?? null,
      onUnauthorized: () => clearSession(store),
    });
    await expect(api.queue()).rejects.toBeInstanceOf(ApiError);
    expect(calls).toHaveLength(1);
    expect(authHeader(calls[0]!.init)).toBeNull();
    expect(calls[0]!.url).not.toContain(FAKE);
    expect(calls[0]!.url).not.toContain("token=");
  });

  it("decide() takes a pathname only, and redirects never carry a query or fragment", () => {
    const sessions: (Session | null)[] = [null, sessionFor("executive"), sessionFor("supervisor")];
    const paths = [PATHS.login, PATHS.queue, PATHS.supervisor, PATHS.audit, "/cases/c1", "/"];
    for (const s of sessions) {
      for (const p of paths) {
        const d = decide(p, s);
        if (d.kind === "redirect") {
          expect(d.to).not.toMatch(/[?#]/);
          expect(d.to).not.toContain("token");
        }
      }
    }
  });

  it("the login page scrubs any query string from the address bar", () => {
    expect(shouldScrubQuery(`?token=${FAKE}`)).toBe(true);
    expect(shouldScrubQuery("?next=/queue")).toBe(true);
    expect(shouldScrubQuery("")).toBe(false);
  });

  it("no console source file reads query parameters or a URL token", () => {
    const sources = import.meta.glob(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    const forbidden = [
      /URLSearchParams/,
      /useSearchParams/,
      /searchParams/,
      /\.get\(\s*["']token["']\s*\)/,
      /location\.(href|search)\s*\+?=/, // writing to the URL
    ];
    const offences: string[] = [];
    for (const [file, text] of Object.entries(sources)) {
      // Strip comments: files are allowed to explain the rule.
      const code = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
      for (const pattern of forbidden) if (pattern.test(code)) offences.push(`${file}: ${pattern}`);
    }
    expect(Object.keys(sources).length).toBeGreaterThan(5);
    expect(offences).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

describe("login", () => {
  it("normal username/password login succeeds and stores a validated session", async () => {
    const token = tokenFor("executive");
    const { fn, calls } = fakeFetch(() =>
      jsonResponse(200, { token, role: "executive", display_name: "Executive One" }),
    );
    const outcome = await requestLogin(fn, "exec1", "pw");
    expect(outcome).toEqual({ ok: true, token, role: "executive", displayName: "Executive One" });

    expect(calls[0]!.url).toBe("/api/auth/login");
    expect(calls[0]!.init.method).toBe("POST");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ username: "exec1", password: "pw" });
    expect(calls[0]!.url).not.toContain("pw");

    const store = memoryStore();
    if (!outcome.ok) throw new Error("unreachable");
    const session = writeSession(store, outcome.token, outcome.role, outcome.displayName, NOW);
    expect(session?.role).toBe("executive");
    expect(readSession(store, NOW)?.token).toBe(token);
    expect(JSON.stringify(store.dump())).not.toContain("pw");
  });

  it("after login, API requests carry Authorization: Bearer", async () => {
    const store = memoryStore();
    const token = tokenFor("executive");
    writeSession(store, token, "executive", "", NOW);
    const { fn, calls } = fakeFetch(() => jsonResponse(200, []));
    const api = createApiClient({
      fetchFn: fn,
      getToken: () => readSession(store, NOW)?.token ?? null,
      onUnauthorized: () => clearSession(store),
    });
    await api.queue();
    expect(authHeader(calls[0]!.init)).toBe(`Bearer ${token}`);
    expect(calls[0]!.url).toBe("/api/queue");
  });

  it("invalid credentials give a safe, fixed message and store nothing", async () => {
    const { fn } = fakeFetch(() => jsonResponse(401, { detail: "Invalid username or password" }));
    const outcome = await requestLogin(fn, "exec1", "wrong");
    expect(outcome).toEqual({ ok: false, error: "invalid_credentials" });
    expect(LOGIN_ERROR_MESSAGES.invalid_credentials).toBe("The username or password is incorrect.");
  });

  it("a server fault never surfaces internals", async () => {
    const { fn } = fakeFetch(
      () => new Response("Traceback: sqlite3.OperationalError at /srv/secret", { status: 500 }),
    );
    const outcome = await requestLogin(fn, "exec1", "pw");
    expect(outcome).toEqual({ ok: false, error: "unavailable" });
    for (const message of Object.values(LOGIN_ERROR_MESSAGES)) {
      expect(message).not.toMatch(/Traceback|sqlite|secret|500/i);
    }
  });

  it("a network failure is reported as unavailable", async () => {
    const fn = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    expect(await requestLogin(fn, "exec1", "pw")).toEqual({ ok: false, error: "unavailable" });
  });

  it("rejects a response with the wrong shape or a non-console role", () => {
    expect(parseLoginResponse({ token: "t", role: "victim" })).toBeNull();
    expect(parseLoginResponse({ token: "", role: "executive" })).toBeNull();
    expect(parseLoginResponse({ role: "executive" })).toBeNull();
    expect(parseLoginResponse(null)).toBeNull();
    expect(parseLoginResponse("token")).toBeNull();
    expect(parseLoginResponse({ token: "t", role: "executive" })).toEqual({
      token: "t",
      role: "executive",
      displayName: "",
    });
  });

  it("a token whose role disagrees with the response is not stored", () => {
    const store = memoryStore();
    const s = writeSession(store, tokenFor("executive"), "supervisor", "", NOW);
    expect(s).toBeNull();
    expect(store.dump()).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// Session lifecycle — fails closed
// ---------------------------------------------------------------------------

describe("session lifecycle", () => {
  it("logout removes the stored session", () => {
    const store = memoryStore();
    writeSession(store, tokenFor("executive"), "executive", "", NOW);
    expect(readSession(store, NOW)).not.toBeNull();
    clearSession(store);
    expect(readSession(store, NOW)).toBeNull();
    expect(store.getItem(SESSION_KEY)).toBeNull();
  });

  it("a backend 401 clears the stored session", async () => {
    const store = memoryStore();
    writeSession(store, tokenFor("executive"), "executive", "", NOW);
    const onUnauthorized = vi.fn(() => clearSession(store));
    const { fn } = fakeFetch(() => jsonResponse(401, { detail: "Not authenticated" }));
    const api = createApiClient({
      fetchFn: fn,
      getToken: () => readSession(store, NOW)?.token ?? null,
      onUnauthorized,
    });
    await expect(api.queue()).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(readSession(store, NOW)).toBeNull();
  });

  it("a 403 or 500 does not sign the user out", async () => {
    const store = memoryStore();
    writeSession(store, tokenFor("executive"), "executive", "", NOW);
    for (const status of [403, 500]) {
      const onUnauthorized = vi.fn();
      const { fn } = fakeFetch(() => jsonResponse(status, { detail: "x" }));
      const api = createApiClient({ fetchFn: fn, getToken: () => "t", onUnauthorized });
      await expect(api.queue()).rejects.toMatchObject({ status });
      expect(onUnauthorized).not.toHaveBeenCalled();
    }
    expect(readSession(store, NOW)).not.toBeNull();
  });

  it("an expired session is dropped on read", () => {
    const store = memoryStore();
    writeSession(store, tokenFor("executive", 60), "executive", "", NOW);
    expect(readSession(store, NOW + 61_000)).toBeNull();
    expect(store.getItem(SESSION_KEY)).toBeNull();
  });

  it("an already-expired token is never stored", () => {
    const store = memoryStore();
    expect(writeSession(store, tokenFor("executive", -1), "executive", "", NOW)).toBeNull();
    expect(store.dump()).toEqual({});
  });

  it("malformed or tampered storage fails closed", () => {
    const cases = [
      "not json",
      JSON.stringify({ token: "garbage", role: "executive" }),
      JSON.stringify({ token: tokenFor("executive"), role: "supervisor" }), // tampered role
      JSON.stringify({ token: makeToken({ sub: "x", role: "admin", exp: NOW / 1000 + HOUR }), role: "admin" }),
      JSON.stringify({ token: makeToken({ role: "executive", exp: NOW / 1000 + HOUR }), role: "executive" }),
      JSON.stringify({ token: makeToken({ sub: "x", role: "executive" }), role: "executive" }),
      JSON.stringify(null),
    ];
    for (const raw of cases) {
      const store = memoryStore();
      store.setItem(SESSION_KEY, raw);
      expect(readSession(store, NOW)).toBeNull();
      expect(store.getItem(SESSION_KEY)).toBeNull();
    }
  });

  it("readClaims never throws on garbage", () => {
    for (const bad of [undefined, null, 42, "", "a.b", "a.b.c", "x.!!!.y", {}]) {
      expect(readClaims(bad)).toBeNull();
    }
  });
});

// ---------------------------------------------------------------------------
// Role-based routing
// ---------------------------------------------------------------------------

describe("role-based redirects and protected routes", () => {
  const executive = sessionFor("executive");
  const supervisor = sessionFor("supervisor");

  it("sends each role to its home after login", () => {
    expect(homeFor("executive")).toBe(PATHS.queue);
    expect(homeFor("supervisor")).toBe(PATHS.supervisor);
  });

  it("keeps signed-in users off the login page", () => {
    expect(decide(PATHS.login, executive)).toEqual({ kind: "redirect", to: PATHS.queue });
    expect(decide(PATHS.login, supervisor)).toEqual({ kind: "redirect", to: PATHS.supervisor });
  });

  it("sends anonymous users to /login from every protected route", () => {
    for (const p of [PATHS.queue, PATHS.audit, PATHS.supervisor, "/cases/c1", "/supervisor/x"]) {
      expect(decide(p, null)).toEqual({ kind: "redirect", to: PATHS.login });
    }
  });

  it("rejects direct navigation to a supervisor route by an executive", () => {
    expect(accessFor("/supervisor")).toBe("supervisor");
    expect(accessFor("/supervisor/reassign")).toBe("supervisor");
    expect(decide(PATHS.supervisor, executive)).toEqual({ kind: "redirect", to: PATHS.queue });
    expect(decide("/supervisor/reassign", executive)).toEqual({ kind: "redirect", to: PATHS.queue });
  });

  it("lets a supervisor use supervisor and console routes", () => {
    expect(decide(PATHS.supervisor, supervisor)).toEqual({ kind: "allow" });
    expect(decide(PATHS.queue, supervisor)).toEqual({ kind: "allow" });
  });

  it("lets an executive use console routes", () => {
    for (const p of [PATHS.queue, PATHS.audit, "/cases/c1"]) {
      expect(decide(p, executive)).toEqual({ kind: "allow" });
    }
  });

  it("hides supervisor navigation from executives", () => {
    expect(navFor("executive").map((i) => i.to)).not.toContain(PATHS.supervisor);
    expect(navFor("supervisor").map((i) => i.to)).toContain(PATHS.supervisor);
  });
});
