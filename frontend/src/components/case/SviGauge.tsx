import { DIMENSION_LABELS, DIMENSION_WEIGHTS, WEIGHTS_ARE_PROVISIONAL } from "../../types/contracts";
import type { DimensionUpdate } from "../../types/contracts";

/**
 * The SVI is never a bare number: the breakdown sits next to it and confidence
 * has equal prominence. When the engine abstains there is no score to show, and
 * that is a designed state rather than an error.
 */
export function SviGauge({ update }: { update: DimensionUpdate }) {
  if (update.needs_human || update.svi === null) {
    return <NeedsHumanState overrides={update.overrides_applied} />;
  }

  return (
    <section aria-label="Stress Vulnerability Index">
      <div className="flex items-baseline gap-3">
        <span className="text-3xl tabular-nums">{update.svi.toFixed(1)}</span>
        <span className="text-lg">{update.band}</span>
      </div>
      {WEIGHTS_ARE_PROVISIONAL && (
        <p className="text-xs text-neutral-700">Weights are provisional, pending expert calibration.</p>
      )}
      <DimensionBreakdown update={update} />
    </section>
  );
}

export function DimensionBreakdown({ update }: { update: DimensionUpdate }) {
  const rows = Object.entries(update.dims);
  return (
    <table className="w-full text-sm">
      <thead>
        <tr>
          <th scope="col" className="text-left">Dimension</th>
          <th scope="col" className="text-right">Weight</th>
          <th scope="col" className="text-right">Score</th>
          <th scope="col" className="text-right">Confidence</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([id, value]) => (
          <tr key={id}>
            <th scope="row" className="text-left font-normal">
              {id} · {DIMENSION_LABELS[id as keyof typeof DIMENSION_LABELS]}
            </th>
            <td className="text-right tabular-nums">
              {DIMENSION_WEIGHTS[id as keyof typeof DIMENSION_WEIGHTS].toFixed(2)}
            </td>
            <td className="text-right tabular-nums">{value.score.toFixed(0)}</td>
            <td className="text-right tabular-nums">{value.conf.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function NeedsHumanState({ overrides }: { overrides: string[] }) {
  return (
    <section aria-label="Needs human assessment" className="border border-neutral-400 p-3">
      <h3 className="font-medium">Needs human assessment</h3>
      <p className="text-sm">
        The system did not produce a score for this case. Read the transcript and assess it directly.
      </p>
      {overrides.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm">
          {overrides.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
