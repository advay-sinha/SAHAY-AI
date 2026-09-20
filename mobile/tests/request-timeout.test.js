/**
 * Timeout and cancellation of the REST helper. Node, no dependency.
 *
 * All HTTP here is mocked with clearly fictional fixtures.
 */

const assert = require("node:assert/strict");
const test = require("node:test");

const { createSession, fetchTimeline } = require("../src/net/restClient");
const { createSessionStore } = require("../src/session/sessionStore");
const {
  BASE_URL,
  TOKEN,
  deferred,
  jsonResponse,
  scriptedFetch,
  sessionResponse,
  timelineResponse,
} = require("./fixtures/sessionFixtures");

const TIMEOUT_MS = 20;
const ENTRY = { stage: "under_review", label: "Late server label", ts: "t" };

/** Lets pending microtasks, timers and unhandled-rejection detection run. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 30));

/** Fails the test if any promise rejection goes unhandled while it runs. */
async function withoutUnhandledRejections(body) {
  const seen = [];
  const onUnhandled = (reason) => seen.push(reason);
  process.on("unhandledRejection", onUnhandled);
  try {
    await body();
    await settle();
  } finally {
    process.off("unhandledRejection", onUnhandled);
  }
  assert.deepEqual(seen, [], "a late rejection escaped as an unhandled promise");
}

/** Counts AbortController.abort() calls while `body` runs. */
async function countAborts(body) {
  const original = AbortController.prototype.abort;
  let aborts = 0;
  AbortController.prototype.abort = function abort(...args) {
    aborts += 1;
    return original.apply(this, args);
  };
  try {
    await body();
  } finally {
    AbortController.prototype.abort = original;
  }
  return aborts;
}

/** Records the helper's timers (identified by their delay) and which were cleared. */
async function trackTimers(delay, body) {
  const originalSet = globalThis.setTimeout;
  const originalClear = globalThis.clearTimeout;
  const created = new Set();
  const cleared = new Set();
  const fired = new Set();
  globalThis.setTimeout = (callback, ms, ...args) => {
    if (ms !== delay) return originalSet(callback, ms, ...args);
    const handle = originalSet(() => {
      fired.add(handle);
      callback(...args);
    }, ms);
    created.add(handle);
    return handle;
  };
  globalThis.clearTimeout = (handle) => {
    if (created.has(handle)) cleared.add(handle);
    return originalClear(handle);
  };
  try {
    await body();
  } finally {
    globalThis.setTimeout = originalSet;
    globalThis.clearTimeout = originalClear;
  }
  return { created, cleared, fired };
}

async function activeStore(replies) {
  const fake = scriptedFetch([jsonResponse(201, sessionResponse()), ...replies]);
  const store = createSessionStore({ apiUrl: BASE_URL, fetchImpl: fake.fetchImpl, timeoutMs: TIMEOUT_MS });
  assert.equal((await store.startSession("granted", "hi")).ok, true);
  return { ...fake, store };
}

test("a timeout settles as a timeout failure and aborts the underlying fetch", async () => {
  let result;
  let signal;
  const aborts = await countAborts(async () => {
    const { calls, fetchImpl } = scriptedFetch(["hang"]);
    result = await fetchTimeline({
      fetchImpl,
      baseUrl: BASE_URL,
      caseId: "fixture-case-0001",
      sessionToken: TOKEN,
      timeoutMs: TIMEOUT_MS,
    });
    signal = calls[0].init.signal;
  });

  assert.deepEqual(result, { kind: "failed", reason: "timeout" });
  assert.equal(aborts, 1);
  assert.equal(signal.aborted, true);
});

test("timeout failures carry no token, URL or response body", async () => {
  const session = await createSession({
    fetchImpl: scriptedFetch(["hang"]).fetchImpl,
    baseUrl: BASE_URL,
    consent: "granted",
    lang: "hi",
    timeoutMs: TIMEOUT_MS,
  });
  const timeline = await fetchTimeline({
    fetchImpl: scriptedFetch(["hang"]).fetchImpl,
    baseUrl: BASE_URL,
    caseId: "fixture-case-0001",
    sessionToken: TOKEN,
    timeoutMs: TIMEOUT_MS,
  });

  assert.deepEqual(session, { ok: false, reason: "timeout" });
  assert.deepEqual(timeline, { kind: "failed", reason: "timeout" });
  assert.doesNotMatch(JSON.stringify([session, timeline]), /NEVER-LOG|Bearer|http|fixture|body|detail/);
});

