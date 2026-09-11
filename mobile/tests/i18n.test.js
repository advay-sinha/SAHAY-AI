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

test("chat state and origin labels match the approved translations", () => {
  const expected = {
    en: {
      "chat.pending": "Sending",
      "chat.sent": "Sent",
      "chat.assistant": "SAHAY-AI Assistant",
      "chat.human_officer": "Human Support Officer",
    },
    hi: {
      "chat.pending": "\u092D\u0947\u091C\u093E \u091C\u093E \u0930\u0939\u093E \u0939\u0948\u2026",
      "chat.sent": "\u092D\u0947\u091C \u0926\u093F\u092F\u093E \u0917\u092F\u093E",
      "chat.assistant": "SAHAY-AI \u0938\u0939\u093E\u092F\u0915",
      "chat.human_officer": "\u092E\u093E\u0928\u0935 \u0938\u0939\u093E\u092F\u0924\u093E \u0905\u0927\u093F\u0915\u093E\u0930\u0940",
    },
  };
  const hindiLengths = {
    "chat.pending": 15,
    "chat.sent": 12,
    "chat.assistant": 14,
    "chat.human_officer": 19,
  };

  for (const language of ["en", "hi"]) {
    const bundle = load(`${language}.json`);
    for (const [key, value] of Object.entries(expected[language])) {
      assert.equal(bundle[key], value, `${language}:${key}`);
      if (language === "hi") {
        assert.equal(bundle[key].length, hindiLengths[key], `${language}:${key}:length`);
      }
    }
  }
});

test("My Requests state labels match the approved translations", () => {
  const expected = {
    en: {
      "timeline.empty": "No requests yet",
      "timeline.loading": "Loading request",
    },
    hi: {
      "timeline.empty": "\u0905\u092D\u0940 \u0915\u094B\u0908 \u0905\u0928\u0941\u0930\u094B\u0927 \u0928\u0939\u0940\u0902 \u0939\u0948",
      "timeline.loading": "\u0905\u0928\u0941\u0930\u094B\u0927 \u0932\u094B\u0921 \u0939\u094B \u0930\u0939\u093E \u0939\u0948\u2026",
    },
  };
  const hindiLengths = {
    "timeline.empty": 22,
    "timeline.loading": 21,
  };

  for (const language of ["en", "hi"]) {
    const bundle = load(`${language}.json`);
    for (const [key, value] of Object.entries(expected[language])) {
      assert.equal(bundle[key], value, `${language}:${key}`);
      if (language === "hi") {
        assert.equal(bundle[key].length, hindiLengths[key], `${language}:${key}:length`);
      }
    }
  }
});
