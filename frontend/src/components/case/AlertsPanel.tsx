import { formatAcknowledgedBy, turnNumber } from "../../console/logic";
import type { PacketAlert, PacketTurn } from "../../types/packet";

/** Alerts sit at the top of the workspace and require acknowledgement. */
export function AlertsPanel({
  alerts,
  transcript,
  onAcknowledge,
  readOnly = false,
  onEvidence,
  busyId,
}: {
  alerts: PacketAlert[];
  transcript: PacketTurn[];
  onAcknowledge: (alertId: string) => void;
  /** Supervisor view (PC-06): acknowledgement is an executive act. */
  readOnly?: boolean;
  onEvidence: (turnId: string) => void;
  busyId: string | null;
}) {
  if (alerts.length === 0) {
    return (
      <section aria-labelledby="alerts-h" className="panel p-3">
        <h2 id="alerts-h" className="font-semibold">Safety alerts</h2>
        <p className="text-sm text-neutral-700">No safety alerts.</p>
      </section>
    );
  }
  return (
    <section aria-labelledby="alerts-h" className="space-y-2">
      <h2 id="alerts-h" className="font-semibold">Safety alerts</h2>
      {alerts.map((a) => {
        const pending = a.requires_ack && !a.acknowledged_at;
        return (
          <article
            key={a.id}
            role={pending ? "alert" : undefined}
            className={`rounded border p-3 ${pending ? "border-error bg-error text-on-error" : "border-secondary/50 bg-teal-50"}`}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-semibold capitalize">
                {a.alert_type} · <span className="uppercase">{a.severity}</span>
              </span>
              {pending ? (
                <button type="button" onClick={() => onAcknowledge(a.id)} disabled={readOnly || busyId === a.id}
                  className="rounded border border-white px-2 py-1 text-sm font-semibold hover:bg-white hover:text-error">
                  {busyId === a.id ? "Acknowledging…" : "Acknowledge"}
                </button>
              ) : (
                <span className="text-xs">{formatAcknowledgedBy(a.acknowledged_by, a.acknowledged_at) ?? "Acknowledged"}</span>
              )}
            </div>
            <p className="mt-1 text-xs">
              Triggered by{" "}
              {a.evidence_turn_ids.map((id) => (
                <button key={id} type="button" onClick={() => onEvidence(id)} className="mr-1 underline">
                  turn {turnNumber(id, transcript) ?? "?"}
                </button>
              ))}
            </p>
          </article>
        );
      })}
    </section>
  );
}
