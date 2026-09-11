import { useRouter } from "expo-router";
import { ErrorScreen } from "../src/screens/ErrorScreen";

export default function ErrorRoute() {
  const router = useRouter();

  function retry(): void {
    if (router.canGoBack()) {
      router.back();
      return;
    }

    router.replace("/home");
  }

  return (
    <ErrorScreen
      onRequestHuman={() => router.push("/handoff")}
      onRetry={retry}
    />
  );
}
