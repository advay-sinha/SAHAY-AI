const test = require("node:test");
const assert = require("node:assert/strict");
const {
  ApiError,
  createSession,
  getTimeline,
  validateApiBaseUrl,
  validateSessionResponse,
} = require("../src/net/apiCore");
const { validateVictimTimeline } = require("../src/net/victimPayload");

const SESSION = Object.freeze({
  session_id: "session-fictional",
  case_id: "case-fictional",
  reference_no: "SAHAY-FICTIONAL",
  session_token: "test-only-token",
  ws_url: "/ws/session/session-fictional",
  lang: "hi",
  consent: "granted",
  ai_disclosure: "Fictional controlled test disclosure",
  human_request_available: true,
});

function response(status, value) {
  return { ok: status >= 200 && status < 300, status, json: async () => value };
}

test("API base URL accepts HTTPS and local-development HTTP only", () => {
  assert.equal(validateApiBaseUrl("https://demo.invalid", false), "https://demo.invalid");
  assert.equal(validateApiBaseUrl("http://192.168.1.9:8000", true), "http://192.168.1.9:8000");
  assert.throws(() => validateApiBaseUrl("http://demo.invalid", false), ApiError);
  assert.throws(() => validateApiBaseUrl("ftp://localhost", true), ApiError);
  assert.throws(() => validateApiBaseUrl("https://demo.invalid/path", false), ApiError);
});

test("session response validator rejects missing and extra keys", () => {
  assert.equal(validateSessionResponse(SESSION), SESSION);
  assert.equal(validateSessionResponse({ ...SESSION, display_name: "invented" }), null);
  const { session_token: _removed, ...missing } = SESSION;
  assert.equal(validateSessionResponse(missing), null);
  assert.equal(validateSessionResponse({ ...SESSION, ws_url: `${SESSION.ws_url}?token=bad` }), null);
});

test("session creation sends one exact unauthenticated request and validates the response", async () => {
  const calls = [];
  const transport = async (...args) => {
    calls.push(args);
    return response(201, SESSION);
  };
  assert.equal(await createSession("https://demo.invalid", {
    channel: "mobile_chat", consent: "granted", lang: "hi",
  }, transport), SESSION);
  assert.equal(calls.length, 1);
  assert.deepEqual(JSON.parse(calls[0][1].body), { channel: "mobile_chat", consent: "granted", lang: "hi" });
  assert.deepEqual(calls[0][1].headers, { "Content-Type": "application/json" });
  assert.equal("Authorization" in calls[0][1].headers, false);
});

test("session creation is not retried after transport or validation failure", async () => {
  let calls = 0;
  await assert.rejects(
    createSession("https://demo.invalid", { channel: "mobile_chat", consent: "granted", lang: "hi" }, async () => {
      calls += 1;
      throw new Error("private transport detail");
    }),
    (error) => error instanceof ApiError && error.kind === "unavailable",
  );
  assert.equal(calls, 1);
  await assert.rejects(
    createSession("https://demo.invalid", { channel: "mobile_chat", consent: "granted", lang: "hi" }, async () => response(201, { ...SESSION, extra: true })),
    (error) => error instanceof ApiError && error.kind === "malformed",
  );
});

test("timeline uses the active case and bearer header and preserves order and duplicates", async () => {
  const payload = {
    reference: SESSION.reference_no,
    timeline: [
      { stage: "request_received", label: "Received", ts: "2026-09-12T00:00:00Z" },
      { stage: "request_received", label: "Received", ts: "2026-09-12T00:00:00Z" },
    ],
  };
  const calls = [];
  const actual = await getTimeline("https://demo.invalid", SESSION, validateVictimTimeline, async (...args) => {
    calls.push(args);
    return response(200, payload);
  });
  assert.deepEqual(actual, payload);
  assert.equal(calls[0][0], "https://demo.invalid/cases/case-fictional/timeline");
  assert.deepEqual(calls[0][1].headers, { Authorization: "Bearer test-only-token" });
});

test("timeline authentication failure is explicit and invalid success is not empty state", async () => {
  await assert.rejects(
    getTimeline("https://demo.invalid", SESSION, validateVictimTimeline, async () => response(401, {})),
    (error) => error instanceof ApiError && error.kind === "authentication",
  );
  await assert.rejects(
    getTimeline("https://demo.invalid", SESSION, validateVictimTimeline, async () => response(200, { reference: SESSION.reference_no })),
    (error) => error instanceof ApiError && error.kind === "malformed",
  );
});
