import { useRouter } from "expo-router";
import { MyRequestsScreen } from "../src/screens/MyRequestsScreen";

export default function RequestsRoute() {
  const router = useRouter();

  return (
    <MyRequestsScreen
      loadState="unavailable"
      onRequestHuman={() => router.push("/handoff")}
    />
  );
}
