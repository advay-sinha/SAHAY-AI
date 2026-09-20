/**
 * REST calls the victim app is allowed to make: POST /sessions and
 * GET /cases/{case_id}/timeline (CONTRACTS.md section 4). Nothing else.
 *
 * Every result is a small tagged object. No result ever carries a response
 * body from a failed call, the session token, or exception text, so nothing
 * sensitive can reach the screen or a log. This module never logs.
 *
 * No automatic retry: POST /sessions has no approved idempotency key.
 */

const { validateVictimTimeline } = require("./victimPayload");

const DEFAULT_TIMEOUT_MS = 15000;
const REQUEST_CONSENTS = Object.freeze(["granted", "declined"]);
const REQUEST_LANGS = Object.freeze(["hi", "en"]);
const RESPONSE_CONSENTS = Object.freeze(["granted", "declined", "pending"]);

/** PC-09, frozen. Exactly these keys; anything else is rejected. */
const SESSION_RESPONSE_KEYS = Object.freeze([
  "session_id",
  "case_id",
  "reference_no",
  "session_token",
  "ws_url",
  "lang",
  "consent",
  "ai_disclosure",
  "human_request_available",
]);

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/;
const TOKEN = /^[\x21-\x7E]{1,4096}$/;

function isPlainRecord(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return Object.getPrototypeOf(value) === Object.prototype;
}

function hasExactKeys(value, expected) {
  if (!isPlainRecord(value)) return false;
  const actual = Reflect.ownKeys(value);
  return actual.length === expected.length
    && actual.every((key) => typeof key === "string" && expected.includes(key));
}

function isIdentifier(value) {
  return typeof value === "string" && IDENTIFIER.test(value);
}

function isNonBlank(value) {
  return typeof value === "string" && value.trim().length > 0 && value.trim() === value;
}

function buildCreateSessionRequest(consent, lang) {
  if (!REQUEST_CONSENTS.includes(consent) || !REQUEST_LANGS.includes(lang)) return null;
  return { channel: "mobile_chat", consent, lang };
}

/**
 * Validates the complete PC-09 response and returns only the fields the app
 * keeps. `lang` and `consent` must echo the request exactly; `ws_url` must be
 * the tokenless path for this session and nothing else.
 */
function validateCreateSessionResponse(value, requested) {
  try {
    if (!hasExactKeys(value, SESSION_RESPONSE_KEYS)) return null;
    if (!isIdentifier(value.session_id) || !isIdentifier(value.case_id)) return null;
    if (!isNonBlank(value.reference_no)) return null;
    if (typeof value.session_token !== "string" || !TOKEN.test(value.session_token)) return null;
    if (value.ws_url !== `/ws/session/${value.session_id}`) return null;
    if (!REQUEST_LANGS.includes(value.lang) || value.lang !== requested.lang) return null;
    if (!RESPONSE_CONSENTS.includes(value.consent) || value.consent !== requested.consent) return null;
    if (typeof value.ai_disclosure !== "string" || value.ai_disclosure.trim().length === 0) return null;
    if (typeof value.human_request_available !== "boolean") return null;

    return {
      session_id: value.session_id,
      case_id: value.case_id,
      reference_no: value.reference_no,
      session_token: value.session_token,
      ws_url: value.ws_url,
      lang: value.lang,
      consent: value.consent,
    };
  } catch {
    return null;
  }
}

/** The victim-safe timeline, exact keys (victimPayload.js), non-blank reference. */
function validateTimelineResponse(value) {
  const timeline = validateVictimTimeline(value);
  if (timeline === null || !isNonBlank(timeline.reference)) return null;
  return timeline;
}

/**
 * One request with a hard timeout. The result settles exactly once, as the
 * first of: the response, the timeout, or the caller's cancellation. Timeout
 * and cancellation both abort the one underlying fetch, and both settle the
 * result before aborting, so the fetch's late response or rejection is
 * consumed here and can never change what the caller sees. The timer and
 * the caller's abort listener are removed on every path. Outcomes carry no
 * URL, header, token or body. Bodies are read only for 2xx responses.
 */
