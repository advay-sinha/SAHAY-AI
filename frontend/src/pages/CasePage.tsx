import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AlertsPanel } from "../components/case/AlertsPanel";
import { AssessmentPanel } from "../components/case/AssessmentPanel";
import { DecisionControls } from "../components/case/DecisionControls";
import { RecommendationsPanel } from "../components/case/RecommendationsPanel";
import { StructuredPanel } from "../components/case/StructuredPanel";
import { TranscriptPanel } from "../components/case/TranscriptPanel";
import { Trajectory } from "../components/case/Trajectory";
import { canAct, canMessage, formatWait, resolveEvidence } from "../console/logic";
import { useCaseSocket } from "../console/useCaseSocket";
import type { Band, DecisionKind } from "../types/contracts";
import type { CasePacket } from "../types/packet";

type LoadState = "loading" | "ready" | "missing" | "error";

function problem(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.detail) return err.detail;
    if (err.status === 0) return "The server could not be reached.";
  }
  return "The action could not be completed. Try again.";
}

/**
 * Case workspace: metadata and structured record (left), two-sided transcript
 * (centre), assessment, alerts, uncertainty, recommendations and decisions
 * (right). Live updates arrive over the case's session socket; every event
 * triggers a refetch of the packet, which is the source of truth.
 */
