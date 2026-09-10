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
  assert.match(source, /<ConsentScreen\s+onAccept=\{\(\)\s*=>\s*router\.replace\(["']\/home["']\)\}/);
});

test("home renders the home screen", () => {
  assert.match(read("app", "home.tsx"), /return\s+<HomeScreen\s*\/>/);
});
