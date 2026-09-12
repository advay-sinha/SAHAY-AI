import { useRouter } from "expo-router";
import { TalkScreen } from "../src/screens/TalkScreen";

export default function TalkRoute() {
  const router = useRouter();

  return (
    <TalkScreen
      onOpenChat={() => router.push("/chat")}
      onRequestHuman={() => router.push("/handoff")}
    />
  );
}
