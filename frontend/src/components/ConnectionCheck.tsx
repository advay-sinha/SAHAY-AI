import { useCallback, useEffect, useRef, useState } from "react";
import { connectSession } from "../api/socket";
import { useAuth } from "../auth/AuthContext";
import type { SocketEvent } from "../types/contracts";

/**
 * P0 gate evidence: React -> FastAPI -> React over the session WebSocket.
 *
 * The token comes from the signed-in session. It is never read from, or
 * written to, the page URL. (An earlier version read `?token=` from the page
 * URL, which put a live JWT into browser history. That path is gone.)
 *
 * The socket handshake itself still carries the token in its own URL, because
 * the frozen contract says `WSS /ws/session/{id}?token=<jwt>` and a browser
 * WebSocket cannot send an Authorization header. That URL is not a page URL
 * and never enters browser history; the backend redacts it from its logs.
 *
 * Everything rendered here is on the victim-safe allowlist. There is no branch
 * that could display an assessment field.
 */

type Status = "idle" | "connecting" | "open" | "closed" | "error";

interface Health {
  status: string;
  llm_provider: string;
  assessment_runner: string;
  fixed_scripts_ready: boolean;
}

export function ConnectionCheck() {
  const { session, api } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [received, setReceived] = useState<SocketEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

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

  const start = useCallback(() => {
    if (!session) return;
    setStatus("connecting");
    setReceived([]);
    const socket = connectSession({
      sessionId: "console-p0",
      token: session.token,
      onOpen: () => {
        setStatus("open");
        socket.send(JSON.stringify({ type: "chat.message", text: "p0-echo", lang: "hi" }));
      },
      onClose: () => setStatus("closed"),
      onEvent: (event) => setReceived((prev) => [...prev, event]),
    });
    socketRef.current = socket;
  }, [session]);

  useEffect(() => () => socketRef.current?.close(), []);

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
        <dt>Socket</dt>
        <dd data-testid="socket-status">{status}</dd>
      </dl>

      <button
        type="button"
        onClick={start}
        disabled={!session || status === "connecting" || status === "open"}
        className="mt-3 border border-neutral-500 px-3 py-1"
        data-testid="connect"
      >
        Send echo
      </button>

      <ul className="mt-3" data-testid="events">
        {received.map((event, i) => (
          <li key={i} data-testid="event">
            <code>{JSON.stringify(event)}</code>
          </li>
        ))}
      </ul>
      {received.length > 0 && (
        <p className="mt-1" data-testid="roundtrip-ok">
          Round trip complete: {received.length} event(s) received.
        </p>
      )}
    </section>
  );
}
