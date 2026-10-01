/**
 * The victim conversation socket and its store wiring. Node, no dependency.
 *
 * A fake socket stands in for the platform WebSocket; every frame is a
 * clearly fictional fixture.
 */

const assert = require("node:assert/strict");
const test = require("node:test");

const { createConversation, socketBaseUrl } = require("../src/net/conversation");
const { createSessionStore } = require("../src/session/sessionStore");
const { BASE_URL, TOKEN, jsonResponse, scriptedFetch, sessionResponse } = require("./fixtures/sessionFixtures");

function fakeSockets() {
  const opened = [];
  function socketFactory(url) {
    const socket = {
      url,
      readyState: 0,
      sent: [],
      closed: false,
      onopen: null,
      onmessage: null,
      onerror: null,
      onclose: null,
      send(data) {
        this.sent.push(JSON.parse(data));
      },
      close() {
        this.closed = true;
      },
      serverOpen() {
        this.readyState = 1;
        this.onopen?.({});
      },
      serverSend(frame) {
        this.onmessage?.({ data: typeof frame === "string" ? frame : JSON.stringify(frame) });
      },
      serverClose(code = 1006) {
        this.readyState = 3;
        this.onclose?.({ code });
      },
    };
    opened.push(socket);
    return socket;
  }
  return { opened, socketFactory };
}

function manualTimers() {
  const pending = new Map();
  let next = 1;
  return {
    pending,
    setTimer(fn, ms) {
      const id = next++;
      pending.set(id, { fn, ms });
      return id;
    },
    clearTimer(id) {
      pending.delete(id);
    },
    fireAll() {
      const due = [...pending.entries()];
      pending.clear();
      for (const [, { fn }] of due) fn();
    },
  };
}

function conversationWith(options = {}) {
  const sockets = fakeSockets();
  const timers = manualTimers();
  const states = [];
  const conversation = createConversation({
    baseUrl: "https://backend.fixture.test",
    sessionId: "fixture-session-0001",
    token: TOKEN,
    lang: "en",
    socketFactory: sockets.socketFactory,
    onChange: (state) => states.push(state),
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    ...options,
  });
  return { conversation, sockets, states, timers };
}

const victimLine = (text, id = "turn-v1") => ({
  type: "transcript.line", turn_id: id, speaker: "victim", text, lang: "en", ts: "2026-10-01T10:00:00Z",
});
const assistantTurn = (text, id = "turn-a1") => ({
  type: "assistant.turn", turn_id: id, text, lang: "en", intent: "ask_medical_need", audio: "prerecorded",
});
const status = (overrides = {}) => ({
  type: "session.status", state: "S2", consent: "granted", lang: "en", human_joined: false, ...overrides,
});

test("socket URLs follow the API scheme", () => {
  assert.equal(socketBaseUrl("https://api.fixture.test"), "wss://api.fixture.test");
  assert.equal(socketBaseUrl("http://10.0.0.5:8000"), "ws://10.0.0.5:8000");
  assert.equal(socketBaseUrl("ftp://x"), null);
});

test("the token reaches only the socket URL, never any state", () => {
  const { conversation, sockets, states } = conversationWith();
  conversation.connect();
  assert.equal(sockets.opened.length, 1);
  assert.equal(
    sockets.opened[0].url,
    `wss://backend.fixture.test/ws/session/fixture-session-0001?token=${encodeURIComponent(TOKEN)}`,
  );
  sockets.opened[0].serverOpen();
  sockets.opened[0].serverSend(status());
  assert.doesNotMatch(JSON.stringify(states), /NEVER-LOG|token/);
});

test("only allowlisted, well-formed events are kept; assessment frames are dropped", () => {
  const { conversation, sockets, states } = conversationWith();
  conversation.connect();
  const socket = sockets.opened[0];
  socket.serverOpen();
  socket.serverSend({ type: "assessment.update", svi: 80, band: "Critical" });
  socket.serverSend({ ...assistantTurn("hello"), band: "High" });
  socket.serverSend("not json");
  socket.serverSend(assistantTurn("Does anyone need medical help right now?"));
  socket.serverSend(status({ human_joined: true }));
  const last = states.at(-1);
  assert.deepEqual(last.events.map((event) => event.type), ["assistant.turn"]);
  assert.equal(last.sessionStatus.human_joined, true);
  assert.doesNotMatch(JSON.stringify(last), /svi|band|Critical/i);
});

test("a chat turn is delivered only when the server echoes it", async () => {
  const { conversation, sockets } = conversationWith();
  conversation.connect();
  const socket = sockets.opened[0];
  socket.serverOpen();
  let delivered = false;
  const sending = conversation.sendChat("They came again.").then(() => { delivered = true; });
  assert.deepEqual(socket.sent, [{ type: "chat.message", text: "They came again.", lang: "en" }]);
  await Promise.resolve();
  assert.equal(delivered, false);
  socket.serverSend(victimLine("They came again."));
  await sending;
  assert.equal(delivered, true);
});

