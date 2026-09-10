/**
 * Read — never verify — a JWT payload.
 *
 * The console cannot verify a signature: it does not hold the secret, and must
 * not. It reads `role` and `exp` only to decide navigation and to drop a
 * session that has obviously expired. The backend verifies every request and
 * is the only authority on what a token permits.
 */

export interface TokenClaims {
  sub: string;
  role: string;
  exp: number; // seconds since epoch
  iat?: number;
}

const JWT_SHAPE = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$/;

function base64UrlDecode(segment: string): string {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** Returns the claims, or null for anything malformed. Never throws. */
export function readClaims(token: unknown): TokenClaims | null {
  if (typeof token !== "string" || !JWT_SHAPE.test(token)) return null;
  try {
    const payload: unknown = JSON.parse(base64UrlDecode(token.split(".")[1] ?? ""));
    if (typeof payload !== "object" || payload === null) return null;
    const { sub, role, exp, iat } = payload as Record<string, unknown>;
    if (typeof sub !== "string" || sub.length === 0) return null;
    if (typeof role !== "string") return null;
    if (typeof exp !== "number" || !Number.isFinite(exp)) return null;
    return { sub, role, exp, iat: typeof iat === "number" ? iat : undefined };
  } catch {
    return null;
  }
}
