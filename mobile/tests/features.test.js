/** EXPO_PUBLIC_VOICE handling (EXT-130 hosted text-only builds). Runs with Node only. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { resolveVoiceEnabled, voiceEnabled } = require("../src/net/features");

const MOBILE = path.join(__dirname, "..");

test("voice stays on unless explicitly switched off", () => {
  assert.equal(resolveVoiceEnabled(undefined), true);
  assert.equal(resolveVoiceEnabled(""), true);
  assert.equal(resolveVoiceEnabled("on"), true);
  assert.equal(resolveVoiceEnabled("off"), false);
  assert.equal(resolveVoiceEnabled(" OFF "), false);
});

test("voiceEnabled reads EXPO_PUBLIC_VOICE at call time", () => {
  const previous = process.env.EXPO_PUBLIC_VOICE;
  try {
    process.env.EXPO_PUBLIC_VOICE = "off";
    assert.equal(voiceEnabled(), false);
    delete process.env.EXPO_PUBLIC_VOICE;
    assert.equal(voiceEnabled(), true);
  } finally {
    if (previous === undefined) delete process.env.EXPO_PUBLIC_VOICE;
    else process.env.EXPO_PUBLIC_VOICE = previous;
  }
});

test("the variable is read by direct member access so Expo inlines it", () => {
  const source = fs.readFileSync(path.join(MOBILE, "src", "net", "features.js"), "utf8");
  assert.match(source, /process\.env\.EXPO_PUBLIC_VOICE/);
});

test("home hides the talk control and /talk redirects when voice is off", () => {
  const home = fs.readFileSync(path.join(MOBILE, "app", "home.tsx"), "utf8");
  assert.match(home, /showTalk=\{voiceEnabled\(\)\}/);
  const screen = fs.readFileSync(path.join(MOBILE, "src", "screens", "HomeScreen.tsx"), "utf8");
  assert.match(screen, /\{showTalk \?/);
  const talk = fs.readFileSync(path.join(MOBILE, "app", "talk.tsx"), "utf8");
  assert.match(talk, /if \(!voiceEnabled\(\)\) return <Redirect href="\/chat" \/>/);
});

test("the talk-to-a-person control is never behind the voice switch", () => {
  const screen = fs.readFileSync(path.join(MOBILE, "src", "screens", "HomeScreen.tsx"), "utf8");
  const gated = screen.slice(screen.indexOf("{showTalk ?"), screen.indexOf(") : null}"));
  assert.doesNotMatch(gated, /TalkToPersonButton/);
  assert.match(screen, /<TalkToPersonButton onPress=\{onRequestHuman\} \/>/);
});

test("the tester notice is off unless the build sets it on", () => {
  const { resolveTesterBuild } = require("../src/net/features");
  assert.equal(resolveTesterBuild(undefined), false);
  assert.equal(resolveTesterBuild(""), false);
  assert.equal(resolveTesterBuild("off"), false);
  assert.equal(resolveTesterBuild("on"), true);
  assert.equal(resolveTesterBuild(" ON "), true);
});

test("every AI disclosure carries the tester notice beside it, outside the grouped label", () => {
  const source = fs.readFileSync(path.join(MOBILE, "src", "components", "AiDisclosure.tsx"), "utf8");
  assert.match(source, /<\/View>\s*<TesterNotice \/>\s*<\/>/);
  const notice = fs.readFileSync(path.join(MOBILE, "src", "components", "TesterNotice.tsx"), "utf8");
  assert.match(notice, /if \(!testerBuild\(\)\) return null;/);
  assert.match(notice, /t\("disclosure\.tester"\)/);
  assert.match(
    fs.readFileSync(path.join(MOBILE, "src", "net", "features.js"), "utf8"),
    /process\.env\.EXPO_PUBLIC_TESTER_BUILD/,
  );
});
