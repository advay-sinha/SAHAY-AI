import { useEffect, useState } from "react";
import type { ApiClient } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export type BackendStatus = "checking" | "operational" | "unreachable";

export async function probeBackendHealth(
  health: ApiClient["health"],
): Promise<BackendStatus> {
  try {
    const response = await health();
    return response.status === "ok" ? "operational" : "unreachable";
  } catch {
    return "unreachable";
  }
}

const LABELS: Record<BackendStatus, string> = {
  checking: "Checking backend",
  operational: "Operational",
  unreachable: "Backend unreachable",
};

export function BackendStatusBadge() {
  const { api } = useAuth();
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let cancelled = false;
    setStatus("checking");
    void probeBackendHealth(api.health).then((next) => {
      if (!cancelled) setStatus(next);
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <span
      className="ml-3 hidden items-center gap-2 rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-200 lg:flex"
      data-testid="backend-status"
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${status === "operational" ? "bg-cyan-300" : status === "unreachable" ? "bg-red-400" : "bg-slate-400"}`}
      />
      {LABELS[status]}
    </span>
  );
}
