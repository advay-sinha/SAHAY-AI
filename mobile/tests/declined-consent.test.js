/**
 * Declined-consent lifecycle. Node, no dependency.
 *
 * The route's real declineConsent body (app/consent.tsx) is executed against
 * the real session store with a mocked fetch and a recording router.
 *
 * Lifecycle: the decision starts exactly one POST /sessions with
 * consent "declined" in the background and navigates to /handoff at once.
 * The human-support route never waits on the backend. A failure leaves no
 * session and is not retried; a late result is kept only if it still
 * belongs to the current decision. No handoff request is sent, and no AI
 * conversation opens.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { createSessionStore } = require("../src/session/sessionStore");
const {
  BASE_URL,
  deferred,
  jsonResponse,
  scriptedFetch,
  sessionResponse,
} = require("./fixtures/sessionFixtures");

const MOBILE = path.join(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(MOBILE, ...parts), "utf8");
const settle = () => new Promise((resolve) => setTimeout(resolve, 30));

function routeBody(name) {
  const source = read("app", "consent.tsx");
  const match = source.match(
    new RegExp(`(?:async )?function ${name}\\(\\): (?:Promise<void>|void) \\{([\\s\\S]*?)\\r?\\n  \\}`),
  );
  assert.ok(match, `${name} is missing`);
  return match[1];
}

function declinedFlow(replies, lang = "hi") {
  const fake = scriptedFetch(replies);
  const store = createSessionStore({ apiUrl: BASE_URL, fetchImpl: fake.fetchImpl, timeoutMs: 50 });
  const navigation = [];
  const router = {
    replace: (href) => navigation.push(["replace", href]),
    push: (href) => navigation.push(["push", href]),
  };
  const decline = new Function("store", "getLanguage", "router", routeBody("declineConsent"));
  return {
    ...fake,
    navigation,
    store,
    decline: () => decline(store, () => lang, router),
  };
}

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
  assert.deepEqual(seen, []);
}

test("decline starts exactly one declined POST /sessions and navigates at once", async () => {
  for (const lang of ["hi", "en"]) {
    const pending = deferred();
    const flow = declinedFlow([() => pending.promise], lang);

    flow.decline();

    // Navigation happened before the backend answered.
    assert.deepEqual(flow.navigation, [["replace", "/handoff"]]);
    assert.equal(flow.store.getSnapshot().creation.status, "creating");
    assert.equal(flow.calls.length, 1);
    assert.equal(flow.calls[0].url, `${BASE_URL}/sessions`);
    assert.equal(flow.calls[0].init.method, "POST");
    assert.equal(flow.calls[0].init.body, JSON.stringify({ channel: "mobile_chat", consent: "declined", lang }));

    // The declined note's "Talk to a person" calls onDecline again: still one request.
    flow.decline();
    assert.equal(flow.calls.length, 1);
    assert.deepEqual(flow.navigation, [["replace", "/handoff"], ["replace", "/handoff"]]);

    pending.resolve(jsonResponse(201, sessionResponse({ consent: "declined", lang })));
    await settle();
    assert.equal(flow.store.getSnapshot().session?.consent, "declined");
    assert.equal(flow.calls.length, 1);
  }
});

test("decline navigates only to the human-support route", async () => {
  const flow = declinedFlow([jsonResponse(201, sessionResponse({ consent: "declined" }))]);
  flow.decline();
  await settle();
  assert.ok(flow.navigation.every(([, href]) => href === "/handoff"));
  assert.ok(flow.navigation.every(([method]) => method === "replace"));
});

test("a failed declined request creates, shows and retries nothing", async () => {
  const replies = [
    new TypeError("Network request failed"),
    jsonResponse(503, {}),
    jsonResponse(201, sessionResponse({ consent: "granted" })),
    jsonResponse(201, sessionResponse({ consent: "declined", extra: 1 })),
    "hang",
  ];
  for (const reply of replies) {
    await withoutUnhandledRejections(async () => {
      const flow = declinedFlow([reply]);
      flow.decline();
      await settle();
      await settle();

      const snapshot = flow.store.getSnapshot();
      assert.equal(snapshot.session, null);
      assert.equal(snapshot.creation.status, "failed");
      assert.equal(snapshot.creation.consent, "declined");
      assert.equal(flow.calls.length, 1, "declined creation was retried automatically");
      assert.deepEqual(flow.navigation, [["replace", "/handoff"]]);
    });
  }
});

test("the background promise cannot reject, even if fetch or a subscriber throws", async () => {
  await withoutUnhandledRejections(async () => {
    const flow = declinedFlow([]);
    flow.store.subscribe(() => {
      throw new Error("subscriber failure");
    });
    flow.decline();
    await settle();
    assert.equal(flow.store.getSnapshot().session, null);
    assert.deepEqual(flow.navigation, [["replace", "/handoff"]]);
  });

  await withoutUnhandledRejections(async () => {
    const store = createSessionStore({
      apiUrl: BASE_URL,
      fetchImpl: () => {
        throw new Error("synchronous platform failure");
      },
    });
    const result = await store.startSession("declined", "hi");
    assert.deepEqual(result, { ok: false, reason: "network" });
  });
});

test("a late success is kept only while it belongs to the current decision", async () => {
  const late = deferred();
  const flow = declinedFlow([
    () => late.promise,
    jsonResponse(201, sessionResponse({
      session_id: "fixture-session-0002",
      case_id: "fixture-case-0002",
      ws_url: "/ws/session/fixture-session-0002",
      consent: "declined",
    })),
  ]);

  flow.decline();
  flow.store.clearSession();
  flow.decline();
  late.resolve(jsonResponse(201, sessionResponse({ consent: "declined" })));
  await settle();

  assert.equal(flow.store.getSnapshot().session?.session_id, "fixture-session-0002");
  assert.equal(flow.calls.length, 2);

  const orphan = deferred();
  const cleared = declinedFlow([() => orphan.promise]);
  cleared.decline();
  cleared.store.clearSession();
  orphan.resolve(jsonResponse(201, sessionResponse({ consent: "declined" })));
  await settle();
  assert.equal(cleared.store.getSnapshot().session, null);
});

test("decline sends only session creation and leaves live handoff credential-gated", async () => {
  const flow = declinedFlow([jsonResponse(201, sessionResponse({ consent: "declined" }))]);
  flow.decline();
  await settle();
  assert.deepEqual(flow.calls.map((call) => `${call.init.method} ${call.url}`), [`POST ${BASE_URL}/sessions`]);

  const handoff = read("app", "handoff.tsx");
  const provider = read("src", "session", "SessionProvider.tsx");
  assert.match(handoff, /const \{ requestHuman \} = useSession\(\)/);
  assert.match(provider, /if \(session\?\.consent === ["']granted["']\) liveSession\.current = session/);
  assert.match(provider, /if \(active === null\) throw new ApiError\(["']authentication["']\)/);
  assert.doesNotMatch(handoff, /fetch\(|sessionStore|restClient|WebSocket/);
});

test("no AI conversation opens on the declined path", () => {
  const source = read("app", "consent.tsx");
  const decline = routeBody("declineConsent");
  const retry = routeBody("retrySession");

  assert.doesNotMatch(decline, /\/home|\/chat|\/talk|await/);
  // Home opens only from the granted decision, or from a granted retry.
  assert.match(routeBody("acceptConsent"), /store\.startSession\("granted"/);
  assert.match(retry, /result\.session\.consent === "granted"\) router\.replace\("\/home"\)/);
  // The consent error screen is shown for a granted failure only.
  assert.match(source, /const grantedFailed = creation\.consent === "granted"/);
  // Chat is enabled only for a validated granted public session; the private
  // live credential is likewise retained only for granted consent.
  const chat = read("app", "chat.tsx");
  const provider = read("src", "session", "SessionProvider.tsx");
  assert.match(chat, /aiPermitted=\{session\?\.consent === ["']granted["']\}/);
  assert.match(provider, /if \(session\?\.consent === ["']granted["']\) liveSession\.current = session/);
  assert.doesNotMatch(decline, /sendChat|requestHuman|WebSocket/);
});
