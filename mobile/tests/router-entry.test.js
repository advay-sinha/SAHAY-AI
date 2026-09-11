/** Expo Router entry-point contracts. Runs with Node and no installed dependency. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const MOBILE = path.join(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(MOBILE, ...parts), "utf8");

test("the root layout provides a headerless router stack", () => {
  const source = read("app", "_layout.tsx");
  assert.match(source, /from\s+["']expo-router["']/);
  assert.match(source, /<Stack\b/);
  assert.match(source, /headerShown:\s*false/);
});

test("language selection updates i18n before opening consent", () => {
  const source = read("app", "index.tsx");
  const setLanguage = source.indexOf("setLanguage(lang)");
  const navigate = source.indexOf('router.push("/consent")');
  assert.ok(setLanguage >= 0, "language route does not update i18n");
  assert.ok(navigate > setLanguage, "consent opens before the language is updated");
  assert.match(source, /<LanguageScreen\s+onSelectLanguage=\{selectLanguage\}/);
});

test("accepting consent replaces the route with home", () => {
  const source = read("app", "consent.tsx");
  assert.match(source, /onAccept=\{\(\)\s*=>\s*router\.replace\(["']\/home["']\)\}/);
});

test("declined consent can continue to the handoff route", () => {
  const source = read("app", "consent.tsx");
  assert.match(source, /onDecline=\{\(\)\s*=>\s*router\.replace\(["']\/handoff["']\)\}/);
});

test("home sends human requests to the handoff route", () => {
  const source = read("app", "home.tsx");
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);
});

test("home opens the chat route", () => {
  const source = read("app", "home.tsx");
  assert.match(source, /onOpenChat=\{\(\)\s*=>\s*router\.push\(["']\/chat["']\)\}/);
});

test("home opens the requests route", () => {
  const source = read("app", "home.tsx");
  assert.match(source, /onOpenRequests=\{\(\)\s*=>\s*router\.push\(["']\/requests["']\)\}/);
});

test("the requests route is local, unavailable, and keeps handoff available", () => {
  const source = read("app", "requests.tsx");
  assert.match(source, /<MyRequestsScreen/);
  assert.match(source, /loadState=["']unavailable["']/);
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);
  assert.doesNotMatch(source, /payload=|fetch\(|WebSocket|Promise\.resolve/);
});

test("the chat route cannot simulate successful delivery", () => {
  const source = read("app", "chat.tsx");
  assert.match(source, /async function unavailableSend\(_text:\s*string\):\s*Promise<void>\s*\{\s*throw new Error\(\);\s*\}/);
  assert.match(source, /onSend=\{unavailableSend\}/);
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);
  assert.doesNotMatch(source, /Promise\.resolve|status=["']sent["']/);
});

test("the handoff route injects an unavailable callback rather than simulated success", () => {
  const source = read("app", "handoff.tsx");
  assert.match(source, /async function unavailableHumanRequest\(\): Promise<void>\s*\{\s*throw new Error\(\);\s*\}/);
  assert.match(source, /<HandoffScreen\s+onRequestHuman=\{unavailableHumanRequest\}\s*\/>/);
  assert.doesNotMatch(source, /initialState/);
});
