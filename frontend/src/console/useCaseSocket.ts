import { useEffect, useRef, useState } from "react";
import { connectSession } from "../api/socket";
import type { SocketEvent } from "../types/contracts";

export type SocketState = "connecting" | "live" | "reconnecting" | "offline";

const MAX_BACKOFF_MS = 15_000;

/**
 * Subscribe to a case's session socket as an executive.
 *
 * The console treats every event as "something changed" and refetches the
 * packet from REST: the database is the source of truth, so a missed or
 * reordered frame can never leave the screen wrong for long. Reconnects back
 * off exponentially and never spin.
 *
 * The socket URL carries the token (frozen contract). It is built inside
 * connectSession, never logged, and never shown on screen.
 */
export function useCaseSocket(
  sessionId: string | undefined,
  token: string | undefined,
  onEvent: (event: SocketEvent) => void,
): SocketState {
  const [state, setState] = useState<SocketState>("connecting");
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!sessionId || !token) return;
    let socket: WebSocket | null = null;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const open = () => {
      if (stopped) return;
      setState(attempt === 0 ? "connecting" : "reconnecting");
      socket = connectSession({
        sessionId,
        token,
        onOpen: () => {
          attempt = 0;
          setState("live");
        },
        onClose: (code) => {
          if (stopped) return;
          // 1008 = the server refused us (bad token / not permitted): stop.
          if (code === 1008) {
            setState("offline");
            return;
          }
          attempt += 1;
          setState("reconnecting");
          timer = setTimeout(open, Math.min(MAX_BACKOFF_MS, 500 * 2 ** attempt));
        },
        onEvent: (event) => handler.current(event),
      });
    };

    const goOffline = () => setState("offline");
    const goOnline = () => {
      attempt = 0;
      if (!socket || socket.readyState === WebSocket.CLOSED) open();
    };
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    open();

    return () => {
      stopped = true;
      clearTimeout(timer);
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
      socket?.close();
    };
  }, [sessionId, token]);

  return state;
}
