const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const MOBILE = path.join(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(MOBILE, ...parts), "utf8");
const { createHandoffRequestController } = require("../src/screens/handoffState");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

test("two immediate attempts invoke the callback exactly once", async () => {
  const pending = deferred();
  const states = [];
  let calls = 0;
  const controller = createHandoffRequestController(() => {
    calls += 1;
    return pending.promise;
  }, (state) => states.push(state));

  const first = controller.request();
  const second = controller.request();

  assert.equal(calls, 1);
  assert.deepEqual(states, ["requesting"]);
  assert.equal(await second, false);

  pending.resolve();
  assert.equal(await first, true);
  assert.deepEqual(states, ["requesting", "requested"]);
});

test("success is emitted only after the callback resolves", async () => {
  const pending = deferred();
  const states = [];
  const controller = createHandoffRequestController(
    () => pending.promise,
    (state) => states.push(state),
  );

  const attempt = controller.request();
  assert.deepEqual(states, ["requesting"]);
  assert.ok(!states.includes("requested"));

  pending.resolve();
  assert.equal(await attempt, true);
  assert.deepEqual(states, ["requesting", "requested"]);
});

test("rejection emits failed, unlocks, and permits a new retry", async () => {
  const states = [];
  let calls = 0;
  const controller = createHandoffRequestController(async () => {
    calls += 1;
    if (calls === 1) throw new Error("unavailable");
  }, (state) => states.push(state));

  assert.equal(await controller.request(), false);
  assert.deepEqual(states, ["requesting", "failed"]);
  assert.ok(!states.includes("requested"));

  assert.equal(await controller.request(), true);
  assert.equal(calls, 2);
  assert.deepEqual(states, ["requesting", "failed", "requesting", "requested"]);
});

test("disposal suppresses success after an in-flight request resolves", async () => {
  const pending = deferred();
  const states = [];
  const controller = createHandoffRequestController(
    () => pending.promise,
    (state) => states.push(state),
  );

  const attempt = controller.request();
  controller.dispose();
  pending.resolve();

  assert.equal(await attempt, false);
  assert.deepEqual(states, ["requesting"]);
});

test("disposal suppresses failure after an in-flight request rejects", async () => {
  const pending = deferred();
  const states = [];
  const controller = createHandoffRequestController(
    () => pending.promise,
    (state) => states.push(state),
  );

  const attempt = controller.request();
  controller.dispose();
  pending.reject(new Error("unavailable"));

  assert.equal(await attempt, false);
  assert.deepEqual(states, ["requesting"]);
});

test("handoff has no public initial state and disposes its controller on unmount", () => {
  const source = read("src", "screens", "HandoffScreen.tsx");
  assert.doesNotMatch(source, /initialState/);
  assert.match(source, /useState<HandoffState>\("idle"\)/);
  assert.match(source, /return \(\) => controller\?\.dispose\(\)/);
  assert.match(source, /createHandoffRequestController/);
});

test("handoff renders localized states and is scroll-safe", () => {
  const source = read("src", "screens", "HandoffScreen.tsx");
  assert.match(source, /t\("human\.requested"\)/);
  assert.match(source, /t\("error\.body"\)/);
  assert.match(source, /t\("error\.retry"\)/);
  assert.match(source, /t\("human\.button"\)/);
  assert.match(source, /<AiDisclosure\s*\/>/);
  assert.match(source, /<ScrollView/);
  assert.match(source, /contentContainerStyle=\{\{\s*flexGrow:\s*1/);
  assert.match(source, /allowFontScaling/);
});

test("consent is scroll-safe after the declined controls appear", () => {
  const source = read("src", "screens", "ConsentScreen.tsx");
  assert.match(source, /<ScrollView\s+contentContainerStyle=\{\{\s*flexGrow:\s*1/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onDecline\}\s*\/>/);
});

test("the reusable human control is accessible and at least 48px high", () => {
  const source = read("src", "components", "TalkToPersonButton.tsx");
  assert.match(source, /accessibilityRole="button"/);
  assert.match(source, /accessibilityLabel=\{label\}/);
  assert.match(source, /accessibilityState=\{\{\s*busy,\s*disabled\s*\}\}/);
  assert.match(source, /minHeight:\s*56/);
  assert.match(source, /allowFontScaling/);
});
