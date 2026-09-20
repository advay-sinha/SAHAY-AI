/**
 * Memory-only session store and the one-case timeline. Node, no dependency.
 *
 * All HTTP here is mocked with clearly fictional fixtures.
 */

const assert = require("node:assert/strict");
const test = require("node:test");

const { createSessionStore, timelineLoadState } = require("../src/session/sessionStore");
const { selectMyRequestsPresentation } = require("../src/screens/myRequestsState");
const {
  BASE_URL,
  TOKEN,
  captureConsole,
  deferred,
  jsonResponse,
  scriptedFetch,
  sessionResponse,
  timelineResponse,
} = require("./fixtures/sessionFixtures");

const TIMELINE_URL = `${BASE_URL}/cases/fixture-case-0001/timeline`;

function storeWith(replies, options = {}) {
  const fake = scriptedFetch(replies);
  const store = createSessionStore({ apiUrl: BASE_URL, fetchImpl: fake.fetchImpl, ...options });
  return { ...fake, store };
}

async function activeStore(timelineReplies, options) {
  const fixture = storeWith([jsonResponse(201, sessionResponse()), ...timelineReplies], options);
  const result = await fixture.store.startSession("granted", "hi");
  assert.equal(result.ok, true);
  return fixture;
}

function presentationOf(store) {
  const { timeline } = store.getSnapshot();
  const loadState = timelineLoadState(timeline);
  return selectMyRequestsPresentation(loadState, loadState === "ready" ? timeline.payload : undefined);
}

test("a missing or malformed API URL fails locally without any request", async () => {
  for (const apiUrl of [undefined, "", "not a url", "http://x.test?token=1"]) {
    const fake = scriptedFetch([]);
    const store = createSessionStore({ apiUrl, fetchImpl: fake.fetchImpl });
    assert.equal(store.getSnapshot().configured, false);
    assert.deepEqual(await store.startSession("granted", "en"), { ok: false, reason: "config" });
    assert.equal(fake.calls.length, 0);
    assert.equal(store.getSnapshot().session, null);
    assert.equal(store.getSnapshot().creation.status, "failed");
  }
});

test("a created session is held in memory and never exposes the token", async () => {
  const { store } = await activeStore([]);
  const snapshot = store.getSnapshot();

  assert.deepEqual(snapshot.session, {
    session_id: "fixture-session-0001",
    case_id: "fixture-case-0001",
    reference_no: "SAH-FIXTURE",
    ws_url: "/ws/session/fixture-session-0001",
    lang: "hi",
    consent: "granted",
  });
  assert.equal(Object.isFrozen(snapshot.session), true);
  assert.doesNotMatch(JSON.stringify(snapshot), /NEVER-LOG|session_token/);
  assert.doesNotMatch(JSON.stringify(store), /NEVER-LOG/);
});

test("a duplicate tap while the request is in flight sends one request", async () => {
  const gate = deferred();
  const { calls, store } = storeWith([() => gate.promise]);

  const first = store.startSession("granted", "hi");
  const second = await store.startSession("granted", "hi");
  const third = await store.startSession("declined", "hi");
  assert.deepEqual(second, { ok: false, reason: "in_flight" });
  assert.deepEqual(third, { ok: false, reason: "in_flight" });
  assert.deepEqual(await store.retrySessionCreation(), { ok: false, reason: "in_flight" });

  gate.resolve(jsonResponse(201, sessionResponse()));
  assert.equal((await first).ok, true);
  assert.equal(calls.length, 1);
});

test("only one session may exist at a time", async () => {
  const { calls, store } = await activeStore([]);
  assert.deepEqual(await store.startSession("granted", "hi"), { ok: false, reason: "active" });
  assert.deepEqual(await store.startSession("declined", "en"), { ok: false, reason: "active" });
  assert.equal(calls.length, 1);
});

