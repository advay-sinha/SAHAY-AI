/**
 * Route access decisions. Pure: pathname and session in, decision out.
 *
 * Deliberately takes a pathname, not a URL. The query string is never an
 * input, so no query parameter can influence who is logged in or where they
 * are sent. Every redirect target is a bare path: no query, no fragment, and
 * therefore nothing a token could ride along in.
 *
 * This is navigation only. The backend checks the Bearer token and role on
 * every request, and is the authority.
 */

import type { ConsoleRole, Session } from "./session";

export const PATHS = {
  login: "/login",
  queue: "/queue",
  supervisor: "/supervisor",
  audit: "/audit",
} as const;

export type Access = "public" | "console" | "supervisor";

export function homeFor(role: ConsoleRole): string {
  return role === "supervisor" ? PATHS.supervisor : PATHS.queue;
}

export function accessFor(pathname: string): Access {
  if (pathname === PATHS.login) return "public";
  if (pathname === PATHS.supervisor || pathname.startsWith(`${PATHS.supervisor}/`)) {
    return "supervisor";
  }
  return "console";
}

export type Decision = { kind: "allow" } | { kind: "redirect"; to: string };

export function decide(pathname: string, session: Session | null): Decision {
  const access = accessFor(pathname);

  if (access === "public") {
    // An authenticated user has no business on the login page.
    return session ? { kind: "redirect", to: homeFor(session.role) } : { kind: "allow" };
  }
  if (!session) return { kind: "redirect", to: PATHS.login };
  if (access === "supervisor" && session.role !== "supervisor") {
    return { kind: "redirect", to: homeFor(session.role) };
  }
  return { kind: "allow" };
}

/** Navigation entries a role may see. Supervisor-only items are absent for executives. */
export function navFor(role: ConsoleRole): { to: string; label: string }[] {
  const items: { to: string; label: string }[] = [
    { to: PATHS.queue, label: "Queue" },
    { to: PATHS.audit, label: "Audit" },
  ];
  if (role === "supervisor") items.push({ to: PATHS.supervisor, label: "Supervisor" });
  return items;
}

/** True when the login page was opened with any query string; it is scrubbed. */
export function shouldScrubQuery(search: string): boolean {
  return search.length > 0 && search !== "?";
}
