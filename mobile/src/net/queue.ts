/**
 * Offline buffer.
 *
 * Capture continues with no network; frames and messages flush on reconnect.
 * Chat must work when the network is too weak for audio: that is an
 * accessibility feature, not a fallback.
 */

export interface QueuedFrame {
  kind: "audio";
  seq: number;
  ms: number;
  pcm16: ArrayBuffer;
}

export interface QueuedMessage {
  kind: "text";
  text: string;
  lang: string;
}

export type QueuedItem = QueuedFrame | QueuedMessage;

export class OfflineQueue {
  private items: QueuedItem[] = [];

  constructor(private readonly maxItems = 2000) {}

  push(item: QueuedItem): void {
    this.items.push(item);
    if (this.items.length > this.maxItems) {
      // Drop the oldest audio rather than the newest, and never drop text.
      const index = this.items.findIndex((entry) => entry.kind === "audio");
      if (index >= 0) this.items.splice(index, 1);
    }
  }

  drain(): QueuedItem[] {
    const drained = this.items;
    this.items = [];
    return drained;
  }

  get size(): number {
    return this.items.length;
  }
}