test("failure never fabricates success, and retry is explicit and reuses the decision", async () => {
  const { calls, store } = storeWith([
    new TypeError("Network request failed"),
    jsonResponse(201, sessionResponse({ lang: "en", consent: "declined" })),
  ]);

  const failed = await store.startSession("declined", "en");
  assert.deepEqual(failed, { ok: false, reason: "network" });
  assert.equal(store.getSnapshot().session, null);
  assert.equal(store.getSnapshot().creation.status, "failed");
  assert.equal(calls.length, 1, "creation was retried automatically");

  // A second decision is refused; only the explicit retry may send again.
  assert.deepEqual(await store.startSession("granted", "hi"), { ok: false, reason: "decided" });
  assert.equal(calls.length, 1);

  const retried = await store.retrySessionCreation();
  assert.equal(retried.ok, true);
  assert.equal(calls.length, 2);
  assert.deepEqual(JSON.parse(calls[1].init.body), { channel: "mobile_chat", consent: "declined", lang: "en" });
  assert.equal(store.getSnapshot().creation.attempt, 2);
});

test("a malformed success response leaves no session", async () => {
  const { store } = storeWith([jsonResponse(201, sessionResponse({ ws_url: "/ws/session/x?token=t" }))]);
  assert.deepEqual(await store.startSession("granted", "hi"), { ok: false, reason: "malformed" });
  assert.equal(store.getSnapshot().session, null);
});

