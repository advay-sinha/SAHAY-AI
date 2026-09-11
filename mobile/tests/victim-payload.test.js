const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  CONSENT_STATUSES,
  EVENT_TYPES,
  SESSION_STATES,
  TIMELINE_STAGES,
  dispatchVictimEvent,
  parseVictimEvent,
  validateVictimEvent,
  validateVictimTimeline,
} = require("../src/net/victimPayload");

const VALID_EVENTS = {
  "assistant.turn": {
    type: "assistant.turn",
    turn_id: "turn-1",
    text: "text",
    lang: "hi",
    intent: "acknowledge",
    audio: "streaming",
  },
  "transcript.line": {
    type: "transcript.line",
    turn_id: "turn-2",
    speaker: "victim",
    text: "text",
    lang: "en",
    ts: "2026-09-11T10:00:00Z",
  },
  "session.status": {
    type: "session.status",
    state: "S3",
    consent: "granted",
    lang: "hi",
    human_joined: false,
  },
  "timeline.update": {
    type: "timeline.update",
    stage: "under_review",
    label: "label",
    ts: "2026-09-11T10:01:00Z",
  },
  "officer.message": {
    type: "officer.message",
    turn_id: "turn-3",
    text: "text",
    lang: "en",
    ts: "2026-09-11T10:02:00Z",
    origin: "human_officer",
  },
};

for (const [name, event] of Object.entries(VALID_EVENTS)) {
  test(`accepts the exact ${name} event`, () => {
    assert.deepEqual(validateVictimEvent(event), event);
    assert.deepEqual(parseVictimEvent(JSON.stringify(event)), event);
  });
}

test("runtime event names match the protected mirror", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "types", "events.ts"), "utf8");
  const match = source.match(/ALLOWED_EVENT_TYPES\s*=\s*\[([\s\S]*?)\]/);
  assert.ok(match);
  const mirrored = [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]);
  assert.deepEqual([...EVENT_TYPES].sort(), mirrored.sort());
});

test("runtime enums match the frozen contract", () => {
  const contract = fs.readFileSync(
    path.join(__dirname, "..", "..", "docs", "contracts", "CONTRACTS.md"),
    "utf8",
  );
  const values = (name) => {
    const match = contract.match(new RegExp(`^${name}\\s+(.+)$`, "m"));
    assert.ok(match, `${name} is absent from the contract`);
    return match[1].split("|").map((value) => value.trim());
  };

  assert.deepEqual([...SESSION_STATES], values("session_state"));
  assert.deepEqual([...CONSENT_STATUSES], values("consent_status"));
  assert.deepEqual([...TIMELINE_STAGES], values("timeline_stage"));
});

test("rejects malformed JSON and non-object input", () => {
  for (const raw of ["", "{", "null", "[]", "true", "1", "not json"]) {
    assert.equal(parseVictimEvent(raw), null, raw);
  }
  assert.equal(parseVictimEvent(VALID_EVENTS["assistant.turn"]), null);

  for (const value of [null, undefined, [], "text", 1, true]) {
    assert.equal(validateVictimEvent(value), null);
  }
});

test("accepts ordinary JSON-parsed event and timeline objects", () => {
  const event = JSON.parse(JSON.stringify(VALID_EVENTS["assistant.turn"]));
  const timeline = JSON.parse(JSON.stringify({
    reference: "SAH-2026-00000001",
    timeline: [{ stage: "request_received", label: "label", ts: "time" }],
  }));

  assert.deepEqual(validateVictimEvent(event), event);
  assert.deepEqual(validateVictimTimeline(timeline), timeline);
});

