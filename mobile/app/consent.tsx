import { useRouter } from "expo-router";
import { useEffect, useRef } from "react";
import { getLanguage } from "../src/i18n";
import { ConsentScreen } from "../src/screens/ConsentScreen";
import { ErrorScreen } from "../src/screens/ErrorScreen";
import { useSessionSnapshot, useSessionStore } from "../src/session/SessionProvider";

export default function ConsentRoute() {
  const router = useRouter();
  const store = useSessionStore();
  const { creation } = useSessionSnapshot();
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // The AI conversation opens only after a granted session is created and validated.
  async function acceptConsent(): Promise<void> {
    const result = await store.startSession("granted", getLanguage());
    if (result.ok && mounted.current) router.replace("/home");
  }

  // Declined consent stays on the human-support path and never waits on the network.
  function declineConsent(): void {
    void store.startSession("declined", getLanguage());
    router.replace("/handoff");
  }

  async function retrySession(): Promise<void> {
    const result = await store.retrySessionCreation();
    if (result.ok && mounted.current && result.session.consent === "granted") router.replace("/home");
  }

  const grantedFailed = creation.consent === "granted"
    && (creation.status === "failed" || (creation.status === "creating" && creation.attempt > 1));

  if (grantedFailed) {
    return (
      <ErrorScreen
        onRequestHuman={() => router.push("/handoff")}
        onRetry={() => { void retrySession(); }}
      />
    );
  }

  return (
    <ConsentScreen
      onAccept={() => { void acceptConsent(); }}
      onDecline={declineConsent}
    />
  );
}
