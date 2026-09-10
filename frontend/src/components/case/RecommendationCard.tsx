import type { ActionRecommended, DecisionKind } from "../../types/contracts";

/**
 * A recommendation renders as awaiting a decision, never as an action taken.
 * The officer's choice is what gets written, to a separate record.
 */
export function RecommendationCard({
  recommendation,
  onDecide,
}: {
  recommendation: ActionRecommended;
  onDecide: (decision: DecisionKind) => void;
}) {
  return (
    <article className="border border-neutral-400 p-3">
      <header className="flex items-baseline justify-between">
        <h3 className="font-medium">{recommendation.action_type}</h3>
        <span className="text-xs uppercase tracking-wide">Awaiting your decision</span>
      </header>
      <p className="text-sm">{recommendation.rationale}</p>
      <p className="text-xs text-neutral-700">
        Confidence {recommendation.confidence.toFixed(2)}
        {recommendation.policy_citations.length === 0
          ? " · no policy citation"
          : ` · ${recommendation.policy_citations.join(", ")}`}
      </p>
      <div className="mt-2 flex gap-2">
        {(["confirm", "modify", "reject"] as const).map((decision) => (
          <button key={decision} type="button" onClick={() => onDecide(decision)}>
            {decision}
          </button>
        ))}
      </div>
    </article>
  );
}
