import { modelSignalRows, turnNumber } from "../../console/logic";
import type { ModelSignal } from "../../types/contracts";
import type { PacketTurn } from "../../types/packet";

/**
 * PC-14: an experimental classifier's reading of the victim's words, for the officer only.
 * Advisory and uncalibrated. It never changes the band, alerts, routing or anything the
 * victim hears; the rules stay authoritative and the officer decides.
 */
export function ModelSignalsPanel({
  signal,
  transcript,
  onEvidence,
}: {
  signal: ModelSignal | null;
  transcript: PacketTurn[];
  onEvidence: (turnId: string) => void;
}) {
  if (!signal) return null;
  const rows = modelSignalRows(signal);
  const upTo = signal.trigger_turn_id ? turnNumber(signal.trigger_turn_id, transcript) : null;
  return (
    <section aria-labelledby="model-signals-h" className="panel p-3">
      <h2 id="model-signals-h" className="font-semibold">
        AI signal <span className="text-xs font-normal text-neutral-700">(advisory, experimental)</span>
      </h2>
      {signal.flag ? (
        <p role="alert" className="mt-2 rounded border border-error bg-error p-2 text-sm font-semibold text-on-error">
          The model flagged possible crisis language that the rules did not. Please read the transcript.
        </p>
      ) : null}
      {signal.status !== "loaded" ? (
        <p className="mt-1 text-sm text-neutral-700">Model signal unavailable for this cycle.</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm">
          {rows.map((r) => (
            <li key={r.label} className="flex items-baseline justify-between gap-2">
              <span>{r.name}</span>
              <span className={r.fired ? "font-semibold" : "text-neutral-700"}>
                {r.percent}% {r.fired ? "· fired" : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {signal.trigger_turn_id ? (
        <p className="mt-2 text-xs">
          Read from the person's words up to{" "}
          <button type="button" onClick={() => onEvidence(signal.trigger_turn_id as string)} className="underline">
            turn {upTo ?? "?"}
          </button>
        </p>
      ) : null}
      <p className="mt-2 text-xs text-neutral-700">
        Uncalibrated reading from an experimental model ({signal.checkpoint_status.replace(/_/g, " ")}).
        It never changes the band, alerts or routing. The rules and your judgement decide.
      </p>
    </section>
  );
}
