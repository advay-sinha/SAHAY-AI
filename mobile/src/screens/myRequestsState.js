const { validateVictimTimeline } = require("../net/victimPayload");

function selectMyRequestsPresentation(loadState, payload) {
  if (loadState === "loading") return { kind: "loading" };
  if (loadState === "unavailable") return { kind: "unavailable" };
  if (loadState === "failed") return { kind: "failed" };
  if (loadState !== "ready") return { kind: "unavailable" };

  const value = validateVictimTimeline(payload);
  if (value === null) return { kind: "failed" };
  if (value.timeline.length === 0) return { kind: "empty" };

  return {
    kind: "timeline",
    reference: value.reference,
    entries: value.timeline.map((entry) => ({
      stage: entry.stage,
      label: entry.label,
    })),
  };
}

module.exports = { selectMyRequestsPresentation };
