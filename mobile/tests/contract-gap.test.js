/**
 * Mobile contract gap tests (lead decisions of 2026-09-11).
 *
 *   1. The mobile allowlist matches the approved contract
 *      (docs/contracts/CONTRACTS.md section 2) and the backend allowlist
 *      (backend/app/ws/events.py VICTIM_ALLOWED): all three agree.
 *   2. Mobile cannot import console types (frontend/, contracts.ts, packet.ts).
 *   3. No assessment field can be declared in any victim event shape.
 *   4. PC-07 officer.message is typed as human-officer origin only, and the
 *      backend allows it only after a verified takeover (the server check is
 *      tested in backend/tests/test_contract_decisions.py; here we assert the
 *      guard is present in the one service that publishes it).
 *
 * Node test runner, no installed dependency:
 *     node --test mobile/tests/
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const REPO = path.join(__dirname, "..", "..");
const SRC = path.join(__dirname, "..", "src");
const read = (...p) => fs.readFileSync(path.join(REPO, ...p), "utf8");

const EVENTS_TS = read("mobile", "src", "types", "events.ts");

function mobileAllowlist() {
  const m = EVENTS_TS.match(/ALLOWED_EVENT_TYPES\s*=\s*\[([\s\S]*?)\]/);
  assert.ok(m, "ALLOWED_EVENT_TYPES missing");
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort();
}

function backendAllowlist() {
  const py = read("backend", "app", "ws", "events.py");
  const m = py.match(/VICTIM_ALLOWED[^=]*=\s*frozenset\(\s*\{([\s\S]*?)\}\s*\)/);
  assert.ok(m, "VICTIM_ALLOWED missing from backend/app/ws/events.py");
  const body = m[1].replace(/#.*$/gm, "");
  return [...body.matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort();
}

function contractSection2() {
  const doc = read("docs", "contracts", "CONTRACTS.md");
  const m = doc.match(/^## 2\.[\s\S]*?(?=^## 3\.)/m);
  assert.ok(m, "CONTRACTS.md section 2 missing");
  return [...m[0].matchAll(/^([a-z]+\.[a-z_]+)\s/gm)].map((x) => x[1]).sort();
}

function sourceFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(ts|tsx|js|jsx)$/.test(e.name)) out.push(full);
  }
  return out;
}

test("mobile allowlist == backend allowlist == CONTRACTS.md section 2", () => {
  const mobile = mobileAllowlist();
  assert.deepEqual(mobile, backendAllowlist());
  assert.deepEqual(mobile, contractSection2());
});

test("the VictimEvent union names exactly the allowlisted events", () => {
  const union = EVENTS_TS.match(/export type VictimEvent\s*=([\s\S]*?);/);
  assert.ok(union);
  const names = [...union[1].matchAll(/type:\s*"([^"]+)"/g)].map((x) => x[1]).sort();
  assert.deepEqual(names, mobileAllowlist());
});

test("mobile never imports console types", () => {
  const offences = [];
  for (const file of sourceFiles(SRC)) {
    const code = fs.readFileSync(file, "utf8");
    for (const m of code.matchAll(/(?:from|import|require)\s*\(?\s*["']([^"']+)["']/g)) {
      const spec = m[1];
      if (/frontend|types\/contracts|types\/packet|console/.test(spec)) {
        offences.push(`${path.relative(SRC, file)} -> ${spec}`);
      }
    }
  }
  assert.deepEqual(offences, []);
});

test("no victim event shape declares an assessment field", () => {
  const FORBIDDEN = ["svi", "band", "dims", "dimension", "needs_human", "confidence", "conf",
    "severity", "alert", "alert_type", "emotion", "recommendation", "evidence_turn_ids",
    "overrides_applied", "breakdown", "risk", "priority"];
  const fields = [...EVENTS_TS.matchAll(/^\s+([a-z_]+)\??:/gm)].map((x) => x[1]);
  assert.ok(fields.length > 0);
  for (const f of fields) assert.ok(!FORBIDDEN.includes(f), `victim event field ${f} is an assessment field`);
});

test("officer.message is typed as human-officer origin only", () => {
  const m = EVENTS_TS.match(/export interface OfficerMessage\s*\{([\s\S]*?)\}/);
  assert.ok(m, "OfficerMessage type missing");
  assert.match(m[1], /origin:\s*"human_officer";/);
  const fields = [...m[1].matchAll(/^\s+([a-z_]+)\??:/gm)].map((x) => x[1]).sort();
  assert.deepEqual(fields, ["lang", "origin", "text", "ts", "turn_id"]);
});

test("the backend publishes officer.message only behind a verified takeover", () => {
  const svc = read("backend", "app", "services", "casework.py");
  const fn = svc.match(/async def officer_message\([\s\S]*?(?=\nasync def |\ndef |$)/);
  assert.ok(fn, "officer_message service missing");
  const body = fn[0];
  const guard = body.indexOf('case.status != "taken_over"');
  const human = body.indexOf("session.human_joined_at is None");
  const publish = body.indexOf('out.add("officer.message"');
  assert.ok(guard > 0 && human > 0, "takeover guard missing");
  assert.ok(publish > guard && publish > human, "officer.message is published before the takeover guard");
  assert.match(body, /_require_owner\(case, officer_id\)/);
});

test("every frozen timeline stage has an en and hi label, and no retired stage remains", () => {
  const doc = read("docs", "contracts", "CONTRACTS.md");
  const line = doc.match(/^timeline_stage\s{2,}(.+)$/m);
  assert.ok(line, "timeline_stage enum missing from CONTRACTS.md section 9");
  const stages = line[1].split("|").map((s) => s.trim()).sort();
  for (const lang of ["en", "hi"]) {
    const strings = JSON.parse(read("mobile", "src", "i18n", `${lang}.json`));
    const keys = Object.keys(strings)
      .filter((k) => k.startsWith("timeline.") && ![
        "timeline.title",
        "timeline.reference",
        "timeline.empty",
        "timeline.loading",
      ].includes(k))
      .map((k) => k.slice("timeline.".length))
      .sort();
    assert.deepEqual(keys, stages, `${lang}.json timeline labels`);
  }
});
