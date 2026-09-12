import type { ChatAck, HumanRequestAck, SocketControlFrame, VictimEvent } from "../types/events";
import { parseSocketMessage } from "./victimPayload";

export interface SessionSocketOptions {
  baseUrl: string;
  path: string;
  sessionId: string;
  token: string;
  onEvent: (event: VictimEvent) => void;
  onControl: (frame: SocketControlFrame) => void;
  onStateChange?: (state: "connecting" | "authenticating" | "open" | "closed", code?: number) => void;
}

export class SessionSocket {
  private socket: WebSocket | null = null;
  private authenticated = false;

  constructor(private readonly options: SessionSocketOptions) {}

  connect(): void {
    if (this.socket !== null) return;
    this.options.onStateChange?.("connecting");
    const socket = new WebSocket(`${this.options.baseUrl}${this.options.path}`);
    socket.onopen = () => {
      this.options.onStateChange?.("authenticating");
      socket.send(JSON.stringify({ type: "auth", token: this.options.token }));
    };
    socket.onclose = (event) => {
      this.authenticated = false;
      this.socket = null;
      this.options.onStateChange?.("closed", event.code);
    };
    socket.onmessage = (message) => {
      if (typeof message.data !== "string") {
        socket.close(4400, "");
        return;
      }
      const frame = parseSocketMessage(message.data, this.options.sessionId);
      if (frame === null) {
        socket.close(4400, "");
        return;
      }
      if (frame.type === "auth.ok") {
        if (frame.role !== "victim" || this.authenticated) {
          socket.close(4400, "");
          return;
        }
        this.authenticated = true;
        this.options.onControl(frame);
        this.options.onStateChange?.("open");
      } else if (frame.type === "chat.ack" || frame.type === "human_request.ack") {
        if (this.authenticated) this.options.onControl(frame);
      } else if (this.authenticated) {
        this.options.onEvent(frame);
      }
    };
    this.socket = socket;
  }

  sendText(clientMessageId: string, text: string, lang: "hi" | "en"): boolean {
    if (!this.authenticated || this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify({ type: "chat.message", client_message_id: clientMessageId, text, lang }));
    return true;
  }

  requestHuman(requestId: string): boolean {
    if (!this.authenticated || this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify({ type: "request_human", request_id: requestId }));
    return true;
  }

  close(): void {
    this.socket?.close();
    this.socket = null;
    this.authenticated = false;
  }
}

export type { ChatAck, HumanRequestAck };
