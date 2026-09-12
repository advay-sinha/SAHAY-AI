const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  createChatSendController,
  selectDisplayMessages,
} = require("../src/screens/chatState");

const MOBILE = path.join(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(MOBILE, ...parts), "utf8");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function assistantEvent() {
  return {
    type: "assistant.turn",
    turn_id: "assistant-1",
    text: "assistant text",
    lang: "en",
    intent: "acknowledge",
    audio: "streaming",
  };
}

function officerEvent(origin = "human_officer") {
  return {
    type: "officer.message",
    turn_id: "officer-1",
    text: "officer text",
    lang: "en",
    ts: "2026-09-11T10:00:00Z",
    origin,
  };
}

test("whitespace-only drafts are rejected", async () => {
  let calls = 0;
  const states = [];
  const controller = createChatSendController(async () => { calls += 1; }, (state) => states.push(state));
  controller.setDraft("  \n\t  ");

  assert.equal(await controller.send(), false);
  assert.equal(calls, 0);
  assert.deepEqual(controller.getState().messages, []);
});

test("rapid sends call onSend once and remain pending until acknowledgement", async () => {
  const pending = deferred();
  const states = [];
  let calls = 0;
  const controller = createChatSendController(() => {
    calls += 1;
    return pending.promise;
  }, (state) => states.push(state));
  controller.setDraft("message");

  const first = controller.send();
  const second = controller.send();

  assert.equal(calls, 1);
  assert.equal(await second, false);
  assert.equal(controller.getState().messages[0].status, "pending");
  assert.ok(!states.some((state) => state.messages.some((message) => message.status === "sent")));

  pending.resolve();
  assert.equal(await first, true);
  assert.equal(controller.getState().messages[0].status, "sent");
});

test("rejection retains the failed text and permits one locked retry", async () => {
  const retryPending = deferred();
  const states = [];
  let calls = 0;
  const controller = createChatSendController(() => {
    calls += 1;
    return calls === 1 ? Promise.reject(new Error("unavailable")) : retryPending.promise;
  }, (state) => states.push(state));
  controller.setDraft("keep this");

  assert.equal(await controller.send(), false);
  let current = controller.getState();
  assert.equal(current.draft, "keep this");
  assert.deepEqual(current.messages, [{ id: 1, text: "keep this", status: "failed" }]);

  const firstRetry = controller.retry(1);
  const duplicateRetry = controller.retry(1);
  assert.equal(calls, 2);
  assert.equal(await duplicateRetry, false);
  assert.equal(controller.getState().messages[0].status, "pending");

  retryPending.resolve();
  assert.equal(await firstRetry, true);
  current = controller.getState();
  assert.equal(current.draft, "");
  assert.equal(current.messages[0].status, "sent");
  assert.ok(states.some((state) => state.messages[0]?.status === "failed"));
});

test("disposal suppresses resolution and rejection state updates", async () => {
  for (const outcome of ["resolve", "reject"]) {
    const pending = deferred();
    const states = [];
    const controller = createChatSendController(() => pending.promise, (state) => states.push(state));
    controller.setDraft("message");
    const attempt = controller.send();
    const emissionsBeforeDispose = states.length;
    controller.dispose();

    if (outcome === "resolve") pending.resolve();
    else pending.reject(new Error("unavailable"));

    assert.equal(await attempt, false);
    assert.equal(states.length, emissionsBeforeDispose);
    assert.equal(controller.setDraft("later"), false);
    assert.equal(states.length, emissionsBeforeDispose);
  }
});

test("AI messages and labels require granted consent and explicit permission", () => {
  assert.deepEqual(selectDisplayMessages([assistantEvent()], "granted", true), [
    { id: "assistant:assistant-1", labelKey: "chat.assistant", text: "assistant text" },
  ]);
  assert.deepEqual(selectDisplayMessages([assistantEvent()], "granted", false), []);
  assert.deepEqual(selectDisplayMessages([assistantEvent()], "granted", "true"), []);
  assert.deepEqual(selectDisplayMessages([assistantEvent()], "pending", true), []);
  assert.deepEqual(selectDisplayMessages([assistantEvent()], "declined", true), []);
});

test("only a runtime-validated human officer receives the human label", () => {
  assert.deepEqual(selectDisplayMessages([officerEvent()], "declined", false), [
    { id: "human_officer:officer-1", labelKey: "chat.human_officer", text: "officer text" },
  ]);
  assert.deepEqual(selectDisplayMessages([officerEvent("assistant")], "granted", true), []);
  assert.deepEqual(selectDisplayMessages([{ origin: "unknown", text: "text" }], "granted", true), []);
});

test("ChatScreen is localized, accessible, scroll-safe, and keeps handoff visible", () => {
  const source = read("src", "screens", "ChatScreen.tsx");
  for (const key of [
    "chat.placeholder",
    "chat.send",
    "chat.pending",
    "chat.sent",
    "chat.assistant",
    "chat.human_officer",
    "error.body",
    "error.retry",
  ]) {
    assert.ok(source.includes(`"${key}"`) || source.includes("message.labelKey"), `${key} is missing`);
  }
  assert.match(source, /<ScrollView/);
  assert.match(source, /<TextInput/);
  assert.match(source, /accessibilityHint=/);
  assert.match(source, /accessibilityLabel=/);
  assert.match(source, /accessibilityRole="button"/);
  assert.match(source, /accessibilityState=/);
  assert.match(source, /minHeight:\s*48/);
  assert.match(source, /allowFontScaling/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onRequestHuman\}\s*\/>/);
  assert.match(source, /<AiDisclosure\s*\/>/);
});
