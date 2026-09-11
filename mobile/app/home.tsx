import { useRouter } from "expo-router";
import { HomeScreen } from "../src/screens/HomeScreen";

export default function HomeRoute() {
  const router = useRouter();

  return <HomeScreen onRequestHuman={() => router.push("/handoff")} />;
}
