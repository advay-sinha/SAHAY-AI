import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ConnectionCheck } from "../components/ConnectionCheck";
import { ConsoleIcon } from "../components/ConsoleIcon";
import { EMPTY_FILTERS, filterQueue, formatWait, type QueueFilters } from "../console/logic";
import type { QueueItem } from "../types/packet";

const POLL_MS = 5000;
const bands = ["Critical", "High", "Moderate", "Low"] as const;
const bandBadge = (i: QueueItem) => i.needs_human_assessment || !i.band ? "badge-nha" : `badge-${i.band.toLowerCase()}`;

/** Live, privacy-safe queue backed exclusively by GET /queue. */
export function QueuePage() {
  const { api, session } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [filters, setFilters] = useState<QueueFilters>(EMPTY_FILTERS);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => { try { setItems(await api.queue()); setState("ready"); } catch (err) { if (err instanceof ApiError && err.status === 401) return; setState((s) => s === "ready" ? s : "error"); } }, [api]);
  useEffect(() => { void load(); const timer = setInterval(() => void load(), POLL_MS); return () => clearInterval(timer); }, [load]);
  const shown = useMemo(() => filterQueue(items, filters), [items, filters]);
  const languages = useMemo(() => [...new Set(items.map((i) => i.language).filter(Boolean))] as string[], [items]);
  const counts = useMemo(() => ({ critical: items.filter((i) => i.unacknowledged_critical).length, high: items.filter((i) => i.band === "High").length, nha: items.filter((i) => i.needs_human_assessment || !i.band).length, unassigned: items.filter((i) => !i.assigned_officer_id).length }), [items]);

  async function claim(caseId: string) { try { await api.claim(caseId); navigate(`/cases/${caseId}`); } catch (err) { setNotice(err instanceof ApiError && err.detail ? err.detail : "The case could not be claimed."); void load(); } }

  return <main className="mx-auto max-w-[1500px] space-y-4 p-4 lg:p-6">
    <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Queue summary">
      {[{ label: "Live active triage", value: items.length, note: "cases pending", tone: "border-secondary", icon: "radio" }, { label: "Critical danger", value: counts.critical, note: "unacknowledged", tone: "border-error", icon: "alert" }, { label: "High band SVI", value: counts.high, note: "score 55–74", tone: "border-amber-600", icon: "shield" }, { label: "Assessment needed", value: counts.nha, note: "score suppressed", tone: "border-blue-300", icon: "user" }].map((card) => <article key={card.label} className={`panel border-t-4 ${card.tone} p-4`}><div className="flex items-center justify-between"><span className="text-label-sm uppercase tracking-wider text-on-surface-variant">{card.label}</span><ConsoleIcon name={card.icon} className="h-4 w-4" /></div><div className="mt-2 flex items-baseline gap-2"><strong className="text-3xl tabular-nums">{state === "loading" ? "—" : String(card.value).padStart(2, "0")}</strong><span className="text-xs text-on-surface-variant">{card.note}</span></div></article>)}
    </section>

    {counts.critical > 0 && <section role="alert" className="flex flex-wrap items-center gap-3 rounded border border-red-900 bg-primary-container p-3 text-white"><span className="grid h-9 w-9 place-items-center rounded bg-error"><ConsoleIcon name="alert" className="h-5 w-5" /></span><div><strong className="block text-sm">HIGH PRIORITY QUEUE ALERT ACTIVE</strong><span className="text-xs text-slate-300">{counts.critical} critical {counts.critical === 1 ? "case requires" : "cases require"} immediate review.</span></div></section>}

    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-outline-variant/50 p-3">
        <h1 className="mr-auto text-headline-md">Live Case Queue</h1>
        <span className="badge badge-success"><ConsoleIcon name="refresh" className="h-3.5 w-3.5" /> Live polling · 5s</span>
        <span className="badge badge-low">{counts.unassigned} unassigned</span>
      </div>
      <form className="grid gap-2 bg-surface-container-low p-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Queue filters" onSubmit={(e) => e.preventDefault()}>
        <label className="text-label-sm">SVI BAND<select className="mt-1 block h-9 w-full rounded border border-outline-variant bg-white px-2 text-sm" value={filters.band} onChange={(e) => setFilters({ ...filters, band: e.target.value as QueueFilters["band"] })}><option value="">All severity levels</option>{bands.map((b) => <option key={b}>{b}</option>)}<option value="needs_human">Needs Human Assessment</option></select></label>
        <label className="text-label-sm">LANGUAGE<select className="mt-1 block h-9 w-full rounded border border-outline-variant bg-white px-2 text-sm" value={filters.language} onChange={(e) => setFilters({ ...filters, language: e.target.value })}><option value="">All languages</option>{languages.map((l) => <option key={l}>{l}</option>)}</select></label>
        <label className="flex h-9 items-center gap-2 self-end rounded border border-outline-variant bg-white px-3 text-sm"><input type="checkbox" checked={filters.alertsOnly} onChange={(e) => setFilters({ ...filters, alertsOnly: e.target.checked })} /> Unacknowledged alerts</label>
        <label className="flex h-9 items-center gap-2 self-end rounded border border-outline-variant bg-white px-3 text-sm"><input type="checkbox" checked={filters.unassignedOnly} onChange={(e) => setFilters({ ...filters, unassignedOnly: e.target.checked })} /> Unassigned only</label>
      </form>
      {notice && <p role="alert" className="border-t border-error-container bg-error-container px-4 py-2 text-sm text-on-error-container">{notice}</p>}
      <section aria-live="polite" data-testid="queue-state">{state === "loading" && <p className="p-6 text-sm">Loading the live queue…</p>}{state === "error" && <p className="p-6 text-sm text-error">The queue could not be loaded. Retrying automatically.</p>}{state === "ready" && shown.length === 0 && <p className="p-6 text-sm">{items.length === 0 ? "No cases are waiting." : "No cases match these filters."}</p>}</section>
      {shown.length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[1000px] text-sm"><caption className="sr-only">Cases, most urgent first</caption><thead className="bg-surface-container text-left text-[10px] uppercase tracking-wider"><tr><th className="px-3 py-2">Priority</th><th className="px-3 py-2">Reference & channel</th><th className="px-3 py-2">Language</th><th className="px-3 py-2">Session timing</th><th className="px-3 py-2">SVI band</th><th className="px-3 py-2">Safety signals</th><th className="px-3 py-2">Consent</th><th className="px-3 py-2">Assignment</th><th className="px-3 py-2">Operation</th></tr></thead><tbody>
        {shown.map((i) => <tr key={i.case_id} className={`border-b border-outline-variant/40 align-top hover:bg-surface-container-low ${i.unacknowledged_critical ? "bg-red-50" : ""}`}>
          <td className="px-3 py-3"><span className={`block h-10 w-1 rounded ${i.unacknowledged_critical ? "bg-error" : i.band === "High" ? "bg-amber-600" : i.band === "Moderate" ? "bg-secondary" : "bg-blue-200"}`} /><span className="mt-1 block text-[10px] font-bold uppercase">{i.unacknowledged_critical ? "Critical" : i.band ?? "Human"}</span></td>
          <td className="px-3 py-3"><Link to={`/cases/${i.case_id}`} className="font-bold hover:underline">{i.reference}</Link><span className="mt-1 block text-xs text-on-surface-variant">{i.channel ?? "Channel pending"}</span></td>
          <td className="px-3 py-3 font-medium">{i.language ?? "—"}</td>
          <td className="px-3 py-3 tabular-nums"><span className={i.wait_seconds > 90 ? "font-semibold text-error" : ""}>Wait {formatWait(i.wait_seconds)}</span><span className="block text-xs text-on-surface-variant">{i.session_state ?? "State pending"}{i.session_ended ? " · ended" : ""}</span></td>
          <td className="px-3 py-3"><span className={`badge ${bandBadge(i)}`}>{i.band ?? "Needs Human Assessment"}</span>{i.takeover_requested && <span className="mt-1 block text-[10px] font-semibold text-error">TAKEOVER REQUESTED</span>}</td>
          <td className="px-3 py-3">{i.alerts.length === 0 ? <span className="text-on-surface-variant">None</span> : i.alerts.map((a) => <span key={`${a.alert_type}-${a.severity}`} className={`mb-1 mr-1 inline-flex rounded px-1.5 py-0.5 text-[10px] ${a.acknowledged ? "bg-surface-container" : "bg-error-container font-semibold text-on-error-container"}`}>{a.alert_type.replace(/_/g, " ")} · {a.severity}</span>)}</td>
          <td className="px-3 py-3"><span className={i.consent === "granted" ? "font-semibold text-secondary" : i.consent === "declined" ? "text-error" : ""}>{i.consent}</span></td>
          <td className="px-3 py-3">{i.assigned_to ?? <span className="badge badge-low">UNASSIGNED</span>}</td>
          <td className="px-3 py-3">{!i.assigned_officer_id && i.status === "open" ? <button type="button" onClick={() => void claim(i.case_id)} className="btn-primary whitespace-nowrap">Claim case</button> : i.assigned_officer_id === session?.subject ? <Link to={`/cases/${i.case_id}`} className="btn-secondary">Open</Link> : null}</td>
        </tr>)}
      </tbody></table></div>}
    </div>
    <details className="text-xs text-on-surface-variant"><summary className="cursor-pointer">Backend connection</summary><div className="mt-2"><ConnectionCheck /></div></details>
  </main>;
}