test("a response arriving after the timeout cannot update timeline state", async () => {
  const late = deferred();
  const { store } = await activeStore([() => late.promise]);

  await store.loadTimeline();
  assert.equal(store.getSnapshot().timeline.status, "failed");

  late.resolve(jsonResponse(200, timelineResponse([ENTRY])));
  await settle();
  assert.equal(store.getSnapshot().timeline.status, "failed");
  assert.equal(store.getSnapshot().timeline.payload, null);
});

test("a session response arriving after the timeout cannot create a session", async () => {
  const late = deferred();
  const fake = scriptedFetch([() => late.promise]);
  const store = createSessionStore({ apiUrl: BASE_URL, fetchImpl: fake.fetchImpl, timeoutMs: TIMEOUT_MS });

  assert.deepEqual(await store.startSession("granted", "hi"), { ok: false, reason: "timeout" });
  late.resolve(jsonResponse(201, sessionResponse()));
  await settle();

  assert.equal(store.getSnapshot().session, null);
  assert.equal(store.getSnapshot().creation.status, "failed");
  assert.equal(fake.calls.length, 1);
});

test("a rejection arriving after the timeout is consumed safely", async () => {
  await withoutUnhandledRejections(async () => {
    const late = deferred();
    const { store } = await activeStore([() => late.promise.then(() => {
      throw Object.assign(new Error("AbortError"), { name: "AbortError" });
    })]);

    await store.loadTimeline();
    assert.equal(store.getSnapshot().timeline.status, "failed");
    late.resolve();
    await settle();
    assert.equal(store.getSnapshot().timeline.status, "failed");
  });

  await withoutUnhandledRejections(async () => {
    const late = deferred();
    const result = createSession({
      fetchImpl: () => late.promise.then(() => Promise.reject(new TypeError("Network request failed"))),
      baseUrl: BASE_URL,
      consent: "granted",
      lang: "hi",
      timeoutMs: TIMEOUT_MS,
    });
    assert.deepEqual(await result, { ok: false, reason: "timeout" });
    late.resolve();
  });
});

test("a late body-read rejection after the timeout is consumed safely", async () => {
  await withoutUnhandledRejections(async () => {
    const body = deferred();
    const response = { status: 200, text: () => body.promise.then(() => Promise.reject(new Error("aborted"))) };
    const { store } = await activeStore([response]);

    await store.loadTimeline();
    assert.equal(store.getSnapshot().timeline.status, "failed");
    body.resolve();
    await settle();
    assert.equal(store.getSnapshot().timeline.status, "failed");
  });
});

test("the timeout timer is cleared after a normal success", async () => {
  const delay = 4321;
  const timers = await trackTimers(delay, async () => {
    const created = await createSession({
      fetchImpl: scriptedFetch([jsonResponse(201, sessionResponse())]).fetchImpl,
      baseUrl: BASE_URL,
      consent: "granted",
      lang: "hi",
      timeoutMs: delay,
    });
    assert.equal(created.ok, true);

    const timeline = await fetchTimeline({
      fetchImpl: scriptedFetch([jsonResponse(200, timelineResponse())]).fetchImpl,
      baseUrl: BASE_URL,
      caseId: "fixture-case-0001",
      sessionToken: TOKEN,
      timeoutMs: delay,
    });
    assert.equal(timeline.kind, "ready");
  });

  assert.equal(timers.created.size, 2);
  assert.deepEqual([...timers.created].filter((handle) => !timers.cleared.has(handle)), []);
  assert.equal(timers.fired.size, 0);
});

test("the timeout timer is cleared after failure and after caller cancellation", async () => {
  const delay = 4322;
  const timers = await trackTimers(delay, async () => {
    await createSession({
      fetchImpl: scriptedFetch([new TypeError("Network request failed")]).fetchImpl,
      baseUrl: BASE_URL,
      consent: "granted",
      lang: "hi",
      timeoutMs: delay,
    });
    const caller = new AbortController();
    const pending = fetchTimeline({
      fetchImpl: scriptedFetch(["hang"]).fetchImpl,
      baseUrl: BASE_URL,
      caseId: "fixture-case-0001",
      sessionToken: TOKEN,
      signal: caller.signal,
      timeoutMs: delay,
    });
    caller.abort();
    assert.deepEqual(await pending, { kind: "aborted" });
  });

  assert.equal(timers.created.size, 2);
  assert.deepEqual([...timers.created].filter((handle) => !timers.cleared.has(handle)), []);
});

