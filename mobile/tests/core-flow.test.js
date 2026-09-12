/** Controlled MVP screen contracts. Runs with Node and no UI test dependency. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SCREENS = path.join(__dirname, "..", "src", "screens");
const readScreen = (name) => fs.readFileSync(path.join(SCREENS, name), "utf8");

test("language and home use flexible scroll-safe root layouts", () => {
  for (const screen of ["LanguageScreen.tsx", "HomeScreen.tsx"]) {
    const source = readScreen(screen);
    assert.match(source, /<SafeScreen>/);
    assert.match(source, /<ScrollView[\s\S]*flexGrow:\s*1/);
    assert.match(source, /backgroundColor:\s*theme\.colors\.canvas/);
  }
  const home = readScreen("HomeScreen.tsx");
  assert.ok(home.indexOf("<AiDisclosure />") < home.indexOf("<ScrollView"));
  assert.ok(home.indexOf("<PersistentFooter>") > home.indexOf("</ScrollView>"));
});

test("language offers balanced accessible Hindi and English controls", () => {
  const source = readScreen("LanguageScreen.tsx");
  assert.match(source, /onSelectLanguage\(["']hi["']\)/);
  assert.match(source, /onSelectLanguage\(["']en["']\)/);
  assert.equal((source.match(/accessibilityRole="button"/g) ?? []).length, 2);
  assert.match(source, /minHeight:\s*88/);
});

test("consent is asynchronous, synchronously locked, and retryable only after failure", () => {
  const source = readScreen("ConsentScreen.tsx");
  assert.match(source, /onAccept:\s*\(\)\s*=>\s*Promise<void>/);
  assert.match(source, /onDecline:\s*\(\)\s*=>\s*Promise<void>/);
  assert.match(source, /decisionStarted\s*=\s*useRef\(false\)/);
  assert.match(source, /if \(decisionStarted\.current\) return/);
  assert.match(source, /decisionStarted\.current = true/);
  assert.match(source, /await \(consent === "granted" \? onAccept\(\) : onDecline\(\)\)/);
  assert.match(source, /catch[\s\S]*decisionStarted\.current = false/);
  assert.match(source, /const disabled = pending \|\| declined/);
  assert.match(source, /accessibilityState=\{\{ disabled, selected: false \}\}/);
  assert.match(source, /onPress=\{\(\) => void decide\("granted"\)\}/);
  assert.match(source, /onPress=\{\(\) => void decide\("declined"\)\}/);
  assert.match(source, /failed[\s\S]*t\("error\.body"\)/);
});

test("consent remains scroll-safe and human contact remains visible", () => {
  const source = readScreen("ConsentScreen.tsx");
  assert.match(source, /<ScrollView\s+contentContainerStyle=\{\{\s*flexGrow:\s*1/);
  assert.match(source, /declined\s*\?\s*\([\s\S]*t\(["']consent\.declined_note["']\)/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onDecline\}\s*\/>/);
  assert.match(source, /minHeight:\s*theme\.size\.button/);
});

test("home enables Talk, Chat, My Requests, and human request", () => {
  const source = readScreen("HomeScreen.tsx");
  for (const callback of ["onOpenTalk", "onOpenChat", "onOpenRequests", "onRequestHuman"]) {
    assert.match(source, new RegExp(`${callback}:\\s*\\(\\)\\s*=>\\s*void`));
  }
  assert.match(source, /<PersistentFooter>[\s\S]*<TalkToPersonButton onPress=\{onRequestHuman\}/);
  assert.match(source, /minHeight:\s*168/);
  assert.match(source, /minHeight:\s*84/);
});