export function CasePage() {
  const { caseId = "" } = useParams();
  const { api, session } = useAuth();
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [highlight, setHighlight] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyAlert, setBusyAlert] = useState<string | null>(null);
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setPacket(await api.case(caseId));
      setState("ready");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return; // client signs the user out
      setState(err instanceof ApiError && err.status === 404 ? "missing" : "error");
    }
  }, [api, caseId]);

  useEffect(() => {
    setState("loading");
    void load();
  }, [load]);

  // Coalesce a burst of socket events into one refetch.
  const onEvent = useCallback(() => {
    clearTimeout(refetchTimer.current);
    refetchTimer.current = setTimeout(() => void load(), 250);
  }, [load]);
  useEffect(() => () => clearTimeout(refetchTimer.current), []);

  const socket = useCaseSocket(packet?.header.session_id, session?.token, onEvent);

  const showEvidence = useCallback(
    (turnId: string) => {
      if (!packet || resolveEvidence([turnId], packet.transcript).length === 0) return;
      setHighlight(turnId);
      const el = document.getElementById(`turn-${turnId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.focus({ preventScroll: true });
    },
    [packet],
  );

  async function run(action: () => Promise<unknown>): Promise<string | null> {
    try {
      await action();
      await load();
      return null;
    } catch (err) {
      return problem(err);
    }
  }

  if (state === "loading") return <main className="p-6">Loading case…</main>;
  if (state === "missing") return <main className="p-6">This case does not exist. <Link to="/queue" className="underline">Back to the queue</Link></main>;
  if (state === "error" || !packet) {
    return (
      <main className="p-6">
        <p>The case could not be loaded.</p>
        <button type="button" onClick={() => void load()} className="mt-2 border px-3 py-1">Retry</button>
      </main>
    );
  }

  const h = packet.header;
  const gate = canAct(packet, session?.subject, session?.role);
  const messageGate = canMessage(packet, gate);
  const readOnly = session?.role === "supervisor";
  const claimable = !readOnly && !h.assigned_officer_id && h.status === "open";

  return (
    <main className="mx-auto max-w-[1600px] space-y-4 p-4 lg:p-6">
      <header className="panel flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
        <Link to="/queue" className="text-xs text-on-surface-variant hover:underline">← Queue</Link>
        <Link to={`/audit/${caseId}`} className="text-xs text-on-surface-variant hover:underline">Audit ledger</Link>
        <h1 className="text-headline-md">{h.reference}</h1>
        <span className={`badge ${h.band ? `badge-${h.band.toLowerCase()}` : "badge-nha"}`}>{h.band ? `Band ${h.band}` : "Needs Human Assessment"}
          {h.band_source === "override" ? " (officer override)" : ""}</span>
        <span className="text-sm">Consent: {h.consent}</span>
        <span className="text-sm">{h.language} · {h.channel}</span>
        {h.duration_seconds !== null && <span className="text-sm">Duration {formatWait(h.duration_seconds)}</span>}
        <span className="text-sm">State {h.session_state}{h.session_ended ? " (ended)" : ""}</span>
        <span className="text-sm">{h.assigned_to ? `Assigned: ${h.assigned_to}` : "Unassigned"}</span>
        {h.takeover_requested && <span className="border border-red-800 px-1 text-sm font-semibold text-red-800">Takeover requested</span>}
        <span className={`ml-auto text-xs ${socket === "live" ? "" : "font-semibold"}`} aria-live="polite">
          {socket === "live" ? "Live" : socket === "reconnecting" ? "Reconnecting…" : socket === "offline" ? "Offline — showing last known state" : "Connecting…"}
        </span>
        {claimable && (
          <button type="button" className="btn-primary"
            onClick={async () => setNotice(await run(() => api.claim(caseId)))}>
            Claim case
          </button>
        )}
      </header>
      {notice && <p role="alert" className="text-sm text-red-800">{notice}</p>}

      <div className="grid items-start gap-4 lg:grid-cols-2 2xl:grid-cols-[minmax(15rem,.8fr)_minmax(22rem,1fr)_minmax(24rem,1.15fr)]">
        <div className="space-y-3">
          <StructuredPanel record={packet.structured} transcript={packet.transcript} onEvidence={showEvidence} />
          <section aria-labelledby="unc-h" className="panel p-3 text-sm">
            <h2 id="unc-h" className="font-semibold">Uncertainty</h2>
            <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-xs">
              {Object.entries(packet.uncertainty).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-neutral-700">{k.replace(/_/g, " ")}</dt>
                  <dd>{typeof v === "object" ? Object.keys(v as object).join(", ") || "none" : String(v)}</dd>
                </div>
              ))}
            </dl>
          </section>
        </div>

        <section aria-labelledby="transcript-h" className="panel min-w-0 p-3 lg:row-span-2 2xl:row-auto">
          <h2 id="transcript-h" className="mb-2 text-headline-sm">Bilingual Live Transcript <span className="ml-2 text-xs font-normal text-on-surface-variant">Original language</span></h2>
          <TranscriptPanel transcript={packet.transcript} highlight={highlight} />
        </section>

        <div className="space-y-3">
          <AlertsPanel alerts={packet.alerts} transcript={packet.transcript} busyId={busyAlert} onEvidence={showEvidence}
            readOnly={readOnly}
            onAcknowledge={async (id) => {
              setBusyAlert(id);
              setNotice(await run(() => api.acknowledge(caseId, id)));
              setBusyAlert(null);
            }} />
          <AssessmentPanel assessment={packet.assessment} onEvidence={showEvidence} />
          <Trajectory points={packet.trajectory} transcript={packet.transcript} onEvidence={showEvidence} />
          <RecommendationsPanel packet={packet} canDecide={gate.ok} blockedReason={gate.ok ? null : gate.reason}
            onEvidence={showEvidence}
            onDecide={(actionId, decision: DecisionKind, rationale) =>
              run(() => api.decide(caseId, actionId, decision, rationale))} />
          <DecisionControls packet={packet} canAct={gate.ok} blockedReason={gate.ok ? null : gate.reason}
            onOverride={(band: Band, reason) => run(() => api.override(caseId, band, reason))}
            onTakeover={() => run(() => api.takeover(caseId))}
            canMessage={messageGate.ok} messageBlockedReason={messageGate.ok ? null : messageGate.reason}
            onMessage={(text) => run(() => api.message(caseId, text))} />
        </div>
      </div>
    </main>
  );
}
