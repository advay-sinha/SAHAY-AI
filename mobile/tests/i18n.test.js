/**
 * Every user-visible string exists in both Hindi and English.
 *
 * A missing key means a distressed user sees a raw key or English text on a
 * Hindi screen. Runs with no installed dependency:
 *     node --test mobile/tests/
 */

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const I18N = path.join(__dirname, "..", "src", "i18n");
const SRC = path.join(__dirname, "..", "src");

function load(name) {
  return JSON.parse(fs.readFileSync(path.join(I18N, name), "utf8"));
}

function directTranslationKeys(source) {
  return [...source.matchAll(/\bt\(\s*(["'])([^"']+)\1\s*\)/g)].map((match) => match[2]);
}

function productionSourceFiles(directory = SRC) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return productionSourceFiles(target);
    return /\.tsx?$/.test(entry.name) ? [target] : [];
  });
}

function executeTranslation(language, key) {
  const source = fs.readFileSync(path.join(I18N, "index.ts"), "utf8");
  const implementation = source.match(
    /export function t\(key: string\): string \{([\s\S]*?)\r?\n\}/,
  );
  assert.ok(implementation, "could not load the translation function");
  return new Function("BUNDLES", "current", "key", implementation[1])(
    { en: load("en.json"), hi: load("hi.json") },
    language,
    key,
  );
}

function valueDigest(bundle) {
  const stableEntries = Object.entries(bundle).sort(([left], [right]) => left.localeCompare(right));
  return crypto.createHash("sha256").update(JSON.stringify(stableEntries)).digest("hex");
}

test("hi and en carry the same keys", () => {
  const hi = load("hi.json");
  const en = load("en.json");
  assert.deepEqual(Object.keys(hi).sort(), Object.keys(en).sort());
});

test("approved locale values remain unchanged", () => {
  assert.equal(
    valueDigest(load("en.json")),
    "eebbc46dd5da033d8acd989faf0e9f8aa8d92066a1e34a62c81bbab5ab010982",
  );
  assert.equal(
    valueDigest(load("hi.json")),
    "b0753895b02ddbbe21f2ff437b993f96656c75932f506ef06dc9d1532a96edab",
  );
});

test("AiDisclosure uses the approved persistent-disclosure key in both locales", () => {
  const source = fs.readFileSync(path.join(SRC, "components", "AiDisclosure.tsx"), "utf8");
  const keys = directTranslationKeys(source);
  assert.deepEqual(keys, ["disclosure.persistent"]);

  for (const name of ["en.json", "hi.json"]) {
    const bundle = load(name);
    for (const key of keys) assert.ok(key in bundle, `${name} is missing ${key}`);
  }
});

test("persistent disclosure translates to its approved text instead of a raw key", () => {
  const expected = {
    en: "AI assistant \u00b7 a person reviews everything",
    hi: "\u090f\u0906\u0908 \u0938\u0939\u093e\u092f\u0915 \u00b7 \u090f\u0915 \u0935\u094d\u092f\u0915\u094d\u0924\u093f \u0938\u092c \u0915\u0941\u091b \u0926\u0947\u0916\u0924\u093e \u0939\u0948",
  };

  for (const language of ["en", "hi"]) {
    const translated = executeTranslation(language, "disclosure.persistent");
    assert.equal(translated, expected[language]);
    assert.notEqual(translated, "disclosure.persistent");
  }
});

test("every direct production translation lookup exists in both locales", () => {
  const bundles = { en: load("en.json"), hi: load("hi.json") };
  for (const file of productionSourceFiles()) {
    const source = fs.readFileSync(file, "utf8");
    assert.doesNotMatch(source, /ai\.disclosure\.persistent/);
    for (const key of directTranslationKeys(source)) {
      for (const language of ["en", "hi"]) {
        assert.ok(key in bundles[language], `${path.relative(SRC, file)}: ${language} is missing ${key}`);
      }
    }
  }
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
      "timeline.loading": "Loading request\u2026",
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
  assert.equal(load("en.json")["timeline.loading"].codePointAt(15), 0x2026);
  assert.equal(load("en.json")["timeline.loading"].length, 16);
  assert.doesNotMatch(load("en.json")["timeline.loading"], /\.\.\./);

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

test("the rendered loading presentation shows the exact approved text in both languages", () => {
  const { selectMyRequestsPresentation } = require("../src/screens/myRequestsState");
  assert.deepEqual(selectMyRequestsPresentation("loading"), { kind: "loading" });

  const screen = fs.readFileSync(path.join(SRC, "screens", "MyRequestsScreen.tsx"), "utf8");
  const block = screen.match(/\{presentation\.kind === "loading" \? \(([\s\S]*?)\) : null\}/);
  assert.ok(block, "loading presentation branch is missing");
  // The branch renders one key, as both its visible text and its accessible label.
  assert.deepEqual(directTranslationKeys(block[1]), ["timeline.loading", "timeline.loading"]);
  assert.match(block[1], /accessibilityLabel=\{t\("timeline\.loading"\)\}/);
  assert.match(block[1], />\s*\{t\("timeline\.loading"\)\}\s*</);

  const approved = {
    en: "Loading request…",
    hi: "अनुरोध लोड हो रहा है…",
  };
  for (const language of ["en", "hi"]) {
    assert.equal(executeTranslation(language, "timeline.loading"), approved[language], language);
  }
});
