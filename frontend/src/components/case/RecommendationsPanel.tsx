import { useState } from "react";
import { decisionFor, turnNumber, validateDecision } from "../../console/logic";
import type { DecisionKind } from "../../types/contracts";
import type { CasePacket, PacketRecommendation } from "../../types/packet";

/**
 * AI recommendations and the officer's decisions, visually separate:
 * the suggestion is a dashed "Suggested by the system" card that always reads
 * "Awaiting your decision"; the officer's decision is a solid record beneath it
 * with the officer's name. Nothing is ever shown as an action taken until an
 * officer confirms it.
 */
export function RecommendationsPanel({
  packet,
  canDecide,
  blockedReason,
  onDecide,
  onEvidence,
}: {
  packet: CasePacket;
  canDecide: boolean;
  blockedReason: string | null;
  onDecide: (actionId: string, decision: DecisionKind, rationale: string) => Promise<string | null>;
  onEvidence: (turnId: string) => void;
}) {
  if (packet.recommendations.length === 0) {
    return (
      <section aria-labelledby="recs-h" className="panel p-3">
        <h2 id="recs-h" className="font-semibold">Recommendations</h2>
        <p className="text-sm text-neutral-700">
          {packet.assessment.band === null
            ? "None — the system does not suggest pathways while it cannot assess the case."
            : "No pathway suggested."}
        </p>
      </section>
    );
  }
  return (
    <section aria-labelledby="recs-h" className="panel space-y-3 p-3">
      <h2 id="recs-h" className="text-headline-sm">Recommended Support Pathways</h2>
      {!canDecide && blockedReason && <p className="text-xs text-neutral-700">{blockedReason}</p>}
      {packet.recommendations.map((r) => (
        <RecommendationItem key={r.action_id} rec={r} packet={packet} canDecide={canDecide}
          onDecide={onDecide} onEvidence={onEvidence} />
      ))}
    </section>
  );
}

function RecommendationItem({
  rec,
  packet,
  canDecide,
  onDecide,
  onEvidence,
}: {
  rec: PacketRecommendation;
  packet: CasePacket;
  canDecide: boolean;
  onDecide: (actionId: string, decision: DecisionKind, rationale: string) => Promise<string | null>;
  onEvidence: (turnId: string) => void;
}) {
  const decision = decisionFor(packet, rec.action_id);
  const [choice, setChoice] = useState<DecisionKind | null>(null);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!choice) return;
    const invalid = validateDecision(choice, rationale);
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    setError(await onDecide(rec.action_id, choice, rationale.trim()));
    setBusy(false);
  }

  return (
    <div>
      <article className="rounded border border-dashed border-outline bg-surface-container-low p-3" aria-label={`Suggested: ${rec.label}`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-medium">{rec.label}</h3>
          <span className="text-xs uppercase tracking-wide">
            {decision ? "Decided" : "Suggested by the system · awaiting your decision"}
          </span>
        </div>
        <p className="mt-1 text-sm">{rec.rationale}</p>
        <p className="mt-1 text-xs text-neutral-700">
          Confidence {rec.confidence.toFixed(2)} · Evidence:{" "}
          {rec.evidence_turn_ids.map((id) => (
            <button key={id} type="button" onClick={() => onEvidence(id)} className="mr-1 underline">
              turn {turnNumber(id, packet.transcript) ?? "?"}
            </button>
          ))}
          · Source: {rec.policy_citations.join(", ") || "no local note matched"} (demo placeholder, not official policy)
        </p>

        {!decision && canDecide && (
          <fieldset className="mt-2">
            <legend className="sr-only">Decision on {rec.label}</legend>
            <div className="flex gap-2">
              {(["confirm", "modify", "reject"] as const).map((d) => (
                <button key={d} type="button" aria-pressed={choice === d}
                  onClick={() => { setChoice(d); setError(null); }}
                  className={`rounded border px-2 py-1 text-sm capitalize ${choice === d ? "border-primary bg-primary text-white" : "border-outline-variant bg-white"}`}>
                  {d}
                </button>
              ))}
            </div>
            {choice && (
              <div className="mt-2">
                <label className="block text-xs font-medium" htmlFor={`why-${rec.action_id}`}>
                  Rationale{choice === "confirm" ? " (optional)" : " (required)"}
                </label>
                <textarea id={`why-${rec.action_id}`} value={rationale} rows={2} maxLength={1000}
                  onChange={(e) => setRationale(e.target.value)}
                  className="mt-1 w-full border border-neutral-500 p-1 text-sm" />
                {error && <p role="alert" className="text-xs text-red-800">{error}</p>}
                <button type="button" onClick={submit} disabled={busy}
                  className="btn-primary mt-2">
                  {busy ? "Recording…" : `Record ${choice}`}
                </button>
              </div>
            )}
          </fieldset>
        )}
      </article>

      {decision && (
        <div className="ml-4 border-l-4 border-secondary bg-teal-50 p-2 text-sm" aria-label="Officer decision">
          <span className="font-semibold capitalize">Officer decision: {decision.decision}</span>
          <span className="text-xs text-neutral-700"> — {decision.officer}
            {decision.decided_at ? `, ${new Date(decision.decided_at).toLocaleString()}` : ""}</span>
          {decision.rationale && <p className="mt-0.5">{decision.rationale}</p>}
        </div>
      )}
    </div>
  );
}
