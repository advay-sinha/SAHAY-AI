import { useRouter } from "expo-router";
import { HomeScreen } from "../src/screens/HomeScreen";

export default function HomeRoute() {
  const router = useRouter();

  return (
    <HomeScreen
      onOpenChat={() => router.push("/chat")}
      onRequestHuman={() => router.push("/handoff")}
    />
  );
}
