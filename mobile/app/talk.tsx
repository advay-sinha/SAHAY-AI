import { Redirect, useRouter } from "expo-router";
import { voiceEnabled } from "../src/net/features";
import { TalkScreen } from "../src/screens/TalkScreen";

export default function TalkRoute() {
  const router = useRouter();

  // A hosted text-only build has no speech recognition behind it; a direct
  // link to /talk lands on chat instead of a microphone that cannot work.
  if (!voiceEnabled()) return <Redirect href="/chat" />;

  return (
    <TalkScreen
      onOpenChat={() => router.push("/chat")}
      onRequestHuman={() => router.push("/handoff")}
    />
  );
}
