/**
 * Session socket with reconnect and resume.
 *
 * The client drops any event that is not on the allowlist. The server already
 * filters by role; this is defence in depth, not the primary control.
 */

import type { VictimEvent } from "../types/events";
import { dispatchVictimEvent } from "./victimPayload";

export interface SessionSocketOptions {
  baseUrl: string;
  sessionId: string;
  token: string;
  onEvent: (event: VictimEvent) => void;
  onAudio?: (chunk: ArrayBuffer) => void;
  onStateChange?: (state: "connecting" | "open" | "closed") => void;
}

export class SessionSocket {
  private socket: WebSocket | null = null;
  private lastAckSeq = 0;

  constructor(private readonly options: SessionSocketOptions) {}

  connect(): void {
    this.options.onStateChange?.("connecting");
    const { baseUrl, sessionId, token } = this.options;
    const socket = new WebSocket(
      `${baseUrl}/ws/session/${sessionId}?token=${encodeURIComponent(token)}`,
    );
    socket.binaryType = "arraybuffer";

    socket.onopen = () => this.options.onStateChange?.("open");
    socket.onclose = () => this.options.onStateChange?.("closed");

    socket.onmessage = (message) => {
      if (message.data instanceof ArrayBuffer) {
        this.options.onAudio?.(message.data);
        return;
      }
      dispatchVictimEvent(String(message.data), this.options.onEvent);
    };

    this.socket = socket;
  }

  /** 8-byte header: uint32 seq | uint32 ms, then 16 kHz mono PCM16. */
  sendFrame(seq: number, ms: number, pcm16: ArrayBuffer): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    const frame = new ArrayBuffer(8 + pcm16.byteLength);
    const view = new DataView(frame);
    view.setUint32(0, seq);
    view.setUint32(4, ms);
    new Uint8Array(frame, 8).set(new Uint8Array(pcm16));
    this.socket.send(frame);
    this.lastAckSeq = seq;
  }

  sendText(text: string, lang: string): void {
    this.socket?.send(JSON.stringify({ type: "chat.message", text, lang }));
  }

  /** One tap, immediate, never in a menu. */
  requestHuman(): void {
    this.socket?.send(JSON.stringify({ type: "request_human" }));
  }

  resumeFrom(): number {
    return this.lastAckSeq;
  }

  close(): void {
    this.socket?.close();
    this.socket = null;
  }
}
