import { useRouter } from "expo-router";
import { ChatScreen } from "../src/screens/ChatScreen";
import { useSession } from "../src/session/SessionProvider";

export default function ChatRoute() {
  const router = useRouter();
  const { session, events, sendChat } = useSession();

  return (
    <ChatScreen
      aiPermitted={session?.consent === "granted"}
      consent={session?.consent ?? "pending"}
      onRequestHuman={() => router.push("/handoff")}
      onSend={sendChat}
      receivedMessages={events}
    />
  );
}
