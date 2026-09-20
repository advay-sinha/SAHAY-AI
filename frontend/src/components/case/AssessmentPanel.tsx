import { assessmentView, explainAbstention } from "../../console/logic";
import type { PacketAssessment } from "../../types/packet";

/**
 * The SVI is never a bare number: the breakdown and confidence sit beside it,
 * and the weights are labelled provisional. Needs Human Assessment replaces the
 * score entirely — no number is rendered anywhere in that state.
 */
export function AssessmentPanel({
  assessment,
  onEvidence,
}: {
  assessment: PacketAssessment;
  onEvidence: (turnId: string) => void;
}) {
  const view = assessmentView(assessment);

  if (view.mode === "suppressed") {
    return (
      <section aria-labelledby="assess-h" className="panel border-l-4 border-l-outline p-3">
        <h2 id="assess-h" className="font-semibold">Assessment</h2>
        <p className="mt-1 text-sm">{view.reason}</p>
        <p className="mt-1 text-sm">Read the transcript and assess the case directly.</p>
      </section>
    );
  }

  if (view.mode === "needs_human") {
    return (
      <section aria-labelledby="assess-h" className="panel border-l-4 border-l-amber-600 p-3" data-testid="needs-human">
        <h2 id="assess-h" className="font-semibold">Needs Human Assessment</h2>
        <p className="mt-1 text-sm">
          The system has not produced a score for this case. Assess it from the transcript.
        </p>
        {view.reasons.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-sm">
            {view.reasons.map((r) => (
              <li key={r}>{explainAbstention(r)}</li>
            ))}
          </ul>
        )}
        {view.evidenceDimensions.length > 0 && (
          <p className="mt-2 text-xs text-neutral-700">
            Evidence has been noted for: {view.evidenceDimensions.join(", ")}. See the transcript.
          </p>
        )}
      </section>
    );
  }

  return (
    <section aria-labelledby="assess-h" className="panel overflow-hidden p-3">
      <h2 id="assess-h" className="text-headline-sm">Structured Vulnerability Index (SVI)</h2>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-4">
        <span className="text-3xl font-bold tabular-nums" aria-label={`Stress vulnerability index ${view.svi}`}>
          {view.svi.toFixed(1)}
        </span>
        <span className={`badge badge-${view.band.toLowerCase()}`}>{view.band}</span>
        <span className="ml-auto text-sm font-semibold text-secondary">
          Confidence {view.confidence === null ? "—" : view.confidence.toFixed(2)}
        </span>
      </div>
      {view.overrides.length > 0 && (
        <p className="mt-1 text-sm font-medium">Hard override: {view.overrides.join(", ").replace(/_/g, " ")}</p>
      )}
      <p className="mt-1 text-xs text-neutral-700">Weights are provisional, pending expert calibration.</p>
      {view.normalizationNote && (
        <p className="mt-1 text-xs text-neutral-700" data-testid="normalization-note">{view.normalizationNote}</p>
      )}
      <div className="mt-3 overflow-x-auto"><table className="w-full text-xs">
        <caption className="sr-only">Dimension breakdown</caption>
        <thead>
          <tr className="bg-surface-container text-left text-[10px] uppercase tracking-wide">
            <th scope="col">Dimension</th>
            <th scope="col" className="text-right">Weight</th>
            <th scope="col" className="text-right">Score</th>
            <th scope="col" className="text-right">Conf.</th>
            <th scope="col">Evidence</th>
          </tr>
        </thead>
        <tbody>
          {view.rows.map((r) => (
            <tr key={r.dimension} className="border-t border-outline-variant/40 align-top">
              <th scope="row" className="py-1 text-left font-normal">
                {r.dimension} · {r.label}
              </th>
              <td className="text-right tabular-nums">{r.weight.toFixed(2)}</td>
              <td className="text-right tabular-nums">{!r.available ? "unavailable" : r.score === null ? "—" : r.score.toFixed(0)}</td>
              <td className="text-right tabular-nums">{r.confidence === null ? "—" : r.confidence.toFixed(2)}</td>
              <td>
                {r.evidence.length === 0 ? (
                  <span className="text-xs text-neutral-600">{!r.available ? "not measured on this channel" : r.score === null ? "not scored" : "none"}</span>
                ) : (
                  r.evidence.map((id, i) => (
                    <button key={id} type="button" onClick={() => onEvidence(id)}
                      className="mr-1 text-xs underline" aria-label={`Show evidence ${i + 1} for ${r.dimension}`}>
                      [{i + 1}]
                    </button>
                  ))
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </section>
  );
}