test("the timeline uses the session case_id and the bearer header only", async () => {
  const { calls, store } = await activeStore([jsonResponse(200, timelineResponse())]);

  await store.loadTimeline("someone-elses-case");
  assert.equal(calls.length, 2);
  assert.equal(calls[1].url, TIMELINE_URL);
  assert.equal(calls[1].init.method, "GET");
  assert.equal(calls[1].init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(calls[1].init.body, undefined);
  assert.doesNotMatch(calls[1].url, /NEVER-LOG|token|someone/);
  assert.doesNotMatch(calls[0].url, /NEVER-LOG|token/);
});

test("a valid empty timeline is the only way to reach timeline.empty", async () => {
  const { store } = await activeStore([jsonResponse(200, timelineResponse())]);
  await store.loadTimeline();
  assert.equal(store.getSnapshot().timeline.status, "ready");
  assert.deepEqual(presentationOf(store), { kind: "empty" });
});

test("server order and duplicate entries are preserved; timestamps are never presented", async () => {
  const entries = [
    { stage: "under_review", label: "Second server label", ts: "2026-09-12T11:00:00Z" },
    { stage: "request_received", label: "First server label", ts: "2026-09-12T10:00:00Z" },
    { stage: "request_received", label: "First server label", ts: "2026-09-12T10:00:00Z" },
  ];
  const { store } = await activeStore([jsonResponse(200, timelineResponse(entries))]);
  await store.loadTimeline();

  const presentation = presentationOf(store);
  assert.deepEqual(presentation, {
    kind: "timeline",
    reference: "SAH-FIXTURE",
    entries: [
      { stage: "under_review", label: "Second server label" },
      { stage: "request_received", label: "First server label" },
      { stage: "request_received", label: "First server label" },
    ],
  });
  assert.doesNotMatch(JSON.stringify(presentation), /2026-09-12|"ts"/);
});

test("additional, internal or assessment fields fail the whole timeline", async () => {
  const entry = { stage: "request_received", label: "Server label", ts: "t" };
  const bodies = [
    { ...timelineResponse([entry]), svi: 71 },
    { ...timelineResponse([entry]), case_id: "fixture-case-0001" },
    timelineResponse([{ ...entry, band: "High" }]),
    timelineResponse([{ ...entry, confidence: 0.9 }]),
    timelineResponse([{ ...entry, priority: "Critical" }]),
    timelineResponse([{ ...entry, officer_id: "exec-1" }]),
    timelineResponse([{ stage: "request_received", label: "Server label" }]),
    timelineResponse([{ ...entry, stage: "escalated" }]),
    { reference: "", timeline: [] },
    { reference: "SAH-FIXTURE" },
    [timelineResponse([entry])],
    [timelineResponse([entry]), timelineResponse([entry])],
    "not json",
  ];
  for (const body of bodies) {
    const { store } = await activeStore([jsonResponse(200, body)]);
    await store.loadTimeline();
    assert.equal(store.getSnapshot().timeline.status, "failed", JSON.stringify(body));
    assert.equal(store.getSnapshot().timeline.payload, null);
    assert.deepEqual(presentationOf(store), { kind: "failed" });
  }
});

test("401 clears the entire in-memory session", async () => {
  const { calls, store } = await activeStore([jsonResponse(401, { detail: "Not authenticated" })]);
  await store.loadTimeline();

  const snapshot = store.getSnapshot();
  assert.equal(snapshot.session, null);
  assert.equal(snapshot.creation.status, "idle");
  assert.deepEqual(presentationOf(store), { kind: "unavailable" });

  // The credential is gone: no further authenticated request is possible.
  await store.loadTimeline();
  assert.equal(calls.length, 2);
});

test("403 clears case data, shows unavailable and never retries with another case", async () => {
  const { calls, store } = await activeStore([
    jsonResponse(200, timelineResponse([{ stage: "request_received", label: "Server label", ts: "t" }])),
    jsonResponse(403, { detail: "Not permitted for this role" }),
  ]);
  await store.loadTimeline();
  assert.equal(store.getSnapshot().timeline.status, "ready");

  await store.loadTimeline();
  assert.equal(store.getSnapshot().timeline.status, "unavailable");
  assert.equal(store.getSnapshot().timeline.payload, null);

  await store.loadTimeline();
  await store.loadTimeline("fixture-case-0002");
  assert.equal(calls.length, 3, "a 403 was followed by another timeline request");
  assert.ok(calls.slice(1).every((call) => call.url === TIMELINE_URL));
});

test("404 shows unavailable and never an empty timeline", async () => {
  const { store } = await activeStore([jsonResponse(404, { detail: "case not found" })]);
  await store.loadTimeline();
  assert.deepEqual(presentationOf(store), { kind: "unavailable" });
  assert.equal(store.getSnapshot().session !== null, true);
});

test("network, timeout, other non-2xx and malformed 2xx fail with explicit retry", async () => {
  const replies = [
    new TypeError("Network request failed"),
    "hang",
    jsonResponse(500, { detail: "boom" }),
    jsonResponse(502, "<html>gateway</html>"),
    jsonResponse(429, {}),
    jsonResponse(200, "{"),
    jsonResponse(204, ""),
  ];
  for (const reply of replies) {
    const { calls, store } = await activeStore(
      [reply, jsonResponse(200, timelineResponse())],
      { timeoutMs: 20 },
    );
    await store.loadTimeline();
    assert.equal(store.getSnapshot().timeline.status, "failed");
    assert.deepEqual(presentationOf(store), { kind: "failed" });
    assert.equal(calls.length, 2, "the timeline request was retried automatically");

    await store.loadTimeline();
    assert.deepEqual(presentationOf(store), { kind: "empty" });
    assert.equal(calls.length, 3);
  }
});

test("a stale timeline response cannot overwrite a newer request", async () => {
  const slow = deferred();
  const { store } = await activeStore([
    () => slow.promise,
    jsonResponse(200, timelineResponse([{ stage: "under_review", label: "Newer", ts: "t" }])),
  ]);

  const first = store.loadTimeline();
  await store.loadTimeline();
  slow.resolve(jsonResponse(200, timelineResponse([{ stage: "closed", label: "Older", ts: "t" }])));
  await first;

  assert.deepEqual(presentationOf(store).entries, [{ stage: "under_review", label: "Newer" }]);
});

test("a superseded request settling cannot disturb the newer request in flight", async () => {
  const newer = deferred();
  const { calls, store } = await activeStore([
    "hang",
    () => newer.promise,
  ]);

  const first = store.loadTimeline();
  const second = store.loadTimeline();
  await first;
  assert.equal(calls[1].init.signal.aborted, true);
  assert.equal(calls[2].init.signal.aborted, false);
  assert.equal(store.getSnapshot().timeline.status, "loading");

  store.cancelTimeline();
  assert.equal(calls[2].init.signal.aborted, true, "the newer request lost its cancellation handle");
  newer.resolve(jsonResponse(200, timelineResponse()));
  await second;
  assert.equal(store.getSnapshot().timeline.status, "idle");
});

test("a stale timeline response cannot overwrite a newer session", async () => {
  const slow = deferred();
  const { store } = await activeStore([
    () => slow.promise,
    jsonResponse(201, sessionResponse({
      session_id: "fixture-session-0002",
      case_id: "fixture-case-0002",
      ws_url: "/ws/session/fixture-session-0002",
    })),
  ]);

  const pending = store.loadTimeline();
  store.clearSession();
  assert.equal((await store.startSession("granted", "hi")).ok, true);
  slow.resolve(jsonResponse(200, timelineResponse([{ stage: "closed", label: "Old case", ts: "t" }])));
  await pending;

  assert.equal(store.getSnapshot().session.case_id, "fixture-case-0002");
  assert.equal(store.getSnapshot().timeline.status, "idle");
  assert.equal(store.getSnapshot().timeline.payload, null);
});

test("a stale 401 cannot clear a newer session", async () => {
  const slow = deferred();
  const { store } = await activeStore([
    () => slow.promise,
    jsonResponse(201, sessionResponse({
      session_id: "fixture-session-0002",
      case_id: "fixture-case-0002",
      ws_url: "/ws/session/fixture-session-0002",
    })),
  ]);

  const pending = store.loadTimeline();
  store.clearSession();
  await store.startSession("granted", "hi");
  slow.resolve(jsonResponse(401, {}));
  await pending;

  assert.equal(store.getSnapshot().session?.session_id, "fixture-session-0002");
});

test("a creation result that arrives after clearSession is discarded", async () => {
  const slow = deferred();
  const { store } = storeWith([() => slow.promise]);
  const pending = store.startSession("granted", "hi");
  store.clearSession();
  slow.resolve(jsonResponse(201, sessionResponse()));
  assert.deepEqual(await pending, { ok: false, reason: "stale" });
  assert.equal(store.getSnapshot().session, null);
});

test("cancelling an unmounted timeline aborts the request and keeps no result", async () => {
  const slow = deferred();
  const { calls, store } = await activeStore([() => slow.promise]);
  const pending = store.loadTimeline();
  store.cancelTimeline();
  assert.equal(calls[1].init.signal.aborted, true);
  slow.resolve(jsonResponse(200, timelineResponse()));
  await pending;
  assert.equal(store.getSnapshot().timeline.status, "idle");
});

test("no session means unavailable, with no request", async () => {
  const { calls, store } = storeWith([]);
  await store.loadTimeline();
  assert.deepEqual(presentationOf(store), { kind: "unavailable" });
  assert.equal(calls.length, 0);
});

test("subscribers are notified and snapshots are immutable", async () => {
  const { store } = storeWith([jsonResponse(201, sessionResponse())]);
  let notified = 0;
  const unsubscribe = store.subscribe(() => { notified += 1; });
  const before = store.getSnapshot();
  await store.startSession("granted", "hi");
  unsubscribe();
  assert.ok(notified >= 2);
  assert.notEqual(store.getSnapshot(), before);
  assert.equal(Object.isFrozen(store.getSnapshot()), true);
  assert.equal(Object.isFrozen(store.getSnapshot().creation), true);
});

test("no flow logs anything, and the token never reaches a result or snapshot", async () => {
  const consoleCapture = captureConsole();
  const seen = [];
  try {
    const { store } = await activeStore([
      jsonResponse(500, {}),
      jsonResponse(200, { ...timelineResponse(), leaked: TOKEN }),
      jsonResponse(401, {}),
    ]);
    seen.push(store.getSnapshot());
    for (let index = 0; index < 3; index += 1) {
      await store.loadTimeline();
      seen.push(store.getSnapshot());
    }
    seen.push(await store.retrySessionCreation());
  } finally {
    consoleCapture.restore();
  }
  assert.deepEqual(consoleCapture.lines, []);
  assert.doesNotMatch(JSON.stringify(seen), /NEVER-LOG/);
});
