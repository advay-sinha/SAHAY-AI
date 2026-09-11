import { useRouter } from "expo-router";
import { HomeScreen } from "../src/screens/HomeScreen";

export default function HomeRoute() {
  const router = useRouter();

  return (
    <HomeScreen
      onOpenChat={() => router.push("/chat")}
      onOpenRequests={() => router.push("/requests")}
      onOpenTalk={() => router.push("/talk")}
      onRequestHuman={() => router.push("/handoff")}
    />
  );
}
