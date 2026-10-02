export type ChatDeliveryStatus = "pending" | "sent" | "failed";
export type ConsentStatus = "granted" | "declined" | "pending";

export interface ChatOutgoingMessage {
  id: number;
  text: string;
  status: ChatDeliveryStatus;
}

export interface ChatState {
  draft: string;
  messages: ChatOutgoingMessage[];
}

export interface ChatSendController {
  dispose: () => void;
  getState: () => ChatState;
  retry: (id: number) => Promise<boolean>;
  send: () => Promise<boolean>;
  setDraft: (text: string) => boolean;
}

export interface DisplayMessage {
  id: string;
  /** null for the person's own confirmed words, which carry no label. */
  labelKey: "chat.assistant" | "chat.human_officer" | null;
  text: string;
}

export function createChatSendController(
  onSend: (text: string) => Promise<void>,
  onStateChange: (state: ChatState) => void,
): ChatSendController;

export function selectDisplayMessages(
  values: readonly unknown[],
  consent: ConsentStatus,
  aiPermitted: boolean,
): DisplayMessage[];
