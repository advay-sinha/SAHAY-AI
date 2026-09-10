import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ConnectionCheck } from "../components/ConnectionCheck";
import { EMPTY_FILTERS, filterQueue, formatWait, type QueueFilters } from "../console/logic";
import type { QueueItem } from "../types/packet";

const POLL_MS = 5000;

/**
 * Live queue. Polls GET /queue (there is no queue event in the frozen
 * contract; PC-04). Critical unacknowledged alerts come first, then takeover
 * requests, then band, then longest waiting — the server's order is kept.
 * No narrative text is shown here: codes only.
 */
export function QueuePage() {
  const { api, session } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [filters, setFilters] = useState<QueueFilters>(EMPTY_FILTERS);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api.queue());
      setState("ready");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setState((s) => (s === "ready" ? s : "error"));
    }
  }, [api]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const shown = useMemo(() => filterQueue(items, filters), [items, filters]);
  const languages = useMemo(() => [...new Set(items.map((i) => i.language).filter(Boolean))] as string[], [items]);

  async function claim(caseId: string) {
    try {
      await api.claim(caseId);
      navigate(`/cases/${caseId}`);
    } catch (err) {
      setNotice(err instanceof ApiError && err.detail ? err.detail : "The case could not be claimed.");
      void load();
    }
  }

  return (
    <main className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-xl font-medium">Live queue</h1>

      <form className="flex flex-wrap items-end gap-3 text-sm" aria-label="Queue filters" onSubmit={(e) => e.preventDefault()}>
        <label>Band
          <select className="ml-1 border border-neutral-500 p-0.5" value={filters.band}
            onChange={(e) => setFilters({ ...filters, band: e.target.value as QueueFilters["band"] })}>
            <option value="">All</option>
            <option value="Critical">Critical</option>
            <option value="High">High</option>
            <option value="Moderate">Moderate</option>
            <option value="Low">Low</option>
            <option value="needs_human">Needs Human Assessment</option>
          </select>
        </label>
        <label>Language
          <select className="ml-1 border border-neutral-500 p-0.5" value={filters.language}
            onChange={(e) => setFilters({ ...filters, language: e.target.value })}>
            <option value="">All</option>
            {languages.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <label><input type="checkbox" className="mr-1" checked={filters.alertsOnly}
          onChange={(e) => setFilters({ ...filters, alertsOnly: e.target.checked })} />Unacknowledged alerts</label>
        <label><input type="checkbox" className="mr-1" checked={filters.unassignedOnly}
          onChange={(e) => setFilters({ ...filters, unassignedOnly: e.target.checked })} />Unassigned</label>
      </form>

      {notice && <p role="alert" className="text-sm text-red-800">{notice}</p>}

      <section aria-live="polite" data-testid="queue-state">
        {state === "loading" && <p>Loading the queue…</p>}
        {state === "error" && <p>The queue could not be loaded. Retrying automatically.</p>}
        {state === "ready" && shown.length === 0 && (
          <p>{items.length === 0 ? "No cases are waiting." : "No cases match these filters."}</p>
        )}
      </section>

      {shown.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Cases, most urgent first</caption>
            <thead>
              <tr className="border-b border-neutral-500 text-left">
                <th scope="col">Reference</th><th scope="col">Band</th><th scope="col">Alerts</th>
                <th scope="col">Lang</th><th scope="col">Channel</th><th scope="col">Waiting</th>
                <th scope="col">State</th><th scope="col">Consent</th><th scope="col">Assigned</th><th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((i) => (
                <tr key={i.case_id} className={`border-b border-neutral-200 ${i.unacknowledged_critical ? "bg-red-50" : ""}`}>
                  <td><Link to={`/cases/${i.case_id}`} className="font-medium underline">{i.reference}</Link></td>
                  <td>{i.band ?? "Needs Human"}{i.takeover_requested ? " · takeover requested" : ""}</td>
                  <td>
                    {i.alerts.length === 0 ? "—" : i.alerts.map((a) => (
                      <span key={a.alert_type} className={`mr-1 inline-block border px-1 text-xs ${a.acknowledged ? "border-neutral-400" : "border-red-800 font-semibold text-red-800"}`}>
                        {a.alert_type} {a.severity}{a.acknowledged ? " ✓" : ""}
                      </span>
                    ))}
                  </td>
                  <td>{i.language}</td><td>{i.channel}</td><td>{formatWait(i.wait_seconds)}</td>
                  <td>{i.session_state}{i.session_ended ? " (ended)" : ""}</td><td>{i.consent}</td>
                  <td>{i.assigned_to ?? "—"}</td>
                  <td>
                    {!i.assigned_officer_id && i.status === "open" ? (
                      <button type="button" onClick={() => void claim(i.case_id)}
                        className="border border-neutral-900 px-2 py-0.5 text-xs font-medium">Claim</button>
                    ) : i.assigned_officer_id === session?.subject ? (
                      <Link to={`/cases/${i.case_id}`} className="text-xs underline">Open</Link>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <details className="text-sm">
        <summary>Backend connection</summary>
        <div className="mt-2"><ConnectionCheck /></div>
      </details>
    </main>
  );
}