test("rejects class instances and objects with non-standard prototypes", () => {
  class EventFrame {
    constructor() {
      Object.assign(this, VALID_EVENTS["assistant.turn"]);
    }
  }

  const customPrototype = Object.assign(
    Object.create({ marker: "prototype" }),
    VALID_EVENTS["assistant.turn"],
  );
  const inheritedExtra = Object.assign(
    Object.create({ unexpected: true }),
    VALID_EVENTS["assistant.turn"],
  );
  const nullPrototype = Object.assign(
    Object.create(null),
    VALID_EVENTS["assistant.turn"],
  );

  assert.equal(validateVictimEvent(new EventFrame()), null);
  assert.equal(validateVictimEvent(customPrototype), null);
  assert.equal(validateVictimEvent(inheritedExtra), null);
  assert.equal(validateVictimEvent(nullPrototype), null);
});

test("rejects special objects wherever payload objects are expected", () => {
  for (const value of [new Date(), new Map(), new Set()]) {
    assert.equal(validateVictimEvent(value), null);
    assert.equal(validateVictimTimeline(value), null);
    assert.equal(
      validateVictimTimeline({ reference: "reference", timeline: [value] }),
      null,
    );
  }
});

test("rejects symbol and non-enumerable additional own properties", () => {
  const eventWithSymbol = { ...VALID_EVENTS["assistant.turn"] };
  eventWithSymbol[Symbol("extra")] = true;

  const eventWithHidden = { ...VALID_EVENTS["assistant.turn"] };
  Object.defineProperty(eventWithHidden, "hidden", { value: true });

  const timelineWithSymbol = { reference: "reference", timeline: [] };
  timelineWithSymbol[Symbol("extra")] = true;

  const entryWithHidden = { stage: "request_received", label: "label", ts: "time" };
  Object.defineProperty(entryWithHidden, "hidden", { value: true });

  assert.equal(validateVictimEvent(eventWithSymbol), null);
  assert.equal(validateVictimEvent(eventWithHidden), null);
  assert.equal(validateVictimTimeline(timelineWithSymbol), null);
  assert.equal(
    validateVictimTimeline({ reference: "reference", timeline: [entryWithHidden] }),
    null,
  );
});

test("rejects unknown event names", () => {
  assert.equal(validateVictimEvent({ type: "unknown.event" }), null);
});

test("rejects every event when any required key is missing", () => {
  for (const event of Object.values(VALID_EVENTS)) {
    for (const key of Object.keys(event)) {
      const incomplete = { ...event };
      delete incomplete[key];
      assert.equal(validateVictimEvent(incomplete), null, `${event.type} without ${key}`);
    }
  }
});

test("rejects wrong primitive types", () => {
  const changes = [
    ["assistant.turn", "turn_id", 1],
    ["assistant.turn", "text", false],
    ["assistant.turn", "intent", {}],
    ["transcript.line", "turn_id", 1],
    ["transcript.line", "text", false],
    ["transcript.line", "ts", 1],
    ["session.status", "human_joined", "false"],
    ["timeline.update", "label", 1],
    ["timeline.update", "ts", false],
    ["officer.message", "turn_id", 1],
    ["officer.message", "text", false],
    ["officer.message", "ts", 1],
  ];

  for (const [type, key, value] of changes) {
    assert.equal(
      validateVictimEvent({ ...VALID_EVENTS[type], [key]: value }),
      null,
      `${type}.${key}`,
    );
  }
});

test("rejects invalid enumerated event values", () => {
  const changes = [
    ["assistant.turn", "lang", "fr"],
    ["assistant.turn", "audio", "complete"],
    ["transcript.line", "speaker", "officer"],
    ["transcript.line", "lang", "fr"],
    ["session.status", "state", "S10"],
    ["session.status", "consent", "unknown"],
    ["session.status", "lang", "fr"],
    ["timeline.update", "stage", "recorded"],
    ["officer.message", "lang", "fr"],
  ];

  for (const [type, key, value] of changes) {
    assert.equal(
      validateVictimEvent({ ...VALID_EVENTS[type], [key]: value }),
      null,
      `${type}.${key}`,
    );
  }
});

test("officer.message accepts only human_officer origin", () => {
  assert.equal(
    validateVictimEvent({ ...VALID_EVENTS["officer.message"], origin: "assistant" }),
    null,
  );
});

