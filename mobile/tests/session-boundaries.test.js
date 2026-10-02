/**
 * Static boundaries for the session and timeline slice. Node, no dependency.
 *
 * REST session creation, one victim-safe timeline, and (EXT-130) the text
 * conversation socket for chat and handoff. The offline queue, storage,
 * audio and every ML module stay disconnected.
 */

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const MOBILE = path.join(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(MOBILE, ...parts), "utf8");

const SLICE_FILES = [
  ["src", "net", "apiConfig.js"],
  ["src", "net", "apiConfig.d.ts"],
  ["src", "net", "restClient.js"],
  ["src", "net", "restClient.d.ts"],
  ["src", "session", "sessionStore.js"],
  ["src", "session", "sessionStore.d.ts"],
  ["src", "session", "SessionProvider.tsx"],
  ["app", "_layout.tsx"],
  ["app", "consent.tsx"],
  ["app", "requests.tsx"],
];

function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/.*$/gm, "$1 ");
}

function productionFiles(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...productionFiles(full));
    else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) found.push(full);
  }
  return found;
}

function allProductionSources() {
  return ["app", "src"].flatMap((root) => productionFiles(path.join(MOBILE, root)))
    .map((file) => ({ file: path.relative(MOBILE, file), code: stripComments(fs.readFileSync(file, "utf8")) }));
}

