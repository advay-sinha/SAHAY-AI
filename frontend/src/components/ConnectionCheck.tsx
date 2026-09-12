import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";

/** Static configuration health display. This is not a live database probe. */

interface Health {
  status: string;
  app_env: string;
  llm_provider: string;
  assessment_runner: string;
  database: string;
  fixed_scripts_ready: boolean;
  detail: Record<string, unknown>;
}

export function ConnectionCheck() {
  const { api } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((body) => !cancelled && setHealth(body))
      .catch(() => !cancelled && setHealthError(true));
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <section aria-label="Backend connection" className="border border-neutral-400 p-3 text-sm">
      <h2 className="font-medium">Backend connection</h2>

      <dl className="mt-2 grid grid-cols-[10rem_1fr] gap-x-3">
        <dt>Health</dt>
        <dd data-testid="health-status">
          {healthError ? "unreachable" : (health?.status ?? "checking…")}
        </dd>
        <dt>LLM provider</dt>
        <dd data-testid="llm-provider">{health?.llm_provider ?? "—"}</dd>
        <dt>Assessment runner</dt>
        <dd>{health?.assessment_runner ?? "—"}</dd>
        <dt>Fixed scripts</dt>
        <dd>{health == null ? "—" : health.fixed_scripts_ready ? "ready" : "not yet written"}</dd>
        <dt>Database configuration</dt>
        <dd>{health?.database ?? "â€”"}</dd>
      </dl>
      <p className="mt-2 text-on-surface-variant">Health reports configured/static state; it is not a live database probe.</p>
    </section>
  );
}