test("a turn fails when the socket is not open, when the echo never comes, or when it drops", async () => {
  const { conversation, sockets, timers } = conversationWith();
  await assert.rejects(conversation.sendChat("early"));
  conversation.connect();
  sockets.opened[0].serverOpen();

  const timedOut = conversation.sendChat("no echo");
  timers.fireAll();
  await assert.rejects(timedOut);

  const dropped = conversation.sendChat("dropped");
  sockets.opened[0].serverClose(1006);
  await assert.rejects(dropped);
});

test("a dropped socket reconnects with backoff; a refused one does not", () => {
  const { conversation, sockets, states, timers } = conversationWith();
  conversation.connect();
  sockets.opened[0].serverOpen();
  sockets.opened[0].serverClose(1006);
  assert.equal(states.at(-1).status, "reconnecting");
  assert.deepEqual([...timers.pending.values()].map((t) => t.ms), [1000]);
  timers.fireAll();
  assert.equal(sockets.opened.length, 2);

  sockets.opened[1].serverClose(1008);
  assert.equal(states.at(-1).status, "closed");
  assert.equal(timers.pending.size, 0);
});

test("close stops reconnecting and closes the socket", () => {
  const { conversation, sockets, timers } = conversationWith();
  conversation.connect();
  sockets.opened[0].serverClose(1006);
  conversation.close();
  assert.equal(timers.pending.size, 0);
  timers.fireAll();
  assert.equal(sockets.opened.length, 1);
});

test("the human request is one frame on an open socket", async () => {
  const { conversation, sockets } = conversationWith();
  conversation.connect();
  await assert.rejects(conversation.requestHuman());
  sockets.opened[0].serverOpen();
  await conversation.requestHuman();
  assert.deepEqual(sockets.opened[0].sent, [{ type: "request_human" }]);
});

function storeWith(replies) {
  const fake = scriptedFetch(replies);
  const sockets = fakeSockets();
  const store = createSessionStore({ apiUrl: BASE_URL, fetchImpl: fake.fetchImpl, socketFactory: sockets.socketFactory });
  return { ...fake, sockets, store };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

test("the store opens one socket for its session and keeps the token out of the snapshot", async () => {
  const { sockets, store } = storeWith([jsonResponse(201, sessionResponse({ lang: "en" }))]);
  store.connectConversation();
  assert.equal(sockets.opened.length, 0, "no socket before a session exists");
  await store.startSession("granted", "en");
  store.connectConversation();
  store.connectConversation();
  assert.equal(sockets.opened.length, 1);
  assert.match(sockets.opened[0].url, /^ws:\/\/backend\.fixture\.test:8000\/ws\/session\/fixture-session-0001\?token=/);
  sockets.opened[0].serverOpen();
  sockets.opened[0].serverSend(assistantTurn("Is there someone with you right now?"));
  assert.equal(store.getSnapshot().conversation.events.length, 1);
  assert.doesNotMatch(JSON.stringify(store.getSnapshot()), /NEVER-LOG|session_token/);
});

test("sendChat waits for the open socket, then for the echo", async () => {
  const { sockets, store } = storeWith([jsonResponse(201, sessionResponse({ lang: "en" }))]);
  await store.startSession("granted", "en");
  const sending = store.sendChat("They came again.");
  await tick();
  sockets.opened[0].serverOpen();
  await tick();
  assert.deepEqual(sockets.opened[0].sent, [{ type: "chat.message", text: "They came again.", lang: "en" }]);
  sockets.opened[0].serverSend(victimLine("They came again."));
  await sending;
});

test("asking for a person with no session creates a declined session, then requests a human", async () => {
  const { calls, sockets, store } = storeWith([jsonResponse(201, sessionResponse({ consent: "declined" }))]);
  const requesting = store.requestHuman("hi");
  await tick();
  assert.equal(calls.length, 1);
  assert.deepEqual(JSON.parse(calls[0].init.body).consent, "declined");
  sockets.opened[0].serverOpen();
  await requesting;
  assert.deepEqual(sockets.opened[0].sent, [{ type: "request_human" }]);
});

test("clearing the session closes its socket and empties the conversation", async () => {
  const { sockets, store } = storeWith([jsonResponse(201, sessionResponse())]);
  await store.startSession("granted", "hi");
  store.connectConversation();
  store.clearSession();
  assert.equal(sockets.opened[0].closed, true);
  assert.equal(store.getSnapshot().conversation.status, "idle");
  assert.deepEqual(store.getSnapshot().conversation.events, []);
});
