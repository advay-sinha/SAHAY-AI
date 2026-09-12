const LANGUAGES = Object.freeze(["hi", "en"]);
const CONSENT = Object.freeze(["granted", "declined"]);
const SESSION_KEYS = Object.freeze([
  "session_id", "case_id", "reference_no", "session_token", "ws_url", "lang",
  "consent", "ai_disclosure", "human_request_available",
]);

class ApiError extends Error {
  constructor(kind, status = null) {
    super(kind);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

function hasExactKeys(value, keys) {
  if (!isRecord(value)) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length
    && actual.every((key) => typeof key === "string" && keys.includes(key));
}

function nonEmptyString(value) {
  return typeof value === "string" && value.length > 0;
}

function isLocalHostname(hostname) {
  const normalized = hostname.toLowerCase();
  if (isLoopbackHostname(normalized)) return true;
  if (/^10(?:\.[0-9]{1,3}){3}$/.test(normalized)) return true;
  if (/^192\.168(?:\.[0-9]{1,3}){2}$/.test(normalized)) return true;
  const match = /^172\.([0-9]{1,2})(?:\.[0-9]{1,3}){2}$/.exec(normalized);
  return match !== null && Number(match[1]) >= 16 && Number(match[1]) <= 31;
}

function isLoopbackHostname(hostname) {
  const normalized = hostname.toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1";
}

function validateApiBaseUrl(raw, options = {}) {
  if (typeof raw !== "string" || raw.length === 0) throw new ApiError("configuration");
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new ApiError("configuration");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") throw new ApiError("configuration");
  if (parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== "/") {
    throw new ApiError("configuration");
  }
  if (parsed.protocol === "http:") {
    const isProduction = options.buildEnvironment === "production";
    const developmentLocal = options.isDevelopment === true && !isProduction && isLocalHostname(parsed.hostname);
    const previewLoopback = options.buildEnvironment === "preview"
      && options.allowHttpLoopback === true
      && isLoopbackHostname(parsed.hostname);
    if (!developmentLocal && !previewLoopback) throw new ApiError("configuration");
  }
  return parsed.origin;
}

function validateSessionResponse(value) {
  if (!hasExactKeys(value, SESSION_KEYS)) return null;
  if (!nonEmptyString(value.session_id) || !nonEmptyString(value.case_id)) return null;
  if (!nonEmptyString(value.reference_no) || !nonEmptyString(value.session_token)) return null;
  if (value.ws_url !== `/ws/session/${value.session_id}` || value.ws_url.includes("?")) return null;
  if (!LANGUAGES.includes(value.lang) || !CONSENT.includes(value.consent)) return null;
  if (!nonEmptyString(value.ai_disclosure) || typeof value.human_request_available !== "boolean") return null;
  return value;
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch {
    throw new ApiError("malformed", response.status);
  }
}

async function createSession(baseUrl, request, transport = fetch) {
  if (!hasExactKeys(request, ["channel", "consent", "lang"])) throw new ApiError("request");
  if (request.channel !== "mobile_chat" || !CONSENT.includes(request.consent) || !LANGUAGES.includes(request.lang)) {
    throw new ApiError("request");
  }
  let response;
  try {
    response = await transport(`${baseUrl}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new ApiError("unavailable");
  }
  if (!response.ok) throw new ApiError(response.status === 401 ? "authentication" : "unavailable", response.status);
  const value = validateSessionResponse(await parseJson(response));
  if (value === null) throw new ApiError("malformed", response.status);
  return value;
}

async function getTimeline(baseUrl, session, validateTimeline, transport = fetch) {
  if (!nonEmptyString(session?.case_id) || !nonEmptyString(session?.session_token)) throw new ApiError("request");
  let response;
  try {
    response = await transport(`${baseUrl}/cases/${encodeURIComponent(session.case_id)}/timeline`, {
      method: "GET",
      headers: { Authorization: `Bearer ${session.session_token}` },
    });
  } catch {
    throw new ApiError("unavailable");
  }
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new ApiError("authentication", response.status);
    throw new ApiError("unavailable", response.status);
  }
  const value = validateTimeline(await parseJson(response));
  if (value === null) throw new ApiError("malformed", response.status);
  return value;
}

module.exports = { ApiError, createSession, getTimeline, validateApiBaseUrl, validateSessionResponse };
