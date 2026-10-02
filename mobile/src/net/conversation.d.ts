import type { VictimEvent } from "../types/events";

export type ConversationStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface SocketLike {
  readonly readyState: number;
  // Handler parameters are typed loosely so the platform WebSocket fits;
  // conversation.js reads only `data` (strings) and `code`.
  /* eslint-disable @typescript-eslint/no-explicit-any */
  onopen: ((event: any) => void) | null;
  onmessage: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onclose: ((event: any) => void) | null;
  /* eslint-enable @typescript-eslint/no-explicit-any */
  send(data: string): void;
  close(): void;
}

export type SocketFactory = (url: string) => SocketLike;

export interface ConversationState {
  readonly status: ConversationStatus;
  /** Validated victim events in arrival order, session.status excluded. */
  readonly events: readonly VictimEvent[];
  readonly sessionStatus: { state: string; consent: string; lang: string; human_joined: boolean } | null;
}

export interface Conversation {
  connect(): void;
  sendChat(text: string): Promise<void>;
  requestHuman(): Promise<void>;
  close(): void;
}

export function createConversation(options: {
  baseUrl: string;
  sessionId: string;
  token: string;
  lang: string;
  socketFactory: SocketFactory;
  onChange: (state: ConversationState) => void;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}): Conversation;

export function socketBaseUrl(httpBaseUrl: string): string | null;
