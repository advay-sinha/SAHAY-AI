import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { formatWait } from "../console/logic";
import type { QueueItem } from "../types/packet";

/**
 * Supervisor view — READ-ONLY by owner decision (2026-09-10). Operational
 * status only: counts by band and state, unacknowledged alerts, unassigned and
 * longest-waiting cases, and who holds what. No reassignment control (BE-021,
 * P3; docs/contracts/PROPOSED_CHANGES.md PC-06) and deliberately no per-officer
 * performance ranking.
 *
 * Reachable only with a supervisor session; executives are redirected by the
 * route guard. The backend is still the authority on every request.
 */
export function SupervisorPage() {
  const { api } = useAuth();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const load = () =>
      api.queue().then(setItems).catch((err: unknown) => {
        if (!(err instanceof ApiError && err.status === 401)) setError(true);
      });
    void load();
    const t = setInterval(load, 10_000);
    return () => clearInterval(t);
  }, [api]);

  const stats = useMemo(() => {
    const all = items ?? [];
    const count = (f: (i: QueueItem) => boolean) => all.filter(f).length;
    return {
      total: all.length,
      bands: (["Critical", "High", "Moderate", "Low"] as const).map((b) => [b, count((i) => i.band === b)] as const),
      nha: count((i) => i.band === null),
      unackAlerts: count((i) => i.alerts.some((a) => !a.acknowledged)),
      unassigned: count((i) => !i.assigned_officer_id),
      takenOver: count((i) => i.status === "taken_over"),
      takeoverRequested: count((i) => i.takeover_requested && i.status !== "taken_over"),
      oldestUnassigned: all.filter((i) => !i.assigned_officer_id).sort((a, b) => b.wait_seconds - a.wait_seconds).slice(0, 5),
    };
  }, [items]);

  if (error) return <main className="p-6">Operational status could not be loaded.</main>;
  if (items === null) return <main className="p-6">Loading…</main>;

  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <h1 className="text-xl font-medium">Supervisor — operational status</h1>
      <p className="text-xs text-neutral-700">Read-only. Reassignment arrives with the supervisor endpoints.</p>

      <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        {[
          ["Open cases", stats.total],
          ["Unacknowledged alerts", stats.unackAlerts],
          ["Takeover requested, not yet taken", stats.takeoverRequested],
          ["Unassigned", stats.unassigned],
          ["Taken over", stats.takenOver],
          ["Needs Human Assessment", stats.nha],
          ...stats.bands,
        ].map(([label, value]) => (
          <div key={String(label)} className="border border-neutral-300 p-2">
            <dt className="text-xs text-neutral-700">{label}</dt>
            <dd className="text-lg tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="oldest-h">
        <h2 id="oldest-h" className="font-semibold">Longest-waiting unassigned cases</h2>
        {stats.oldestUnassigned.length === 0 ? <p className="text-sm">None.</p> : (
          <ul className="mt-1 text-sm">
            {stats.oldestUnassigned.map((i) => (
              <li key={i.case_id}>
                <Link to={`/cases/${i.case_id}`} className="underline">{i.reference}</Link> — waiting {formatWait(i.wait_seconds)},{" "}
                {i.band ?? "Needs Human Assessment"}{i.alerts.some((a) => !a.acknowledged) ? ", unacknowledged alert" : ""}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="assign-h">
        <h2 id="assign-h" className="font-semibold">Assignments</h2>
        <ul className="mt-1 text-sm">
          {items.filter((i) => i.assigned_officer_id).map((i) => (
            <li key={i.case_id}>{i.reference} — {i.assigned_to} ({i.status.replace("_", " ")})</li>
          ))}
          {items.every((i) => !i.assigned_officer_id) && <li>No cases assigned.</li>}
        </ul>
      </section>
    </main>
  );
}
