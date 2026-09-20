/**
 * Backend base URL from EXPO_PUBLIC_API_URL.
 *
 * The value is configuration, not a secret, but it is still never echoed:
 * a malformed value might carry credentials or a query string. There is no
 * default and no localhost fallback. A USB development port forward (for
 * example device 18000 to backend 8000 over ADB) is set by the operator in the
 * environment, never here.
 */

const URL_PATTERN = new RegExp(
  "^(https?)://"
    + "(\\[[0-9a-f:.]+\\]|[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*)"
    + "(?::([0-9]{1,5}))?"
    + "((?:/[a-z0-9._~-]*)*)$",
  "i",
);

function resolveApiBaseUrl(raw) {
  if (typeof raw !== "string" || raw.trim().length === 0) {
    return { ok: false, error: "missing" };
  }

  const match = URL_PATTERN.exec(raw.trim());
  if (match === null) return { ok: false, error: "invalid" };

  const scheme = match[1].toLowerCase();
  const host = match[2].toLowerCase();
  const port = match[3];
  const path = match[4].replace(/\/+$/, "");

  if (port !== undefined) {
    const value = Number(port);
    if (!Number.isInteger(value) || value < 1 || value > 65535) {
      return { ok: false, error: "invalid" };
    }
  }

  const segments = path.split("/").slice(1);
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) {
    return { ok: false, error: "invalid" };
  }

  return {
    ok: true,
    baseUrl: `${scheme}://${host}${port === undefined ? "" : `:${Number(port)}`}${path}`,
  };
}

function configuredApiUrl() {
  // Direct member access so Expo inlines the public variable at build time.
  return process.env.EXPO_PUBLIC_API_URL;
}

module.exports = { configuredApiUrl, resolveApiBaseUrl };
