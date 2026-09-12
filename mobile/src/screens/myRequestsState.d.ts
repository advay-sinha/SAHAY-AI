import type { TimelineStage } from "../net/victimPayload";

export type MyRequestsLoadState = "loading" | "ready" | "failed" | "unavailable";

export interface PresentableTimelineEntry {
  stage: TimelineStage;
  label: string;
}

export type MyRequestsPresentation =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "failed" }
  | { kind: "unavailable" }
  | {
      kind: "timeline";
      reference: string;
      entries: PresentableTimelineEntry[];
    };

export function selectMyRequestsPresentation(
  loadState: MyRequestsLoadState,
  payload: unknown,
): MyRequestsPresentation;
