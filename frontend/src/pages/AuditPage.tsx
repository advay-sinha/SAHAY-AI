import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { AuditEntry, QueueItem } from "../types/packet";

/**
 * Audit trail. /audit lists cases; /audit/:caseId shows every recorded event:
 * who (system or a named officer), what and when. Append-only on the server.
 */
export function AuditPage() {
  const { caseId } = useParams();
  const { api } = useAuth();
  const [cases, setCases] = useState<QueueItem[] | null>(null);
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setError(false);
    setEntries(null);
    const run = caseId ? api.audit(caseId).then(setEntries) : api.queue().then(setCases);
    run.catch((err: unknown) => {
      if (!(err instanceof ApiError && err.status === 401)) setError(true);
    });
  }, [api, caseId]);

  if (error) return <main className="p-6">The audit trail could not be loaded.</main>;

  if (!caseId) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <h1 className="text-xl font-medium">Audit trail</h1>
        {cases === null ? <p>Loading…</p> : cases.length === 0 ? <p>No cases.</p> : (
          <ul className="mt-2 list-disc pl-5">
            {cases.map((c) => (
              <li key={c.case_id}><Link to={`/audit/${c.case_id}`} className="underline">{c.reference}</Link></li>
            ))}
          </ul>
        )}
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <p className="text-sm"><Link to="/audit" className="underline">All cases</Link> · <Link to={`/cases/${caseId}`} className="underline">Open case</Link></p>
      <h1 className="mt-1 text-xl font-medium">Audit trail</h1>
      {entries === null ? <p>Loading…</p> : entries.length === 0 ? <p>No events recorded.</p> : (
        <div className="overflow-x-auto">
          <table className="mt-2 w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-500 text-left">
                <th scope="col">When</th><th scope="col">Actor</th><th scope="col">Event</th><th scope="col">Detail</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i} className="border-b border-neutral-200 align-top">
                  <td className="whitespace-nowrap">{e.at ? new Date(e.at).toLocaleString() : "—"}</td>
                  <td>{e.actor_kind === "human" ? e.actor : "system"}</td>
                  <td className="font-mono text-xs">{e.action}</td>
                  <td className="text-xs">
                    {Object.entries(e.detail).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
