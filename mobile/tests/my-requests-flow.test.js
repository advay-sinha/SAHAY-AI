const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { selectMyRequestsPresentation } = require("../src/screens/myRequestsState");

const MOBILE = path.join(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(MOBILE, ...parts), "utf8");

function payload(entries = []) {
  return { reference: "SAH-2026-00000001", timeline: entries };
}

test("loading, unavailable, failed, and successful empty states stay distinct", () => {
  assert.deepEqual(selectMyRequestsPresentation("loading"), { kind: "loading" });
  assert.deepEqual(selectMyRequestsPresentation("unavailable"), { kind: "unavailable" });
  assert.deepEqual(selectMyRequestsPresentation("failed"), { kind: "failed" });
  assert.deepEqual(selectMyRequestsPresentation("ready", payload()), { kind: "empty" });
  assert.deepEqual(selectMyRequestsPresentation("ready"), { kind: "failed" });
});

test("a valid single timeline preserves server order, duplicates, labels, and input", () => {
  const value = payload([
    { stage: "under_review", label: "Later server label", ts: "2026-09-11T11:00:00Z" },
    { stage: "request_received", label: "Earlier server label", ts: "2026-09-11T10:00:00Z" },
    { stage: "request_received", label: "Earlier server label", ts: "2026-09-11T10:00:00Z" },
    { stage: "action_taken", label: "Human-confirmed server label", ts: "2026-09-11T12:00:00Z" },
  ]);
  const before = structuredClone(value);

  assert.deepEqual(selectMyRequestsPresentation("ready", value), {
    kind: "timeline",
    reference: "SAH-2026-00000001",
    entries: [
      { stage: "under_review", label: "Later server label" },
      { stage: "request_received", label: "Earlier server label" },
      { stage: "request_received", label: "Earlier server label" },
      { stage: "action_taken", label: "Human-confirmed server label" },
    ],
  });
  assert.deepEqual(value, before);
});

test("long timelines retain every entry for the scrollable presentation", () => {
  const entries = Array.from({ length: 250 }, (_, index) => ({
    stage: index % 2 === 0 ? "request_received" : "under_review",
    label: `Server label ${index}`,
    ts: `Server timestamp ${250 - index}`,
  }));

  const presentation = selectMyRequestsPresentation("ready", payload(entries));

  assert.equal(presentation.kind, "timeline");
  assert.equal(presentation.entries.length, entries.length);
  assert.deepEqual(
    presentation.entries.map((entry) => entry.label),
    entries.map((entry) => entry.label),
  );
  assert.ok(presentation.entries.every((entry) => !("ts" in entry)));
});

test("the selector accepts one exact payload, not a list or unexpected data", () => {
  const exact = payload([
    { stage: "request_received", label: "Server label", ts: "time" },
  ]);

  assert.equal(selectMyRequestsPresentation("ready", [exact]).kind, "failed");
  assert.equal(
    selectMyRequestsPresentation("ready", { ...exact, unexpected: true }).kind,
    "failed",
  );
  assert.equal(
    selectMyRequestsPresentation("ready", payload([
      { stage: "unknown", label: "Server label", ts: "time" },
    ])).kind,
    "failed",
  );
});

test("action_taken is never synthesized", () => {
  const presentation = selectMyRequestsPresentation("ready", payload([
    { stage: "officer_assigned", label: "Server label", ts: "time" },
  ]));

  assert.equal(presentation.kind, "timeline");
  assert.deepEqual(presentation.entries.map((entry) => entry.stage), ["officer_assigned"]);
});

test("MyRequestsScreen keeps disclosure and handoff outside its scrollable timeline", () => {
  const source = read("src", "screens", "MyRequestsScreen.tsx");
  const scrollStart = source.indexOf("<ScrollView");
  const scrollEnd = source.indexOf("</ScrollView>");
  const disclosure = source.indexOf("<AiDisclosure />");
  const entries = source.indexOf("presentation.entries.map");
  const handoff = source.indexOf("<TalkToPersonButton onPress={onRequestHuman} />");

  assert.ok(scrollStart >= 0 && scrollEnd > scrollStart, "inner timeline ScrollView is missing");
  assert.ok(disclosure >= 0 && disclosure < scrollStart, "AI disclosure is not persistent");
  assert.ok(entries > scrollStart && entries < scrollEnd, "long timeline content is not scrollable");
  assert.ok(handoff > scrollEnd, "human-contact control can be buried by the timeline");
  assert.match(source, /<View style=\{\{ flex: 1, gap: 16, padding: 16, backgroundColor: theme\.colors\.canvas \}\}>/);
  assert.match(source, /<ScrollView[\s\S]*style=\{\{ flex: 1 \}\}/);
});

test("MyRequestsScreen is localized, accessible, and omits timestamps", () => {
  const source = read("src", "screens", "MyRequestsScreen.tsx");
  for (const key of [
    "timeline.title",
    "timeline.reference",
    "timeline.loading",
    "timeline.empty",
    "error.title",
    "error.body",
    "error.retry",
  ]) {
    assert.ok(source.includes(`"${key}"`), `${key} is missing`);
  }
  assert.match(source, /<ScrollView/);
  assert.match(source, /accessibilityLabel=/);
  assert.match(source, /accessibilityRole="button"/);
  assert.match(source, /accessibilityState=/);
  assert.match(source, /minHeight:\s*theme\.size\.button/);
  assert.match(source, /allowFontScaling/);
  assert.match(source, /<AiDisclosure\s*\/>/);
  assert.match(source, /<TalkToPersonButton\s+onPress=\{onRequestHuman\}\s*\/>/);
  assert.doesNotMatch(source, /\.sort\(|\.reverse\(|\.ts\b/);
});

test("timeline renders a connected geometric rail inside one grouped card", () => {
  const source = read("src", "screens", "MyRequestsScreen.tsx");
  assert.match(source, /<SurfaceCard style=\{\{ padding: theme\.space\.lg \}\}>[\s\S]*presentation\.entries\.map/);
  assert.match(source, /index < presentation\.entries\.length - 1/);
  assert.match(source, /backgroundColor:\s*theme\.colors\.border, flex:\s*1, width:\s*2/);
  assert.match(source, /importantForAccessibility="no-hide-descendants"/);
  assert.ok(source.indexOf("<PersistentFooter>") > source.indexOf("</ScrollView>"));
});
