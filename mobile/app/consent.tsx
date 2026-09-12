import { useRouter } from "expo-router";
import { ConsentScreen } from "../src/screens/ConsentScreen";
import { useSession } from "../src/session/SessionProvider";

export default function ConsentRoute() {
  const router = useRouter();
  const { createSession } = useSession();

  async function decide(consent: "granted" | "declined"): Promise<void> {
    await createSession(consent);
    router.replace(consent === "granted" ? "/home" : "/handoff");
  }

  return (
    <ConsentScreen
      onAccept={() => decide("granted")}
      onDecline={() => decide("declined")}
    />
  );
}