function importsOf(code) {
  return [...code.matchAll(/(?:from|import|require)\s*\(?\s*["']([^"']+)["']/g)].map((m) => m[1]);
}

/** SHA-256 of the committed blob; CRLF checkouts are normalized first. */
function blobDigest(...parts) {
  const text = fs.readFileSync(path.join(MOBILE, ...parts), "utf8").replace(/\r\n/g, "\n");
  return crypto.createHash("sha256").update(text).digest("hex");
}

test("queue.ts is byte-identical to the integration base", () => {
  assert.equal(blobDigest("src", "net", "queue.ts"), "a0e41a2b9e72108f8aa92f1a1e8dceb62d9fca1e6d336ef53298f7d4d8bf8727");
});

test("no route or slice module imports the socket or the offline queue", () => {
  const offences = [];
  for (const { file, code } of allProductionSources()) {
    if (file === path.join("src", "net", "socket.ts")) continue;
    for (const spec of importsOf(code)) {
      if (/(?:^|\/)(?:socket|queue)$/.test(spec)) offences.push(`${file} -> ${spec}`);
    }
  }
  assert.deepEqual(offences, []);
});

test("the platform socket is built in one place and the token URL in one module", () => {
  const sockets = allProductionSources()
    .filter(({ code }) => /\bWebSocket\b/.test(code))
    .map(({ file }) => file)
    .sort();
  assert.deepEqual(sockets, [
    path.join("src", "net", "socket.ts"),
    path.join("src", "session", "SessionProvider.tsx"),
  ]);
  assert.match(stripComments(read("src", "session", "SessionProvider.tsx")), /\(url\) => new WebSocket\(url\)/);

  const tokenUrls = allProductionSources()
    .filter(({ file, code }) => file !== path.join("src", "net", "socket.ts") && /\?token=/.test(code))
    .map(({ file }) => file);
  assert.deepEqual(tokenUrls, [path.join("src", "net", "conversation.js")]);
  for (const parts of SLICE_FILES) {
    assert.doesNotMatch(stripComments(read(...parts)), /\bws_url\b[^\n]*\+|\?token=/);
  }
});

test("no storage dependency or storage API is used anywhere in the app", () => {
  const offences = [];
  for (const { file, code } of allProductionSources()) {
    for (const pattern of [
      /AsyncStorage/,
      /SecureStore/,
      /expo-secure-store/,
      /expo-file-system/,
      /react-native-mmkv/,
      /\blocalStorage\b/,
      /\bsessionStorage\b/,
      /\bindexedDB\b/,
      /document\.cookie/,
    ]) {
      if (pattern.test(code)) offences.push(`${file}: ${pattern}`);
    }
  }
  assert.deepEqual(offences, []);
});

test("slice modules never log and never build URLs from navigation parameters", () => {
  for (const parts of SLICE_FILES) {
    const code = stripComments(read(...parts));
    assert.doesNotMatch(code, /\bconsole\./, parts.join("/"));
    assert.doesNotMatch(code, /useLocalSearchParams|useGlobalSearchParams|Linking\.|getInitialURL/, parts.join("/"));
    assert.doesNotMatch(code, /analytics|Sentry|crashlytics/i, parts.join("/"));
  }
});

test("the token is sent only in the Authorization header", () => {
  const client = stripComments(read("src", "net", "restClient.js"));
  assert.match(client, /Authorization: `Bearer \$\{sessionToken\}`/);
  // 4 in fetchTimeline, 4 in buildTurnAudioSource (PC-12); both put it in the Authorization header only.
  assert.equal((client.match(/sessionToken/g) ?? []).length, 8);
  assert.doesNotMatch(client, /\?token|token=|encodeURIComponent\(sessionToken\)/);

  const store = stripComments(read("src", "session", "sessionStore.js"));
  assert.doesNotMatch(store, /session_token:\s/);
  assert.match(store, /sessionToken: credential/);
});

test("the timeline URL takes the case only from the validated session", () => {
  const store = stripComments(read("src", "session", "sessionStore.js"));
  assert.match(store, /async loadTimeline\(\) \{/);
  assert.match(store, /caseId: session\.case_id,/);
  assert.equal((store.match(/caseId:/g) ?? []).length, 1);
});

test("the slice renders nothing new: no timestamps, no sort, no assessment field", () => {
  const screen = stripComments(read("src", "screens", "MyRequestsScreen.tsx"));
  assert.doesNotMatch(screen, /\.ts\b|\.sort\(|\.reverse\(/);
  for (const parts of SLICE_FILES) {
    const code = stripComments(read(...parts));
    assert.doesNotMatch(code, /\.sort\(|\.reverse\(|\bentry\.ts\b/, parts.join("/"));
    for (const term of ["svi", "band", "dimension", "dims", "emotion", "assessment", "alert", "severity",
      "recommendation", "confidence", "priority", "needs_human", "supervisor", "executive"]) {
      assert.doesNotMatch(code, new RegExp(`\\b${term}\\b`, "i"), `${parts.join("/")}: ${term}`);
    }
  }
});

test("no mobile module imports ML, shadow or runtime code", () => {
  const offences = [];
  for (const { file, code } of allProductionSources()) {
    for (const spec of importsOf(code)) {
      if (/(?:^|[\\/.])ml(?:[\\/.]|$)|shadow|ml\.runtime|ml\.training|onnx|torch|whisper|silero/i.test(spec)) {
        offences.push(`${file} -> ${spec}`);
      }
    }
  }
  assert.deepEqual(offences, []);
});

test("chat and handoff reach the server only through the store; talk and home stay disconnected", () => {
  for (const route of ["talk.tsx", "home.tsx"]) {
    const code = stripComments(read("app", route));
    assert.doesNotMatch(code, /SessionProvider|sessionStore|restClient|fetch\(/, route);
  }
  for (const route of ["chat.tsx", "handoff.tsx"]) {
    const code = stripComments(read("app", route));
    assert.doesNotMatch(code, /sessionStore"|restClient|conversation"|fetch\(|WebSocket|token/, route);
  }
  const chat = stripComments(read("app", "chat.tsx"));
  assert.match(chat, /aiPermitted=\{consent === "granted"\}/);
  assert.match(chat, /onSend=\{\(text\) => store\.sendChat\(text\)\}/);
  assert.match(chat, /receivedMessages=\{conversation\.events\}/);
  assert.match(stripComments(read("app", "handoff.tsx")), /onRequestHuman=\{\(\) => store\.requestHuman\(getLanguage\(\)\)\}/);
});

test("no dependency was added or changed", () => {
  const pkg = JSON.parse(read("package.json"));
  assert.deepEqual(Object.keys(pkg.dependencies).sort(), [
    "@expo/metro-runtime",
    "expo",
    "expo-asset",
    "expo-audio",
    "expo-constants",
    "expo-linking",
    "expo-router",
    "expo-status-bar",
    "react",
    "react-dom",
    "react-native",
    "react-native-safe-area-context",
    "react-native-screens",
    "react-native-web", // EXT-130 hosted web build
  ]);
  assert.deepEqual(Object.keys(pkg.devDependencies).sort(), ["@types/react", "typescript"]);

  assert.equal(blobDigest("package.json"), "457421c075c94c21d3512c6b1c781a70b34bedc8bec15802a0cb73cebdac71b0");
  assert.equal(blobDigest("package-lock.json"), "e0efe1fe9a607328d4f1565af51ef3416ffc407a494c9b429b17a11dace0bd63");
});

test("production code never imports the test fixtures", () => {
  const offences = allProductionSources()
    .filter(({ code }) => importsOf(code).some((spec) => /fixture|tests\//i.test(spec)))
    .map(({ file }) => file);
  assert.deepEqual(offences, []);
  for (const { code, file } of allProductionSources()) {
    assert.doesNotMatch(code, /fixture-session|fixture-case|SAH-FIXTURE/, file);
  }
});
