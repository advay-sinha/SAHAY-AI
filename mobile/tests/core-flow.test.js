/** Slice 1 screen contracts. Runs with Node and no installed dependency. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SCREENS = path.join(__dirname, "..", "src", "screens");
const readScreen = (name) => fs.readFileSync(path.join(SCREENS, name), "utf8");

test("language offers accessible Hindi and English 48px controls", () => {
  const source = readScreen("LanguageScreen.tsx");
  assert.match(source, /onSelectLanguage:\s*\(lang:\s*Lang\)\s*=>\s*void/);
  assert.match(source, /onSelectLanguage\(["']hi["']\)/);
  assert.match(source, /onSelectLanguage\(["']en["']\)/);
  assert.match(source, /t\(["']language\.hindi["']\)/);
  assert.match(source, /t\(["']language\.english["']\)/);
  assert.equal((source.match(/accessibilityRole="button"/g) ?? []).length, 2);
  assert.equal((source.match(/accessibilityLabel=/g) ?? []).length, 2);
  assert.match(source, /accessibilityState=/);
  assert.match(source, /minHeight:\s*48/);
});

test("consent starts unselected and only accept invokes onAccept", () => {
  const source = readScreen("ConsentScreen.tsx");
  assert.match(source, /onAccept:\s*\(\)\s*=>\s*void/);
  assert.match(source, /onDecline:\s*\(\)\s*=>\s*void/);
  assert.match(source, /useState\(false\)/);
  assert.match(source, /onPress=\{onAccept\}/);
  assert.equal((source.match(/onAccept/g) ?? []).length, 3);
  const declineHandler = source.match(/function declineConsent\(\): void\s*\{([\s\S]*?)\}/);
  assert.ok(declineHandler, "decline handler is missing");
  assert.match(declineHandler[1], /setDeclined\(true\)/);
  assert.doesNotMatch(declineHandler[1], /onAccept/);
  assert.match(source, /onPress=\{declineConsent\}/);
  assert.match(source, /declined\s*\?\s*\([\s\S]*t\(["']consent\.declined_note["']\)/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onDecline\}\s*\/>/);
  assert.match(source, /<ScrollView\s+contentContainerStyle=\{\{\s*flexGrow:\s*1/);
  assert.equal((source.match(/accessibilityRole="button"/g) ?? []).length, 2);
  assert.match(source, /accessibilityState=\{\{\s*disabled:\s*false,\s*selected:\s*declined\s*\}\}/);
  assert.match(source, /minHeight:\s*48/);
});

test("home enables the human request while chat and requests remain disabled", () => {
  const source = readScreen("HomeScreen.tsx");
  assert.match(source, /onRequestHuman:\s*\(\)\s*=>\s*void/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onRequestHuman\}\s*\/>/);
  for (const key of ["home.chat", "home.my_requests"]) {
    assert.ok(source.includes(`"${key}"`), `${key} is missing`);
  }
  assert.doesNotMatch(source, /"home\.talk"/);
  assert.match(source, /accessibilityRole="button"/);
  assert.match(source, /accessibilityLabel=\{label\}/);
  assert.match(source, /accessibilityState=\{\{\s*disabled:\s*true\s*\}\}/);
  assert.match(source, /\sdisabled\s/);
  assert.match(source, /minHeight:\s*48/);
});
