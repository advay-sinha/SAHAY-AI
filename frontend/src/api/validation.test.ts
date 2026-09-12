import { describe, expect, it } from "vitest";

import { createApiClient } from "./client";
import { ResponseValidationError, validateHealth, validateTimeline } from "./validation";
import { validateAuthOk, validateSocketEvent } from "./socketValidation";

const HEALTH = {
  status: "ok",
  app_env: "test",
  llm_provider: "mock",
  assessment_runner: "local",
  database: "configured (not probed)",
  fixed_scripts_ready: false,
  detail: {},
};

describe("exact REST response validation", () => {
  it("accepts canonical health and timeline responses without reordering or deduplicating", () => {
    expect(validateHealth(HEALTH)).toEqual(HEALTH);
    const timeline = {
      reference: "SAH-FICTIONAL",
      timeline: [
        { stage: "under_review", label: "second", ts: "2030-01-01T00:00:01Z" },
        { stage: "under_review", label: "second", ts: "2030-01-01T00:00:01Z" },
      ],
    };
    expect(validateTimeline(timeline)).toEqual(timeline);
  });

  it("rejects extra, missing, nested-extra, and prototype-bearing payloads", () => {
    expect(() => validateHealth({ ...HEALTH, reachable: true })).toThrow(ResponseValidationError);
    const { database: _missing, ...incomplete } = HEALTH;
    expect(() => validateHealth(incomplete)).toThrow(ResponseValidationError);
    expect(() => validateTimeline({
      reference: "SAH-FICTIONAL",
      timeline: [{ stage: "request_received", label: "received", ts: "time", band: "High" }],
    })).toThrow(ResponseValidationError);
    expect(() => validateHealth(Object.assign(Object.create({ inherited: true }), HEALTH)))
      .toThrow(ResponseValidationError);
  });

  it("routes every successful Web REST operation through a validator", async () => {
    const fetchFn = async () => new Response(JSON.stringify({ unexpected: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    const api = createApiClient({ fetchFn, getToken: () => "fictional-token", onUnauthorized: () => undefined });
    const operations = [
      api.health(), api.queue(), api.case("case"), api.claim("case"),
      api.acknowledge("case", "alert"), api.decide("case", "action", "confirm", "fictional rationale"),
      api.override("case", "High", "fictional rationale"), api.takeover("case"),
      api.message("case", "fictional message", "en"), api.timeline("case"), api.audit("case"),
    ];
    for (const operation of operations) {
      await expect(operation).rejects.toMatchObject({ status: 502 });
    }
  });
});

describe("exact WebSocket response validation", () => {
  it("accepts only the matching exact authentication acknowledgement", () => {
    const frame = { type: "auth.ok", session_id: "session-1", role: "executive" };
    expect(validateAuthOk(frame, "session-1")).toEqual(frame);
    expect(validateAuthOk({ ...frame, extra: true }, "session-1")).toBeNull();
    expect(validateAuthOk(frame, "session-2")).toBeNull();
  });

  it("accepts an exact status event and rejects unknown or extra keys", () => {
    const status = { type: "session.status", state: "S1", consent: "granted", lang: "en", human_joined: false };
    expect(validateSocketEvent(status)).toEqual(status);
    expect(validateSocketEvent({ ...status, svi: 9 })).toBeNull();
    expect(validateSocketEvent({ type: "chat.ack" })).toBeNull();
  });

  it("mirrors the exact canonical recommendation event without REST-only status", () => {
    const recommendation = {
      type: "action.recommended", action_id: "action-1", action_type: "internal_review",
      rationale: "Fictional rationale.", policy_citations: ["policy-1"], confidence: 0.5,
    };
    expect(validateSocketEvent(recommendation)).toEqual(recommendation);
    expect(validateSocketEvent({ ...recommendation, status: "awaiting_decision" })).toBeNull();
  });

  it("rejects malformed nested executive event data", () => {
    const dims = Object.fromEntries(Array.from({ length: 9 }, (_, index) => [
      `D${index + 1}`, { score: null, conf: null, evidence_turn_ids: [] },
    ]));
    const update = {
      type: "dimension.update", dims, svi: null, band: null,
      needs_human: true, overrides_applied: [],
    };
    expect(validateSocketEvent(update)).toEqual(update);
    expect(validateSocketEvent({ ...update, dims: { ...dims, D4: { score: 0 } } })).toBeNull();
    expect(validateSocketEvent({
      type: "escalation.packet", case_id: "case-1", band: null,
      alerts: [{ alert_type: "crisis", severity: "critical", evidence_turn_ids: [], requires_ack: false }],
      summary: "Fictional summary.", ready: true,
    })).toBeNull();
  });
});
