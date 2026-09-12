/** POST /sessions request and PC-09 response validation. Node, no dependency. */

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  SESSION_RESPONSE_KEYS,
  buildCreateSessionRequest,
  createSession,
  validateCreateSessionResponse,
} = require("../src/net/restClient");
const {
  BASE_URL,
  TOKEN,
  captureConsole,
  jsonResponse,
  scriptedFetch,
  sessionResponse,
} = require("./fixtures/sessionFixtures");

const GRANTED_HI = { consent: "granted", lang: "hi" };

test("the request payload is exact for every consent and language", () => {
  for (const consent of ["granted", "declined"]) {
    for (const lang of ["hi", "en"]) {
      const request = buildCreateSessionRequest(consent, lang);
      assert.deepEqual(request, { channel: "mobile_chat", consent, lang });
      assert.deepEqual(Object.keys(request), ["channel", "consent", "lang"]);
    }
  }
  for (const [consent, lang] of [["pending", "hi"], ["granted", "ta"], [undefined, "en"], ["GRANTED", "hi"]]) {
    assert.equal(buildCreateSessionRequest(consent, lang), null);
  }
});

test("createSession posts the exact JSON body to /sessions with no credential", async () => {
  for (const consent of ["granted", "declined"]) {
    for (const lang of ["hi", "en"]) {
      const { calls, fetchImpl } = scriptedFetch([
        jsonResponse(201, sessionResponse({ consent, lang })),
      ]);
      const result = await createSession({ fetchImpl, baseUrl: BASE_URL, consent, lang });

      assert.equal(result.ok, true);
      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, `${BASE_URL}/sessions`);
      assert.equal(calls[0].init.method, "POST");
      assert.deepEqual(JSON.parse(calls[0].init.body), { channel: "mobile_chat", consent, lang });
      assert.equal(calls[0].init.body, JSON.stringify({ channel: "mobile_chat", consent, lang }));
      assert.equal(calls[0].init.headers["Content-Type"], "application/json");
      assert.equal("Authorization" in calls[0].init.headers, false);
    }
  }
});

test("a valid response keeps only the contract fields the app needs", () => {
  const session = validateCreateSessionResponse(sessionResponse(), GRANTED_HI);
  assert.deepEqual(session, {
    session_id: "fixture-session-0001",
    case_id: "fixture-case-0001",
    reference_no: "SAH-FIXTURE",
    session_token: TOKEN,
    ws_url: "/ws/session/fixture-session-0001",
    lang: "hi",
    consent: "granted",
  });
});

test("the validator knows exactly the nine PC-09 keys", () => {
  assert.deepEqual([...SESSION_RESPONSE_KEYS].sort(), [
    "ai_disclosure",
    "case_id",
    "consent",
    "human_request_available",
    "lang",
    "reference_no",
    "session_id",
    "session_token",
    "ws_url",
  ]);
});

test("every missing key is rejected", () => {
  for (const key of SESSION_RESPONSE_KEYS) {
    const value = sessionResponse();
    delete value[key];
    assert.equal(validateCreateSessionResponse(value, GRANTED_HI), null, key);
  }
});

test("additional keys, including assessment or state fields, are rejected", () => {
  for (const extra of ["state", "token", "svi", "band", "priority", "needs_human", "unexpected"]) {
    assert.equal(
      validateCreateSessionResponse({ ...sessionResponse(), [extra]: "x" }, GRANTED_HI),
      null,
      extra,
    );
  }
  const withProto = JSON.parse(`{${JSON.stringify(sessionResponse()).slice(1, -1)},"__proto__":{}}`);
  assert.equal(validateCreateSessionResponse(withProto, GRANTED_HI), null);
});

