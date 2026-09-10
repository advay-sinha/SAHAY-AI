/**
 * Every user-visible string exists in both Hindi and English.
 *
 * A missing key means a distressed user sees a raw key or English text on a
 * Hindi screen. Runs with no installed dependency:
 *     node --test mobile/tests/
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const I18N = path.join(__dirname, "..", "src", "i18n");

function load(name) {
  return JSON.parse(fs.readFileSync(path.join(I18N, name), "utf8"));
}

test("hi and en carry the same keys", () => {
  const hi = load("hi.json");
  const en = load("en.json");
  assert.deepEqual(Object.keys(hi).sort(), Object.keys(en).sort());
});

test("no string is empty in either language", () => {
  for (const name of ["hi.json", "en.json"]) {
    const bundle = load(name);
    for (const [key, value] of Object.entries(bundle)) {
      assert.ok(String(value).trim().length > 0, `${name}: ${key} is empty`);
    }
  }
});

test("the AI disclosure and the human-request strings exist in both languages", () => {
  const required = [
    "consent.ai_disclosure",
    "consent.human_review",
    "consent.right_to_human",
    "disclosure.persistent",
    "human.button",
  ];
  for (const name of ["hi.json", "en.json"]) {
    const bundle = load(name);
    for (const key of required) {
      assert.ok(key in bundle, `${name} is missing ${key}`);
    }
  }
});

test("declining consent still promises a route to a person", () => {
  for (const name of ["hi.json", "en.json"]) {
    assert.ok(load(name)["consent.declined_note"], `${name} is missing consent.declined_note`);
  }
});