function requestJson({ fetchImpl, url, method, headers, body, timeoutMs, signal }) {
  if (signal && signal.aborted) return Promise.resolve({ kind: "aborted" });

  const controller = new AbortController();

  async function perform() {
    const init = { method, headers, signal: controller.signal };
    if (body !== undefined) init.body = body;

    let response;
    try {
      response = await fetchImpl(url, init);
    } catch {
      return { kind: "network" };
    }
    if (controller.signal.aborted) return { kind: "aborted" };
    if (!response || typeof response.status !== "number") return { kind: "network" };
    if (response.status < 200 || response.status > 299) {
      return { kind: "status", status: response.status };
    }

    try {
      return { kind: "ok", status: response.status, body: JSON.parse(await response.text()) };
    } catch {
      return { kind: "malformed" };
    }
  }

  return new Promise((resolve) => {
    let settled = false;
    let timer = null;

    function finish(outcome) {
      if (settled) return;
      settled = true;
      if (timer !== null) clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", onCallerAbort);
      resolve(outcome);
    }

    function onCallerAbort() {
      finish({ kind: "aborted" });
      controller.abort();
    }

    timer = setTimeout(() => {
      finish({ kind: "timeout" });
      controller.abort();
    }, timeoutMs);
    if (signal) signal.addEventListener("abort", onCallerAbort);

    perform().then(finish, () => finish({ kind: "network" }));
  });
}

async function createSession({ fetchImpl, baseUrl, consent, lang, timeoutMs = DEFAULT_TIMEOUT_MS }) {
  const request = buildCreateSessionRequest(consent, lang);
  if (request === null) return { ok: false, reason: "invalid" };

  const outcome = await requestJson({
    fetchImpl,
    url: `${baseUrl}/sessions`,
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(request),
    timeoutMs,
  });

  if (outcome.kind === "network" || outcome.kind === "timeout" || outcome.kind === "aborted") {
    return { ok: false, reason: outcome.kind };
  }
  if (outcome.kind === "status") return { ok: false, reason: "http" };
  if (outcome.kind !== "ok" || outcome.status !== 201) return { ok: false, reason: "malformed" };

  const session = validateCreateSessionResponse(outcome.body, request);
  if (session === null) return { ok: false, reason: "malformed" };
  return { ok: true, session };
}

/**
 * GET /cases/{case_id}/timeline with the victim's bearer token. The token
 * goes only in the Authorization header, never in the URL.
 */
async function fetchTimeline({
  fetchImpl,
  baseUrl,
  caseId,
  sessionToken,
  signal,
  timeoutMs = DEFAULT_TIMEOUT_MS,
}) {
  if (!isIdentifier(caseId) || typeof sessionToken !== "string" || !TOKEN.test(sessionToken)) {
    return { kind: "failed", reason: "invalid" };
  }

  const outcome = await requestJson({
    fetchImpl,
    url: `${baseUrl}/cases/${encodeURIComponent(caseId)}/timeline`,
    method: "GET",
    headers: { Accept: "application/json", Authorization: `Bearer ${sessionToken}` },
    signal,
    timeoutMs,
  });

  switch (outcome.kind) {
    case "aborted":
      return { kind: "aborted" };
    case "network":
    case "timeout":
      return { kind: "failed", reason: outcome.kind };
    case "status":
      if (outcome.status === 401) return { kind: "unauthenticated" };
      if (outcome.status === 403) return { kind: "forbidden" };
      if (outcome.status === 404) return { kind: "not_found" };
      return { kind: "failed", reason: "http" };
    case "ok": {
      if (outcome.status !== 200) return { kind: "failed", reason: "malformed" };
      const timeline = validateTimelineResponse(outcome.body);
      if (timeline === null) return { kind: "failed", reason: "malformed" };
      return { kind: "ready", timeline };
    }
    default:
      return { kind: "failed", reason: "malformed" };
  }
}

module.exports = {
  DEFAULT_TIMEOUT_MS,
  SESSION_RESPONSE_KEYS,
  buildCreateSessionRequest,
  createSession,
  fetchTimeline,
  validateCreateSessionResponse,
  validateTimelineResponse,
};
