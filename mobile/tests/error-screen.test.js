/** Dependency-free ErrorScreen contracts. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { createErrorActions } = require("../src/screens/errorActions");

const MOBILE = path.join(__dirname, "..");
const source = fs.readFileSync(path.join(MOBILE, "src", "screens", "ErrorScreen.tsx"), "utf8");
const actionsSource = fs.readFileSync(
  path.join(MOBILE, "src", "screens", "errorActions.js"),
  "utf8",
);

test("ErrorScreen replaces its placeholder with only existing localized error copy", () => {
  assert.doesNotMatch(source, /<Text[^>]*>\s*ErrorScreen\s*<\/Text>/);
  assert.doesNotMatch(source, /scaffold|placeholder/i);

  const visibleKeys = [...source.matchAll(/t\(["']([^"']+)["']\)/g)].map((match) => match[1]);
  assert.deepEqual(new Set(visibleKeys), new Set(["error.title", "error.body", "error.retry"]));

  for (const locale of ["en", "hi"]) {
    const messages = JSON.parse(
      fs.readFileSync(path.join(MOBILE, "src", "i18n", `${locale}.json`), "utf8"),
    );
    for (const key of new Set(visibleKeys)) {
      assert.equal(typeof messages[key], "string", `${locale} is missing ${key}`);
      assert.ok(messages[key].length > 0, `${locale}:${key} is empty`);
    }
  }

  assert.doesNotMatch(source, />\s*[A-Za-z][^<{\n]*\s*</);
});

test("retry invokes only its injected callback exactly once", () => {
  const calls = [];
  const actions = createErrorActions({
    onRequestHuman: () => calls.push("human"),
    onRetry: () => calls.push("retry"),
  });

  assert.equal(actions.retry(), undefined);
  assert.deepEqual(calls, ["retry"]);
});

test("human contact invokes only its injected callback exactly once", () => {
  const calls = [];
  const actions = createErrorActions({
    onRequestHuman: () => calls.push("human"),
    onRetry: () => calls.push("retry"),
  });

  assert.equal(actions.requestHuman(), undefined);
  assert.deepEqual(calls, ["human"]);
});

test("ErrorScreen uses the executable actions without internal side effects", () => {
  assert.match(source, /onRetry:\s*\(\)\s*=>\s*void/);
  assert.match(source, /onRequestHuman:\s*\(\)\s*=>\s*void/);
  assert.match(source, /createErrorActions\(\{\s*onRequestHuman,\s*onRetry\s*\}\)/);
  assert.match(source, /<Pressable[\s\S]*?onPress=\{retry\}[\s\S]*?>/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{requestHuman\}\s*\/>/);
  assert.equal((source.match(/onRetry/g) ?? []).length, 3);
  assert.equal((source.match(/onRequestHuman/g) ?? []).length, 3);
  assert.doesNotMatch(
    `${source}\n${actionsSource}`,
    /fetch\(|axios|AsyncStorage|localStorage|sessionStorage|useEffect|useState|Promise|navigation\.|success/i,
  );
});

test("disclosure and human contact stay visible outside the scrolling error content", () => {
  const disclosure = source.indexOf("<AiDisclosure />");
  const scrollStart = source.indexOf("<ScrollView");
  const scrollEnd = source.indexOf("</ScrollView>");
  const humanContact = source.indexOf("<TalkToPersonButton onPress={requestHuman} />");

  assert.ok(disclosure >= 0 && disclosure < scrollStart);
  assert.ok(scrollStart >= 0 && scrollEnd > scrollStart);
  assert.ok(humanContact > scrollEnd);
});

test("error content is large-font scroll-safe without disabling font scaling", () => {
  assert.match(source, /<ScrollView[\s\S]*contentContainerStyle=\{\{\s*flexGrow:\s*1/);
  assert.match(source, /<ScrollView[\s\S]*style=\{\{\s*flex:\s*1\s*\}\}/);
  assert.equal((source.match(/<Text\b/g) ?? []).length, 3);
  assert.equal((source.match(/allowFontScaling/g) ?? []).length, 3);
  assert.doesNotMatch(source, /allowFontScaling=\{false\}|maxFontSizeMultiplier/);
});

test("retry is an accessible button with a minimum 48px touch target", () => {
  const retryButton = source.match(/<Pressable([\s\S]*?)<\/Pressable>/);
  assert.ok(retryButton, "retry button is missing");
  assert.match(retryButton[1], /accessibilityLabel=\{t\(["']error\.retry["']\)\}/);
  assert.match(retryButton[1], /accessibilityRole="button"/);
  assert.match(retryButton[1], /minHeight:\s*theme\.size\.button/);
  assert.match(source, /accessibilityRole="header"/);
});

test("error reassurance panel and persistent footer are compositionally separated", () => {
  assert.match(source, /<SurfaceCard elevated tone="recessed"/);
  assert.match(source, /minHeight:\s*280/);
  assert.ok(source.indexOf("<PersistentFooter>") > source.indexOf("</ScrollView>"));
  assert.match(source, /pattern="shield" size=\{72\} tone="danger"/);
});
