/** Typed WebSocket client. P0 scope is the echo required by the gate. */

import type { SocketEvent } from "../types/contracts";

export type SocketHandler = (event: SocketEvent) => void;

export interface SocketOptions {
  sessionId: string;
  token: string;
  onEvent: SocketHandler;
  onOpen?: () => void;
  onClose?: (code: number) => void;
}

export function connectSession({
  sessionId,
  token,
  onEvent,
  onOpen,
  onClose,
}: SocketOptions): WebSocket {
  // Default to the page origin so the Vite dev-server proxy (/ws -> :8000)
  // handles forwarding. VITE_WS_URL overrides it for a direct connection.
  const base = import.meta.env.VITE_WS_URL ?? `ws://${window.location.host}`;
  const socket = new WebSocket(`${base}/ws/session/${sessionId}?token=${encodeURIComponent(token)}`);

  socket.addEventListener("open", () => onOpen?.());
  socket.addEventListener("close", (event) => onClose?.(event.code));
  socket.addEventListener("message", (message) => {
    if (typeof message.data !== "string") return; // binary frames are TTS audio
    try {
      onEvent(JSON.parse(message.data) as SocketEvent);
    } catch {
      // A malformed frame is dropped rather than crashing the console.
    }
  });

  return socket;
}
