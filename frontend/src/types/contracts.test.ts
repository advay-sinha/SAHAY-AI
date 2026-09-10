/**
 * Contract mirror — self-consistency checks.
 *
 * Deliberately uses no Node APIs (`fs`, `path`, `__dirname`), so it needs no
 * `@types/node` and does not change the approved EXT-001 dependency set.
 *
 * The cross-file comparison — this file against `backend/app/ws/events.py`,
 * `ml/svi/dimensions.py` and `docs/contracts/CONTRACTS.md` — lives in
 * `backend/tests/test_contract_mirror.py`, which reads files for free and runs
 * with no installed dependency at all.
 */

import { describe, expect, it } from "vitest";

import {
  ASSESSMENT_DISCLAIMER,
  DIMENSION_LABELS,
  DIMENSION_WEIGHTS,
  EXECUTIVE_ONLY_EVENTS,
  VICTIM_ALLOWED_EVENTS,
  WEIGHTS_ARE_PROVISIONAL,
  type DimensionId,
} from "./contracts";

describe("event allowlists", () => {
  it("has exactly the four victim events from CONTRACTS.md section 2", () => {
    expect([...VICTIM_ALLOWED_EVENTS].sort()).toEqual([
      "assistant.turn",
      "session.status",
      "timeline.update",
      "transcript.line",
    ]);
  });

  it("has exactly the six executive-only events from CONTRACTS.md section 3", () => {
    expect([...EXECUTIVE_ONLY_EVENTS].sort()).toEqual([
      "action.recommended",
      "alert.safety",
      "case.structured",
      "dimension.update",
      "escalation.packet",
      "safesignal.flag",
    ]);
  });

  it("never lets an executive event onto the victim allowlist", () => {
    const victim = new Set<string>(VICTIM_ALLOWED_EVENTS);
    expect(EXECUTIVE_ONLY_EVENTS.filter((e) => victim.has(e))).toEqual([]);
  });
});

describe("SVI dimensions", () => {
  it("weights sum to 1.0", () => {
    const total = Object.values(DIMENSION_WEIGHTS).reduce((a, b) => a + b, 0);
    expect(total).toBeCloseTo(1.0, 6);
  });

  it("labels and weights all nine dimensions", () => {
    const ids = Object.keys(DIMENSION_LABELS) as DimensionId[];
    expect(ids).toHaveLength(9);
    for (const id of ids) {
      expect(DIMENSION_LABELS[id].length).toBeGreaterThan(0);
      expect(DIMENSION_WEIGHTS[id]).toBeGreaterThan(0);
    }
  });

  it("orders D1 and D2 highest, since they carry the hard overrides", () => {
    const sorted = (Object.entries(DIMENSION_WEIGHTS) as [DimensionId, number][])
      .sort((a, b) => b[1] - a[1])
      .map(([id]) => id);
    expect(sorted.slice(0, 2)).toEqual(["D1", "D2"]);
  });
});

describe("what the console must always say", () => {
  it("keeps the weights labelled provisional", () => {
    expect(WEIGHTS_ARE_PROVISIONAL).toBe(true);
  });

  it("disclaims clinical, legal and forensic determination", () => {
    expect(ASSESSMENT_DISCLAIMER).toContain("not a clinical, legal or forensic determination");
    expect(ASSESSMENT_DISCLAIMER).toContain("reviewing officer");
  });
});