test("an already-cancelled caller starts no timer and no request", async () => {
  const delay = 4323;
  const cancelled = new AbortController();
  cancelled.abort();
  const none = scriptedFetch([]);
  const timers = await trackTimers(delay, async () => {
    assert.deepEqual(await fetchTimeline({
      fetchImpl: none.fetchImpl,
      baseUrl: BASE_URL,
      caseId: "fixture-case-0001",
      sessionToken: TOKEN,
      signal: cancelled.signal,
      timeoutMs: delay,
    }), { kind: "aborted" });
  });
  assert.equal(timers.created.size, 0, "a timer was left running for a request that never started");
  assert.equal(none.calls.length, 0);
});

test("caller cancellation and timeout combine: first wins, both abort, listener removed", async () => {
  // Caller first: settles as aborted even though fetch ignores the signal.
  const caller = new AbortController();
  const added = [];
  const removed = [];
  const add = caller.signal.addEventListener.bind(caller.signal);
  const remove = caller.signal.removeEventListener.bind(caller.signal);
  caller.signal.addEventListener = (type, listener) => { added.push(type); add(type, listener); };
  caller.signal.removeEventListener = (type, listener) => { removed.push(type); remove(type, listener); };

  const first = scriptedFetch(["hang"]);
  const pending = fetchTimeline({
    fetchImpl: first.fetchImpl,
    baseUrl: BASE_URL,
    caseId: "fixture-case-0001",
    sessionToken: TOKEN,
    signal: caller.signal,
    timeoutMs: TIMEOUT_MS,
  });
  caller.abort();
  assert.deepEqual(await pending, { kind: "aborted" });
  assert.equal(first.calls[0].init.signal.aborted, true);
  assert.deepEqual(added, ["abort"]);
  assert.deepEqual(removed, ["abort"]);
  await settle();

  // Timeout first: a later caller abort cannot change the settled outcome.
  const later = new AbortController();
  const second = scriptedFetch(["hang"]);
  const timedOut = await fetchTimeline({
    fetchImpl: second.fetchImpl,
    baseUrl: BASE_URL,
    caseId: "fixture-case-0001",
    sessionToken: TOKEN,
    signal: later.signal,
    timeoutMs: TIMEOUT_MS,
  });
  later.abort();
  assert.deepEqual(timedOut, { kind: "failed", reason: "timeout" });
  assert.equal(second.calls[0].init.signal.aborted, true);

  // Already cancelled: nothing is sent at all.
  const cancelled = new AbortController();
  cancelled.abort();
  const none = scriptedFetch([]);
  assert.deepEqual(await fetchTimeline({
    fetchImpl: none.fetchImpl,
    baseUrl: BASE_URL,
    caseId: "fixture-case-0001",
    sessionToken: TOKEN,
    signal: cancelled.signal,
    timeoutMs: TIMEOUT_MS,
  }), { kind: "aborted" });
  assert.equal(none.calls.length, 0);
});

test("an explicitly aborted request cannot later update state", async () => {
  await withoutUnhandledRejections(async () => {
    const lateSuccess = deferred();
    const { calls, store } = await activeStore([() => lateSuccess.promise]);
    const pending = store.loadTimeline();
    store.cancelTimeline();
    assert.equal(calls[1].init.signal.aborted, true);
    await pending;
    assert.equal(store.getSnapshot().timeline.status, "idle");

    lateSuccess.resolve(jsonResponse(200, timelineResponse([ENTRY])));
    await settle();
    assert.equal(store.getSnapshot().timeline.status, "idle");
    assert.equal(store.getSnapshot().timeline.payload, null);
  });

  await withoutUnhandledRejections(async () => {
    const lateFailure = deferred();
    const { store } = await activeStore([() => lateFailure.promise.then(() => {
      throw Object.assign(new Error("The operation was aborted"), { name: "AbortError" });
    })]);
    const pending = store.loadTimeline();
    store.clearSession();
    await pending;
    lateFailure.resolve();
    await settle();
    assert.equal(store.getSnapshot().session, null);
    assert.equal(store.getSnapshot().timeline.status, "idle");
  });
});

test("a late 401 after cancellation cannot clear a session", async () => {
  const late = deferred();
  const { store } = await activeStore([() => late.promise]);
  const pending = store.loadTimeline();
  store.cancelTimeline();
  await pending;
  late.resolve(jsonResponse(401, {}));
  await settle();
  assert.equal(store.getSnapshot().session?.session_id, "fixture-session-0001");
});
