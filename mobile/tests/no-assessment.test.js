/**
 * The victim app must never display any part of the assessment.
 *
 * mobile/CLAUDE.md: "There is a test asserting `svi`, `band` and `dimension`
 * do not appear in `mobile/src/`. Do not remove it."
 *
 * Telling a distressed person that a machine has rated them "Critical" is
 * harmful. The score exists for the executive. This app shows: you are heard,
 * this is your reference number, this is what happens next.
 *
 * Runs with the Node test runner and no installed dependency:
 *     node --test mobile/tests/
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SRC = path.join(__dirname, "..", "src");

/** Forbidden identifiers, matched on word boundaries in code (not in prose). */
const FORBIDDEN = [
  "svi",
  "band",
  "dimension",
  "dimensions",
  "dims",
  "needs_human",
  "emotion",
  "assessment",
  "alert",
  "severity",
  "recommendation",
  "confidence",
  "risk_score",
  "safesignal",
];

/**
 * Comments are stripped before scanning. The rule is about what the app can
 * render, and the files legitimately explain the rule in prose.
 */
function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/.*$/gm, "$1 ");
}

function sourceFiles(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...sourceFiles(full));
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) {
      found.push(full);
    }
  }
  return found;
}

test("mobile/src contains no assessment identifier", () => {
  const offences = [];

  for (const file of sourceFiles(SRC)) {
    const code = stripComments(fs.readFileSync(file, "utf8"));
    for (const term of FORBIDDEN) {
      const pattern = new RegExp(`\\b${term}\\b`, "i");
      if (pattern.test(code)) {
        offences.push(`${path.relative(SRC, file)}: ${term}`);
      }
    }
  }

  assert.deepEqual(
    offences,
    [],
    `assessment identifiers found in mobile/src:\n${offences.join("\n")}`,
  );
});

test("mobile/src never imports the console contract mirror", () => {
  const offences = [];
  for (const file of sourceFiles(SRC)) {
    const code = stripComments(fs.readFileSync(file, "utf8"));
    if (/from\s+["'][^"']*frontend[^"']*["']/.test(code)) {
      offences.push(path.relative(SRC, file));
    }
  }
  assert.deepEqual(offences, [], `mobile imported from frontend: ${offences.join(", ")}`);
});

test("the four victim events are the only ones the app knows about", () => {
  const events = fs.readFileSync(path.join(SRC, "types", "events.ts"), "utf8");
  const match = events.match(/ALLOWED_EVENT_TYPES\s*=\s*\[([\s\S]*?)\]/);
  assert.ok(match, "ALLOWED_EVENT_TYPES is missing from src/types/events.ts");

  const listed = [...match[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(listed, [
    "assistant.turn",
    "session.status",
    "timeline.update",
    "transcript.line",
  ]);
});
