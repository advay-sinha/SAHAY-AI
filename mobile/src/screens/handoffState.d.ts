export type HandoffState = "idle" | "requesting" | "requested" | "failed";

export interface HandoffRequestController {
  dispose: () => void;
  request: () => Promise<boolean>;
}

export function createHandoffRequestController(
  onRequestHuman: () => Promise<void>,
  onStateChange: (state: HandoffState) => void,
): HandoffRequestController;
