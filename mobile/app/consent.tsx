import { useRouter } from "expo-router";
import { ConsentScreen } from "../src/screens/ConsentScreen";

export default function ConsentRoute() {
  const router = useRouter();

  return <ConsentScreen onAccept={() => router.replace("/home")} />;
}
