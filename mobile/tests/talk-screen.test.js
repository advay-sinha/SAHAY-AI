/** Presentation-only Talk screen contracts. Runs with Node and no installed dependency. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SCREEN = path.join(__dirname, "..", "src", "screens", "TalkScreen.tsx");
const source = fs.readFileSync(SCREEN, "utf8");

test("TalkScreen uses only the approved localized presentation labels", () => {
  const keys = [...source.matchAll(/t\(["']([^"']+)["']\)/g)].map((match) => match[1]);
  assert.deepEqual(keys.sort(), ["home.chat", "home.talk"]);
  assert.match(source, /<Text\s+accessibilityRole="header"[^>]*>[\s\S]*t\(["']home\.talk["']\)/);
  assert.match(source, /<AiDisclosure\s*\/>/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onRequestHuman\}\s*\/>/);
});

test("TalkScreen keeps disclosure and human contact outside its scroll-safe content", () => {
  assert.match(source, /<ScrollView[\s\S]*contentContainerStyle=\{\{\s*flexGrow:\s*1/);
  assert.match(source, /<ScrollView[\s\S]*style=\{\{\s*flex:\s*1\s*\}\}/);
  const scrollEnd = source.indexOf("</ScrollView>");
  const disclosure = source.indexOf("<AiDisclosure");
  const scrollStart = source.indexOf("<ScrollView");
  const humanContact = source.indexOf("<TalkToPersonButton");
  assert.ok(scrollEnd >= 0, "scrolling content is missing");
  assert.ok(disclosure >= 0 && disclosure < scrollStart, "disclosure is inside the ScrollView");
  assert.ok(humanContact > scrollEnd, "human contact is inside the ScrollView");
});

test("TalkScreen chat alternative is accessible and large-font safe", () => {
  assert.match(source, /onOpenChat:\s*\(\)\s*=>\s*void/);
  assert.match(source, /accessibilityLabel=\{chatLabel\}/);
  assert.match(source, /accessibilityRole="button"/);
  assert.match(source, /accessibilityState=\{\{\s*disabled:\s*false\s*\}\}/);
  assert.match(source, /onPress=\{onOpenChat\}/);
  assert.match(source, /minHeight:\s*48/);
  assert.ok((source.match(/allowFontScaling/g) ?? []).length >= 2);
});

test("TalkScreen contains no voice capability, fabricated state, or unavailable presentation", () => {
  const prohibitedKeys = [
    "talk.listening",
    "talk.speaking",
    "talk.tap_to_speak",
    "talk.tap_to_send",
    "human.joined",
    "offline.body",
  ];
  for (const key of prohibitedKeys) {
    assert.equal(source.includes(key), false, `${key} must not be presented`);
  }

  assert.doesNotMatch(
    source,
    /expo-audio|Audio|microphone|record(?:ing)?|playback|permission|setTimeout|setInterval|transcript|fetch\(|WebSocket|queue|status|success|message\s*=|useState|useEffect|Date\.|Promise/i,
  );
});
