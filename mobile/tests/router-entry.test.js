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

test("accepting consent creates the session before replacing with home", () => {
  const source = read("app", "consent.tsx");
  assert.match(source, /await createSession\(consent\)/);
  assert.ok(source.indexOf("await createSession(consent)") < source.indexOf("router.replace"));
  assert.match(source, /onAccept=\{\(\) => decide\("granted"\)\}/);
  assert.match(source, /consent === "granted" \? "\/home" : "\/handoff"/);
});

test("declined consent creates a declined session before handoff", () => {
  const source = read("app", "consent.tsx");
  assert.match(source, /onDecline=\{\(\) => decide\("declined"\)\}/);
  assert.match(source, /router\.replace\(consent === "granted" \? "\/home" : "\/handoff"\)/);
});

test("accept and decline route callbacks remain strictly separated", () => {
  const source = read("app", "consent.tsx");
  assert.equal((source.match(/decide\("granted"\)/g) ?? []).length, 1);
  assert.equal((source.match(/decide\("declined"\)/g) ?? []).length, 1);
  assert.match(source, /createSession\(consent\)/);
});

test("home sends human requests to the handoff route", () => {
  const source = read("app", "home.tsx");
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);
});

test("home opens the chat route", () => {
  const source = read("app", "home.tsx");
  assert.match(source, /onOpenChat=\{\(\)\s*=>\s*router\.push\(["']\/chat["']\)\}/);
});

test("home opens the talk route without changing its other destinations", () => {
  const source = read("app", "home.tsx");
  assert.match(source, /onOpenTalk=\{\(\)\s*=>\s*router\.push\(["']\/talk["']\)\}/);
  assert.equal((source.match(/router\.push\(["']\/talk["']\)/g) ?? []).length, 1);
  assert.match(source, /onOpenChat=\{\(\)\s*=>\s*router\.push\(["']\/chat["']\)\}/);
  assert.match(source, /onOpenRequests=\{\(\)\s*=>\s*router\.push\(["']\/requests["']\)\}/);
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);
});

test("home opens the requests route", () => {
  const source = read("app", "home.tsx");
  assert.match(source, /onOpenRequests=\{\(\)\s*=>\s*router\.push\(["']\/requests["']\)\}/);
});

test("the requests route loads only the active session timeline and keeps handoff available", () => {
  const source = read("app", "requests.tsx");
  assert.match(source, /<MyRequestsScreen/);
  assert.match(source, /const \{ session, loadTimeline \} = useSession\(\)/);
  assert.match(source, /loadTimeline\(\)\.then/);
  assert.match(source, /if \(!active \|\| value === null\) return/);
  assert.match(source, /loadState=\{loadState\}/);
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);
  assert.doesNotMatch(source, /fetch\(|WebSocket|Promise\.resolve/);
});

test("the chat route uses acknowledgement-backed session delivery", () => {
  const source = read("app", "chat.tsx");
  assert.match(source, /const \{ session, events, sendChat \} = useSession\(\)/);
  assert.match(source, /onSend=\{sendChat\}/);
  assert.match(source, /receivedMessages=\{events\}/);
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);
  assert.doesNotMatch(source, /Promise\.resolve|status=["']sent["']/);
});

test("the handoff route uses the causal session acknowledgement", () => {
  const source = read("app", "handoff.tsx");
  assert.match(source, /const \{ requestHuman \} = useSession\(\)/);
  assert.match(source, /<HandoffScreen onRequestHuman=\{requestHuman\} \/>/);
  assert.doesNotMatch(source, /Promise\.resolve/);
  assert.doesNotMatch(source, /initialState/);
});

test("the error route renders ErrorScreen and sends human contact only to handoff", () => {
  const source = read("app", "error.tsx");
  assert.match(source, /<ErrorScreen\b/);
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);

  const humanCallback = source.match(/onRequestHuman=\{([\s\S]*?)\}/);
  assert.ok(humanCallback, "error route human callback is missing");
  assert.equal((humanCallback[1].match(/router\.(?:push|replace|back)/g) ?? []).length, 1);
  assert.doesNotMatch(humanCallback[1], /["']\/(?:home|error|offline|talk)["']/);
});

test("the error route retries with back navigation and a home fallback", () => {
  const source = read("app", "error.tsx");
  const retry = source.match(/function retry\(\): void\s*\{([\s\S]*?)\r?\n  \}\r?\n\r?\n  return \(/);
  assert.ok(retry, "error route retry callback is missing");
  assert.match(retry[1], /if \(router\.canGoBack\(\)\)\s*\{\s*router\.back\(\);\s*return;/);
  assert.match(retry[1], /router\.replace\(["']\/home["']\)/);
  assert.match(source, /onRetry=\{retry\}/);
  assert.equal((retry[1].match(/router\.back\(\)/g) ?? []).length, 1);
  assert.equal((retry[1].match(/router\.replace\(["']\/home["']\)/g) ?? []).length, 1);
  assert.doesNotMatch(retry[1], /router\.push|["']\/(?:handoff|error|offline|talk)["']/);
});

test("the error route has no fabricated operation behavior", () => {
  const source = read("app", "error.tsx");
  assert.doesNotMatch(
    source,
    /Promise|setTimeout|setInterval|fetch\(|axios|XMLHttpRequest|WebSocket|AsyncStorage|localStorage|sessionStorage|console\.|success|status|result/i,
  );
});

test("the talk route renders TalkScreen with strictly separated destinations", () => {
  const source = read("app", "talk.tsx");
  assert.match(source, /<TalkScreen\b/);
  assert.match(source, /onOpenChat=\{\(\)\s*=>\s*router\.push\(["']\/chat["']\)\}/);
  assert.match(source, /onRequestHuman=\{\(\)\s*=>\s*router\.push\(["']\/handoff["']\)\}/);

  const chatCallback = source.match(/onOpenChat=\{([\s\S]*?)\}/);
  const humanCallback = source.match(/onRequestHuman=\{([\s\S]*?)\}/);
  assert.ok(chatCallback, "talk route chat callback is missing");
  assert.ok(humanCallback, "talk route human callback is missing");
  assert.deepEqual(chatCallback[1].match(/router\.push\(["']([^"']+)["']\)/g), ['router.push("/chat")']);
  assert.deepEqual(humanCallback[1].match(/router\.push\(["']([^"']+)["']\)/g), ['router.push("/handoff")']);
});

test("the offline route remains absent and is not routed", () => {
  assert.equal(fs.existsSync(path.join(MOBILE, "app", "offline.tsx")), false);
  const routeSources = fs.readdirSync(path.join(MOBILE, "app"))
    .filter((name) => name.endsWith(".tsx"))
    .map((name) => read("app", name))
    .join("\n");
  assert.doesNotMatch(routeSources, /router\.(?:push|replace)\(["']\/offline["']\)/);
});
