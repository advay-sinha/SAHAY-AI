import { useRouter } from "expo-router";
import { useEffect } from "react";
import { MyRequestsScreen } from "../src/screens/MyRequestsScreen";
import { useSessionSnapshot, useSessionStore } from "../src/session/SessionProvider";
import { timelineLoadState } from "../src/session/sessionStore";

export default function RequestsRoute() {
  const router = useRouter();
  const store = useSessionStore();
  const { timeline } = useSessionSnapshot();

  // The store supplies the case from the validated session; this route passes none.
  useEffect(() => {
    void store.loadTimeline();
    return () => store.cancelTimeline();
  }, [store]);

  const loadState = timelineLoadState(timeline);

  return (
    <MyRequestsScreen
      loadState={loadState}
      onRequestHuman={() => router.push("/handoff")}
      onRetry={loadState === "failed" ? () => { void store.loadTimeline(); } : undefined}
      payload={loadState === "ready" ? timeline.payload : undefined}
    />
  );
}