test("wrong types, bad enums, empty identifiers and malformed URLs are rejected", () => {
  const cases = {
    session_id: ["", " ", 1, null, "a/b", "../x", "id with space", ".hidden"],
    case_id: ["", 7, null, "case/other", "..", "case?x=1"],
    reference_no: ["", "   ", " SAH-1", 5, null],
    session_token: ["", "has space", 12, null, "line\nbreak"],
    ws_url: [
      "",
      "/ws/session/other-session",
      "/ws/session/fixture-session-0001?token=abc",
      "ws://host/ws/session/fixture-session-0001",
      "/ws/session/fixture-session-0001/",
      null,
    ],
    lang: ["ta", "", null, "HI", "en"],
    consent: ["pending", "declined", "", null, "GRANTED"],
    ai_disclosure: ["", "   ", 3, null],
    human_request_available: ["true", 1, null],
  };
  for (const [key, values] of Object.entries(cases)) {
    for (const bad of values) {
      assert.equal(
        validateCreateSessionResponse(sessionResponse({ [key]: bad }), GRANTED_HI),
        null,
        `${key}=${JSON.stringify(bad)}`,
      );
    }
  }
  for (const value of [null, [], "text", 1, [sessionResponse()]]) {
    assert.equal(validateCreateSessionResponse(value, GRANTED_HI), null);
  }
});

test("lang and consent must echo the request", () => {
  assert.equal(
    validateCreateSessionResponse(sessionResponse({ lang: "en" }), GRANTED_HI),
    null,
  );
  assert.equal(
    validateCreateSessionResponse(sessionResponse({ consent: "declined" }), GRANTED_HI),
    null,
  );
  assert.notEqual(
    validateCreateSessionResponse(sessionResponse({ consent: "declined", lang: "en" }), {
      consent: "declined",
      lang: "en",
    }),
    null,
  );
});

test("failures never fabricate a session and never retry", async () => {
  const replies = [
    [new TypeError("Network request failed"), "network"],
    [jsonResponse(500, { detail: "internal" }), "http"],
    [jsonResponse(400, { detail: "unknown channel" }), "http"],
    [jsonResponse(401, {}), "http"],
    [jsonResponse(201, "not json"), "malformed"],
    [jsonResponse(201, sessionResponse({ extra: true })), "malformed"],
    [jsonResponse(201, {}), "malformed"],
    [jsonResponse(200, sessionResponse()), "malformed"],
    [{}, "network"],
  ];
  for (const [reply, reason] of replies) {
    const { calls, fetchImpl } = scriptedFetch([reply]);
    const result = await createSession({ fetchImpl, baseUrl: BASE_URL, ...GRANTED_HI });
    assert.deepEqual(result, { ok: false, reason });
    assert.equal(calls.length, 1, "POST /sessions was retried automatically");
  }
});

test("a hung request times out as a failure, not a session", async () => {
  const { calls, fetchImpl } = scriptedFetch(["hang"]);
  const result = await createSession({ fetchImpl, baseUrl: BASE_URL, ...GRANTED_HI, timeoutMs: 20 });
  assert.deepEqual(result, { ok: false, reason: "timeout" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].init.signal.aborted, true);
});

test("an invalid decision sends nothing", async () => {
  const { calls, fetchImpl } = scriptedFetch([]);
  const result = await createSession({ fetchImpl, baseUrl: BASE_URL, consent: "pending", lang: "hi" });
  assert.deepEqual(result, { ok: false, reason: "invalid" });
  assert.equal(calls.length, 0);
});

test("the token is never logged and never appears in a failure", async () => {
  const consoleCapture = captureConsole();
  try {
    const ok = scriptedFetch([jsonResponse(201, sessionResponse())]);
    await createSession({ fetchImpl: ok.fetchImpl, baseUrl: BASE_URL, ...GRANTED_HI });

    const bad = scriptedFetch([jsonResponse(201, sessionResponse({ unexpected: TOKEN }))]);
    const failure = await createSession({ fetchImpl: bad.fetchImpl, baseUrl: BASE_URL, ...GRANTED_HI });
    assert.doesNotMatch(JSON.stringify(failure), /NEVER-LOG/);
  } finally {
    consoleCapture.restore();
  }
  assert.deepEqual(consoleCapture.lines, []);
});
