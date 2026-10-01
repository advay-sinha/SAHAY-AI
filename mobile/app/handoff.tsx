import { useRouter } from "expo-router";
import { getLanguage } from "../src/i18n";
import { HandoffScreen } from "../src/screens/HandoffScreen";
import { useSessionSnapshot, useSessionStore } from "../src/session/SessionProvider";

export default function HandoffRoute() {
  const router = useRouter();
  const store = useSessionStore();
  const { conversation } = useSessionSnapshot();

  return (
    <HandoffScreen
      humanJoined={conversation.sessionStatus?.human_joined === true}
      onOpenChat={() => router.push("/chat")}
      onRequestHuman={() => store.requestHuman(getLanguage())}
    />
  );
}