test("rejects additional event keys generically", () => {
  for (const event of Object.values(VALID_EVENTS)) {
    assert.equal(validateVictimEvent({ ...event, unexpected: true }), null, event.type);
  }
  assert.equal(
    validateVictimEvent({ ...VALID_EVENTS["timeline.update"], svi: 10 }),
    null,
  );
});

test("accepts the exact single-case timeline and preserves entry order", () => {
  const value = {
    reference: "SAH-2026-00000001",
    timeline: [
      { stage: "under_review", label: "second", ts: "2026-09-11T11:00:00Z" },
      { stage: "request_received", label: "first", ts: "2026-09-11T10:00:00Z" },
    ],
  };

  const validated = validateVictimTimeline(value);
  assert.deepEqual(validated, value);
  assert.deepEqual(validated.timeline.map((entry) => entry.label), ["second", "first"]);
});

test("accepts every approved timeline stage", () => {
  for (const stage of TIMELINE_STAGES) {
    const value = {
      reference: "SAH-2026-00000001",
      timeline: [{ stage, label: "label", ts: "time" }],
    };
    assert.deepEqual(validateVictimTimeline(value), value);
  }
});

test("rejects malformed timeline responses", () => {
  const exact = {
    reference: "SAH-2026-00000001",
    timeline: [{ stage: "request_received", label: "label", ts: "time" }],
  };

  for (const value of [null, [], {}, { timeline: [] }, { reference: "reference" }]) {
    assert.equal(validateVictimTimeline(value), null);
  }
  assert.equal(validateVictimTimeline({ ...exact, reference: 1 }), null);
  assert.equal(validateVictimTimeline({ ...exact, timeline: {} }), null);
  assert.equal(
    validateVictimTimeline({ ...exact, timeline: [{ ...exact.timeline[0], stage: "recorded" }] }),
    null,
  );
  assert.equal(
    validateVictimTimeline({ ...exact, timeline: [{ ...exact.timeline[0], label: false }] }),
    null,
  );
  assert.equal(
    validateVictimTimeline({ ...exact, timeline: [{ ...exact.timeline[0], ts: 1 }] }),
    null,
  );
});

test("rejects additional outer and timeline-entry fields", () => {
  const entry = { stage: "request_received", label: "label", ts: "time" };
  assert.equal(
    validateVictimTimeline({ reference: "reference", timeline: [], unexpected: true }),
    null,
  );
  assert.equal(
    validateVictimTimeline({ reference: "reference", timeline: [{ ...entry, unexpected: true }] }),
    null,
  );
  assert.equal(
    validateVictimTimeline({ reference: "reference", timeline: [{ ...entry, band: "High" }] }),
    null,
  );
});

test("socket dispatch drops invalid input and emits only validated events", () => {
  const received = [];
  assert.equal(dispatchVictimEvent("{", (event) => received.push(event)), false);
  assert.equal(
    dispatchVictimEvent(JSON.stringify({ type: "unknown.event" }), (event) => received.push(event)),
    false,
  );
  assert.equal(
    dispatchVictimEvent(
      JSON.stringify({ ...VALID_EVENTS["assistant.turn"], unexpected: true }),
      (event) => received.push(event),
    ),
    false,
  );
  assert.equal(
    dispatchVictimEvent(
      JSON.stringify(VALID_EVENTS["assistant.turn"]),
      (event) => received.push(event),
    ),
    true,
  );
  assert.deepEqual(received, [VALID_EVENTS["assistant.turn"]]);
});

test("SessionSocket delegates text frames to the strict dispatch path", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "src", "net", "socket.ts"), "utf8");
  assert.match(source, /import \{ dispatchVictimEvent \} from ["']\.\/victimPayload["']/);
  assert.match(source, /dispatchVictimEvent\(String\(message\.data\), this\.options\.onEvent\)/);
  assert.doesNotMatch(source, /parsed as VictimEvent/);
});
