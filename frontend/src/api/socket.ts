import type { SocketEvent } from "../types/contracts";
import { validateAuthOk, validateSocketEvent } from "./socketValidation";

export type SocketHandler = (event: SocketEvent) => void;
export interface SocketOptions {
  sessionId: string;
  token: string;
  onEvent: SocketHandler;
  onReady?: () => void;
  onClose?: (code: number) => void;
}

export function connectSession({ sessionId, token, onEvent, onReady, onClose }: SocketOptions): WebSocket {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const configured = import.meta.env.VITE_WS_URL ?? `${scheme}://${window.location.host}`;
  const base = new URL(configured);
  if (!(["ws:", "wss:"].includes(base.protocol)) || base.search || base.hash || base.pathname !== "/") {
    throw new Error("invalid WebSocket configuration");
  }
  const socket = new WebSocket(`${base.origin}/ws/session/${encodeURIComponent(sessionId)}`);
  let authenticated = false;

  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({ type: "auth", token }));
  });
  socket.addEventListener("close", (event) => onClose?.(event.code));
  socket.addEventListener("message", (message) => {
    if (typeof message.data !== "string") {
      socket.close(4400, "");
      return;
    }
    let value: unknown;
    try { value = JSON.parse(message.data); } catch { socket.close(4400, ""); return; }
    if (!authenticated) {
      const auth = validateAuthOk(value, sessionId);
      if (auth === null || auth.role === "victim") { socket.close(4400, ""); return; }
      authenticated = true;
      onReady?.();
      return;
    }
    const event = validateSocketEvent(value);
    if (event === null) { socket.close(4400, ""); return; }
    onEvent(event);
  });
  return socket;
}
