import { BAND_BOUNDS, trajectoryGeometry, trajectoryPath, turnNumber } from "../../console/logic";
import type { PacketTurn, TrajectoryPoint } from "../../types/packet";

const W = 280;
const H = 90;

/**
 * SVI over the assessment cycles, in plain SVG. A cycle under Needs Human
 * Assessment has no point and breaks the line: no value is invented for it.
 * Each point is a button that jumps to the utterance that moved it.
 */
export function Trajectory({
  points,
  transcript,
  onEvidence,
}: {
  points: TrajectoryPoint[];
  transcript: PacketTurn[];
  onEvidence: (turnId: string) => void;
}) {
  if (points.length === 0) return null;
  const geo = trajectoryGeometry(points, W, H);
  return (
    <section aria-labelledby="traj-h" className="panel p-3">
      <h2 id="traj-h" className="text-sm font-semibold">Trajectory</h2>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 h-24 w-full" role="img"
        aria-label="SVI across assessment cycles; gaps are cycles without a score">
        {BAND_BOUNDS.map((b) => (
          <line key={b.band} x1={0} x2={W} y1={H - 8 - (b.from / 100) * (H - 16)}
            y2={H - 8 - (b.from / 100) * (H - 16)} stroke="#d4d4d4" strokeWidth={0.5} />
        ))}
        <path d={trajectoryPath(geo)} fill="none" stroke="#171717" strokeWidth={1.5} />
        {geo.map((g) =>
          g.y === null ? (
            <text key={g.point.cycle} x={g.x} y={H - 2} fontSize={7} textAnchor="middle" fill="#525252">NHA</text>
          ) : (
            <circle key={g.point.cycle} cx={g.x} cy={g.y} r={3} fill="#171717" />
          ),
        )}
      </svg>
      <ol className="mt-1 space-y-0.5 text-xs">
        {points.map((p) => (
          <li key={p.cycle}>
            Cycle {p.cycle}: {p.band ?? "Needs Human Assessment"}
            {p.svi !== null ? ` (${p.svi.toFixed(1)})` : ""} ·{" "}
            {p.trigger_turn_id ? (
              <button type="button" className="underline" onClick={() => onEvidence(p.trigger_turn_id!)}>
                after turn {turnNumber(p.trigger_turn_id, transcript) ?? "?"}
              </button>
            ) : "—"}{" "}
            <span className="text-neutral-600">({p.cause.replace(/_/g, " ")})</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
