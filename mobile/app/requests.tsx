import { useEffect, useState } from "react";
import { useRouter } from "expo-router";
import { MyRequestsScreen } from "../src/screens/MyRequestsScreen";
import { useSession } from "../src/session/SessionProvider";
import type { VictimTimeline } from "../src/net/victimPayload";
import type { MyRequestsLoadState } from "../src/screens/myRequestsState";

export default function RequestsRoute() {
  const router = useRouter();
  const { session, loadTimeline } = useSession();
  const [loadState, setLoadState] = useState<MyRequestsLoadState>(session ? "loading" : "unavailable");
  const [payload, setPayload] = useState<VictimTimeline | undefined>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    if (session === null) {
      setLoadState("unavailable");
      setPayload(undefined);
      return () => { active = false; };
    }
    setLoadState("loading");
    void loadTimeline().then((value) => {
      if (!active || value === null) return;
      setPayload(value);
      setLoadState("ready");
    }).catch(() => {
      if (active) setLoadState("failed");
    });
    return () => { active = false; };
  }, [attempt, loadTimeline, session]);

  return (
    <MyRequestsScreen
      loadState={loadState}
      payload={payload}
      onRequestHuman={() => router.push("/handoff")}
      onRetry={() => setAttempt((value) => value + 1)}
    />
  );
}
