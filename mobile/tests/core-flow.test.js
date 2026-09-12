/** Slice 1 screen contracts. Runs with Node and no installed dependency. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SCREENS = path.join(__dirname, "..", "src", "screens");
const readScreen = (name) => fs.readFileSync(path.join(SCREENS, name), "utf8");

function executableConsentHandlers(source) {
  const body = (name) => {
    const match = source.match(new RegExp(`function ${name}\\(\\): void\\s*\\{([^{}]*)\\}`));
    assert.ok(match, `${name} is missing or is not dependency-free`);
    return match[1];
  };
  const compile = (name) => new Function(
    "decisionStarted",
    "setDeclined",
    "onAccept",
    "onDecline",
    body(name),
  );
  return {
    accept: compile("acceptConsent"),
    decline: compile("declineConsent"),
  };
}

function acceptDisabledPresentation(source, declined) {
  const block = source.match(
    /<Pressable\s+[\s\S]*?accessibilityLabel=\{t\(["']consent\.accept["']\)\}([\s\S]*?)<\/Pressable>/,
  );
  assert.ok(block, "accept control is missing");

  const disabled = block[1].match(/\bdisabled=\{([^}]+)\}/);
  const accessibilityDisabled = block[1].match(
    /accessibilityState=\{\{\s*disabled:\s*([^,}]+)/,
  );
  assert.ok(disabled, "accept control has no disabled property");
  assert.ok(accessibilityDisabled, "accept control has no accessible disabled state");

  const evaluate = (expression) => new Function("declined", `return (${expression});`)(declined);
  return {
    accessibilityDisabled: evaluate(accessibilityDisabled[1]),
    disabled: evaluate(disabled[1]),
  };
}

test("language and home use flexible scroll-safe root layouts", () => {
  for (const screen of ["LanguageScreen.tsx", "HomeScreen.tsx"]) {
    const source = readScreen(screen);
    assert.match(source, /<SafeScreen>/);
    assert.match(source, /<ScrollView[\s\S]*contentContainerStyle=\{\{[\s\S]*?flexGrow:\s*1/);
    assert.match(source, /style=\{\{\s*flex:\s*1\s*\}\}/);
    assert.match(source, /backgroundColor:\s*theme\.colors\.canvas/);
  }
  const home = readScreen("HomeScreen.tsx");
  assert.ok(home.indexOf("<AiDisclosure />") < home.indexOf("<ScrollView"));
  assert.ok(home.indexOf("<PersistentFooter>") > home.indexOf("</ScrollView>"));
});

test("language offers balanced accessible Hindi and English controls", () => {
  const source = readScreen("LanguageScreen.tsx");
  assert.match(source, /onSelectLanguage:\s*\(lang:\s*Lang\)\s*=>\s*void/);
  assert.match(source, /onSelectLanguage\(["']hi["']\)/);
  assert.match(source, /onSelectLanguage\(["']en["']\)/);
  assert.match(source, /t\(["']language\.hindi["']\)/);
  assert.match(source, /t\(["']language\.english["']\)/);
  assert.equal((source.match(/accessibilityRole="button"/g) ?? []).length, 2);
  assert.equal((source.match(/accessibilityLabel=/g) ?? []).length, 2);
  assert.match(source, /accessibilityState=/);
  assert.match(source, /minHeight:\s*88/);
  assert.equal((source.match(/height:\s*28,\s*width:\s*28/g) ?? []).length, 2);
});

test("consent starts undecided with either choice available", () => {
  const source = readScreen("ConsentScreen.tsx");
  assert.match(source, /onAccept:\s*\(\)\s*=>\s*void/);
  assert.match(source, /onDecline:\s*\(\)\s*=>\s*void/);
  assert.match(source, /useState\(false\)/);
  assert.match(source, /decisionStarted\s*=\s*useRef\(false\)/);
  assert.match(source, /onPress=\{acceptConsent\}/);
  assert.equal((source.match(/onAccept/g) ?? []).length, 3);
  assert.deepEqual(acceptDisabledPresentation(source, false), {
    accessibilityDisabled: false,
    disabled: false,
  });
  assert.match(source, /accessibilityState=\{\{\s*disabled:\s*declined,\s*selected:\s*false\s*\}\}/);
  assert.match(source, /onPress=\{declineConsent\}/);
  assert.match(source, /declined\s*\?\s*\([\s\S]*t\(["']consent\.declined_note["']\)/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onDecline\}\s*\/>/);
  assert.match(source, /<ScrollView\s+contentContainerStyle=\{\{\s*flexGrow:\s*1/);
  assert.equal((source.match(/accessibilityRole="button"/g) ?? []).length, 2);
  assert.match(source, /accessibilityState=\{\{\s*disabled:\s*declined,\s*selected:\s*declined\s*\}\}/);
  assert.match(source, /disabled=\{declined\}/);
  assert.match(source, /minHeight:\s*theme\.size\.button/);
  assert.match(source, /<SurfaceCard elevated tone="navy"/);
  assert.equal((source.match(/\["consent\.[^"]+",/g) ?? []).length, 4);
});

test("decline then accept invokes only decline", () => {
  const handlers = executableConsentHandlers(readScreen("ConsentScreen.tsx"));
  const decisionStarted = { current: false };
  let declineCalls = 0;
  let acceptCalls = 0;
  let selectedCalls = 0;

  const args = [
    decisionStarted,
    () => { selectedCalls += 1; },
    () => { acceptCalls += 1; },
    () => { declineCalls += 1; },
  ];
  handlers.decline(...args);
  handlers.accept(...args);

  assert.equal(declineCalls, 1);
  assert.equal(acceptCalls, 0);
  assert.equal(selectedCalls, 1);
});

test("accept then decline invokes only accept", () => {
  const handlers = executableConsentHandlers(readScreen("ConsentScreen.tsx"));
  const decisionStarted = { current: false };
  let declineCalls = 0;
  let acceptCalls = 0;

  const args = [
    decisionStarted,
    () => assert.fail("accept selected decline"),
    () => { acceptCalls += 1; },
    () => { declineCalls += 1; },
  ];
  handlers.accept(...args);
  handlers.decline(...args);

  assert.equal(acceptCalls, 1);
  assert.equal(declineCalls, 0);
});

test("repeated accept presses invoke acceptance once", () => {
  const handlers = executableConsentHandlers(readScreen("ConsentScreen.tsx"));
  const decisionStarted = { current: false };
  let acceptCalls = 0;
  const args = [
    decisionStarted,
    () => assert.fail("accept selected decline"),
    () => { acceptCalls += 1; },
    () => assert.fail("accept invoked decline"),
  ];

  handlers.accept(...args);
  handlers.accept(...args);

  assert.equal(acceptCalls, 1);
});

test("repeated decline presses invoke decline once", () => {
  const handlers = executableConsentHandlers(readScreen("ConsentScreen.tsx"));
  const decisionStarted = { current: false };
  let declineCalls = 0;
  let selectedCalls = 0;
  const args = [
    decisionStarted,
    () => { selectedCalls += 1; },
    () => assert.fail("decline invoked acceptance"),
    () => { declineCalls += 1; },
  ];

  handlers.decline(...args);
  handlers.decline(...args);

  assert.equal(declineCalls, 1);
  assert.equal(selectedCalls, 1);
});

test("accept is rendered disabled after decline", () => {
  const source = readScreen("ConsentScreen.tsx");
  assert.deepEqual(acceptDisabledPresentation(source, true), {
    accessibilityDisabled: true,
    disabled: true,
  });
});

test("home enables Talk, Chat, My Requests, and the human request", () => {
  const source = readScreen("HomeScreen.tsx");
  assert.match(source, /onOpenChat:\s*\(\)\s*=>\s*void/);
  assert.match(source, /onOpenTalk:\s*\(\)\s*=>\s*void/);
  assert.match(source, /onRequestHuman:\s*\(\)\s*=>\s*void/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onRequestHuman\}\s*\/>/);
  assert.match(source, /t\(["']home\.talk["']\)/);
  assert.match(source, /onPress=\{onOpenTalk\}/);
  assert.match(source, /t\(["']home\.chat["']\)/);
  assert.match(source, /onPress=\{onOpenChat\}/);
  assert.match(source, /accessibilityState=\{\{\s*disabled:\s*false\s*\}\}/);
  assert.match(source, /t\(["']home\.my_requests["']\)/);
  assert.match(source, /onOpenRequests:\s*\(\)\s*=>\s*void/);
  assert.match(source, /onPress=\{onOpenRequests\}/);
  assert.equal((source.match(/accessibilityState=\{\{\s*disabled:\s*false\s*\}\}/g) ?? []).length, 3);
  assert.match(source, /accessibilityRole="button"/);
  assert.match(source, /minHeight:\s*168/);
  assert.match(source, /minHeight:\s*84/);
  assert.match(source, /<PersistentFooter>[\s\S]*<TalkToPersonButton onPress=\{onRequestHuman\}/);
});
